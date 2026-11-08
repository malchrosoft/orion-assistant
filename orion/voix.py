# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Écoute (Vosk, hors ligne) + reconnaissance du locuteur par empreinte vocale (x-vector Vosk)."""
import json
import math
import queue

from .config import DATA, RACINE

PROFILS = DATA / "profils_voix.json"


def _cosinus(a, b):
    ps = sum(x * y for x, y in zip(a, b))
    return ps / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


class Profils:
    """Une empreinte moyenne par personne, stockée en JSON."""

    def __init__(self, seuil):
        self.seuil = seuil
        self.data = json.loads(PROFILS.read_text()) if PROFILS.exists() else {}

    def identifier(self, vecteur):
        if not vecteur or not self.data:
            return "invité"
        nom, score = max(((n, _cosinus(vecteur, v)) for n, v in self.data.items()), key=lambda x: x[1])
        return nom if score >= self.seuil else "invité"

    def enregistrer(self, nom, vecteurs):
        moyenne = [sum(c) / len(vecteurs) for c in zip(*vecteurs)]
        self.data[nom] = moyenne
        PROFILS.write_text(json.dumps(self.data))


class Oreille:
    """Micro → texte + empreinte. `muet` permet d'ignorer le micro pendant qu'Orion parle."""

    def __init__(self, cfg):
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model, SetLogLevel, SpkModel
        SetLogLevel(-1)
        self.file = queue.Queue()
        self.muet = False
        modele = Model(str(RACINE / cfg["modele_vosk"]))
        self.reco = KaldiRecognizer(modele, 16000)
        spk = RACINE / cfg["modele_locuteur"]
        if spk.exists():
            self.reco.SetSpkModel(SpkModel(str(spk)))
        self.flux = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1,
                                      callback=self._recevoir)
        self.flux.start()

    def _recevoir(self, donnees, *_):
        if not self.muet:
            self.file.put(bytes(donnees))

    def vider(self):
        while not self.file.empty():
            self.file.get_nowait()
        self.reco.Reset()

    def lire(self, delai=0.1):
        """Non bloquant : (texte, final, empreinte) ; texte vide si rien de nouveau."""
        try:
            bloc = self.file.get(timeout=delai)
        except queue.Empty:
            return "", False, None
        if self.reco.AcceptWaveform(bloc):
            r = json.loads(self.reco.Result())
            return r.get("text", ""), True, r.get("spk")
        return json.loads(self.reco.PartialResult()).get("partial", ""), False, None

    def phrase(self, sur_partiel=None):
        """Bloque jusqu'à une phrase complète ; renvoie (texte, empreinte ou None)."""
        while True:
            bloc = self.file.get()
            if self.reco.AcceptWaveform(bloc):
                r = json.loads(self.reco.Result())
                if r.get("text"):
                    return r["text"], r.get("spk")
            elif sur_partiel:
                partiel = json.loads(self.reco.PartialResult()).get("partial")
                if partiel:
                    sur_partiel(partiel)
