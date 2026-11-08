# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Écoute (Vosk, hors ligne) + reconnaissance du locuteur par empreinte vocale (x-vector Vosk)."""
import array
import json
import math
import queue

from .config import DONNEES, UTILISATEUR

PROFILS = DONNEES / "profils_voix.json"
HAUTEURS = DONNEES / "hauteurs_voix.json"  # hauteur moyenne de la voix (Hz) de chaque phrase, par personne


def hauteur(echantillons, taux=16000):
    """Hauteur fondamentale médiane (Hz) des passages voisés d'une phrase, par autocorrélation ; None si
    la phrase est trop courte ou sans voix. Un second critère, indépendant de l'empreinte de Vosk."""
    try:
        import numpy as np
    except ImportError:
        return None
    x = np.frombuffer(bytes(echantillons), dtype=np.int16).astype(np.float32)
    trame, pas = int(0.04 * taux), int(0.02 * taux)
    if len(x) < trame * 5:
        return None
    seuil = 0.3 * np.sqrt(np.mean(x ** 2) + 1e-9)
    mini, maxi = int(taux / 450), int(taux / 70)  # voix d'enfant à voix grave : 70 à 450 Hz
    valeurs = []
    for d in range(0, len(x) - trame, pas):
        t = x[d:d + trame] - x[d:d + trame].mean()
        if np.sqrt(np.mean(t ** 2)) < seuil:
            continue  # silence ou souffle
        ac = np.correlate(t, t, "full")[trame - 1:]
        retard = mini + int(np.argmax(ac[mini:maxi]))
        if ac[retard] > 0.35 * ac[0]:  # passage vraiment voisé
            valeurs.append(taux / retard)
    return float(np.median(valeurs)) if len(valeurs) >= 5 else None


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
        self.ambigu = None  # (noms…) quand plusieurs voix enregistrées se ressemblent trop pour trancher
        self.data = json.loads(PROFILS.read_text()) if PROFILS.exists() else {}
        self.hauteurs = json.loads(HAUTEURS.read_text()) if HAUTEURS.exists() else {}

    def _empreintes(self, nom):
        v = self.data[nom]
        return v if v and isinstance(v[0], list) else [v]  # ancien format : une seule empreinte moyenne

    def ressemblances(self, vecteur, hz=None):
        """[(nom, score)] du plus proche au moins proche. L'empreinte (Vosk) fait l'essentiel ; la hauteur de
        voix, quand elle est connue des deux côtés, départage les voix proches (un adulte et un enfant…)."""
        notes = []
        for n in self.data:
            score = max(_cosinus(vecteur, e) for e in self._empreintes(n))
            moy, ecart = self.hauteur_de(n)
            if hz and moy:
                score -= 0.12 * min(1.0, abs(hz - moy) / (2 * ecart + 15))
            notes.append((n, score))
        return sorted(notes, key=lambda x: -x[1])

    def hauteur_de(self, nom):
        """(moyenne, écart type) des hauteurs de voix connues de la personne, ou (None, None)."""
        h = self.hauteurs.get(nom, [])
        if len(h) < 3:
            return None, None
        moy = sum(h) / len(h)
        return moy, math.sqrt(sum((v - moy) ** 2 for v in h) / len(h))

    def identifier(self, vecteur, hz=None):
        self.score, self.ambigu = 0.0, None
        if not vecteur or not self.data:
            return "invité"
        notes = self.ressemblances(vecteur, hz)
        nom, self.score = notes[0]
        proches = [n for n, sc in notes if sc >= self.seuil and self.score - sc < 0.04]
        if len(proches) > 1:
            self.ambigu = tuple(proches)  # plusieurs voix trop proches : Orion demandera qui parle
        return nom if self.score >= self.seuil else "invité"

    def comparaison(self):
        """Pour le panneau : {nom: {« empreintes », « hauteur », « proches »: {autre: ressemblance}}}."""
        resultat = {}
        for n in self.data:
            proches = {}
            for autre in self.data:
                if autre != n:
                    proches[autre] = max(_cosinus(a, b) for a in self._empreintes(n) for b in self._empreintes(autre))
            moy, _ = self.hauteur_de(n)
            resultat[n] = {"empreintes": len(self._empreintes(n)), "hauteur": moy, "proches": proches}
        return resultat

    def enregistrer(self, nom, vecteurs):
        self.data[nom] = [list(v) for v in vecteurs]
        self._sauver()

    def apprendre(self, nom, vecteur, hz=None):
        """Ajoute une empreinte (et la hauteur de voix) reconnue avec assurance ou confirmée par la personne ;
        les plus anciennes apprises cèdent la place."""
        if vecteur:
            empreintes = self._empreintes(nom) + [list(vecteur)]
            if len(empreintes) > self.MAX:
                del empreintes[5]
            self.data[nom] = empreintes
        if hz:
            self.hauteurs[nom] = (self.hauteurs.get(nom, []) + [round(hz, 1)])[-self.MAX:]
        self._sauver()

    def _sauver(self):
        PROFILS.write_text(json.dumps(self.data))
        HAUTEURS.write_text(json.dumps(self.hauteurs))


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
        self.hauteur = None        # hauteur de voix (Hz) de la dernière phrase complète
        self._phrase = bytearray()  # audio de la phrase en cours
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
        self._phrase.clear()

    def lire(self, delai=0.1):
        """Non bloquant : (texte, final, empreinte) ; texte vide si rien de nouveau."""
        try:
            bloc = self.file.get(timeout=delai)
        except queue.Empty:
            return "", False, None
        self._phrase += bloc
        if self.reco.AcceptWaveform(bloc):
            r = json.loads(self.reco.Result())
            mots = r.get("result", [])
            self.confiance = sum(m.get("conf", 1) for m in mots) / len(mots) if mots else 0.0
            self.hauteur = hauteur(self._phrase[-16000 * 2 * 12:]) if r.get("text") else None  # 12 s au plus
            self._phrase.clear()
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
