# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Écoute (Vosk, hors ligne) + reconnaissance du locuteur par empreinte vocale (x-vector Vosk)."""
import array
import json
import math
import queue

from .config import DONNEES, UTILISATEUR

PROFILS = DONNEES / "profils_voix.json"


def _cosinus(a, b):
    ps = sum(x * y for x, y in zip(a, b))
    return ps / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


class Profils:
    """Plusieurs empreintes par personne (stockées en JSON) : celles de l'enregistrement, puis celles des
    phrases reconnues avec assurance, pour suivre les variations de la voix (distance au micro, fatigue…)."""
    MAX = 40  # empreintes gardées par personne (les 5 de l'enregistrement ne sont jamais retirées)

    def __init__(self, seuil):
        self.seuil = seuil
        self.score = 0.0  # ressemblance de la dernière voix identifiée (affichée dans le terminal)
        self.data = json.loads(PROFILS.read_text()) if PROFILS.exists() else {}

    def _empreintes(self, nom):
        v = self.data[nom]
        return v if v and isinstance(v[0], list) else [v]  # ancien format : une seule empreinte moyenne

    def identifier(self, vecteur):
        self.score = 0.0
        if not vecteur or not self.data:
            return "invité"
        nom, self.score = max(((n, max(_cosinus(vecteur, e) for e in self._empreintes(n))) for n in self.data),
                              key=lambda x: x[1])
        return nom if self.score >= self.seuil else "invité"

    def enregistrer(self, nom, vecteurs):
        self.data[nom] = [list(v) for v in vecteurs]
        self._sauver()

    def apprendre(self, nom, vecteur):
        """Ajoute une empreinte reconnue avec assurance ; les plus anciennes apprises cèdent la place."""
        empreintes = self._empreintes(nom) + [list(vecteur)]
        if len(empreintes) > self.MAX:
            del empreintes[5]
        self.data[nom] = empreintes
        self._sauver()

    def _sauver(self):
        PROFILS.write_text(json.dumps(self.data))


class Oreille:
    """Micro → texte + empreinte. `muet` permet d'ignorer le micro pendant qu'Orion parle."""

    def __init__(self, cfg):
        import sounddevice as sd
        from vosk import SetLogLevel, SpkModel
        SetLogLevel(-1)
        self.file = queue.Queue()
        self.muet = False
        self.confiance = 1.0
        self.niveau = 0.0
        spk = UTILISATEUR / cfg["modele_locuteur"]
        self._spk = SpkModel(str(spk)) if spk.exists() else None
        self.charger(cfg.get("chemin_vosk") or UTILISATEUR / cfg["modele_vosk"])
        self.flux = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1,
                                      callback=self._recevoir)
        self.flux.start()

    def charger(self, chemin_modele):
        """(Re)charge le modèle de reconnaissance, par exemple pour changer de langue de discussion."""
        from vosk import KaldiRecognizer, Model
        reco = KaldiRecognizer(Model(str(chemin_modele)), 16000)
        reco.SetWords(True)  # confiance mot par mot : on ignore les transcriptions douteuses
        if self._spk:
            reco.SetSpkModel(self._spk)  # l'empreinte vocale ne dépend pas de la langue
        self.reco = reco

    def _recevoir(self, donnees, *_):
        # Volume instantané (0 à 1) pour l'hologramme : un échantillon sur huit suffit, sans numpy
        echantillons = array.array("h", bytes(donnees))[::8]
        if echantillons:
            rms = math.sqrt(sum(e * e for e in echantillons) / len(echantillons))
            self.niveau = min(1.0, rms / 3000)
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
            mots = r.get("result", [])
            self.confiance = sum(m.get("conf", 1) for m in mots) / len(mots) if mots else 0.0
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
