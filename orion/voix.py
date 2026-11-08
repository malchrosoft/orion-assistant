# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Écoute (Vosk, hors ligne) + reconnaissance du locuteur par empreinte vocale (x-vector Vosk)."""
import array
import json
import math
import queue

from .config import DONNEES, UTILISATEUR

PROFILS = DONNEES / "profils_voix.json"
HAUTEURS = DONNEES / "hauteurs_voix.json"  # traits mesurés de chaque phrase (hauteur, formants…), par personne
# Traits de la voix, en plus de l'empreinte de Vosk, avec l'écart en deçà duquel deux valeurs se valent :
# hauteur (f0), formants (f1-f3, liés à la longueur du conduit vocal : enfant / adulte), brillance du timbre
# (centre de gravité du spectre) et débit (mots par seconde).
TOLERANCES = {"f0": 15, "f1": 60, "f2": 120, "f3": 150, "centre": 200, "debit": 0.5}


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


def _formants(trame, taux, ordre=14):
    """Trois premiers formants (Hz) d'une trame voisée, par prédiction linéaire (LPC, Levinson-Durbin)."""
    import numpy as np
    x = np.append(trame[0], trame[1:] - 0.97 * trame[:-1]) * np.hamming(len(trame))  # préaccentuation
    r = np.correlate(x, x, "full")[len(x) - 1:len(x) + ordre]
    if r[0] <= 0:
        return None
    a, e = np.array([1.0]), r[0]
    for i in range(1, ordre + 1):  # Levinson-Durbin
        k = -(r[i] + np.dot(a[1:], r[i - 1:0:-1])) / e
        a = np.append(a, 0) + k * np.append(0, a[::-1])
        e *= 1 - k * k
    racines = [z for z in np.roots(a) if z.imag > 0]
    freqs = sorted(np.angle(z) * taux / (2 * np.pi) for z in racines
                   if -taux / np.pi * np.log(abs(z)) < 400)  # largeur de bande < 400 Hz : vrai formant
    freqs = [f for f in freqs if 150 < f < 4500]
    return freqs[:3] if len(freqs) >= 3 else None


def traits(echantillons, mots=(), taux=16000):
    """Traits de la voix d'une phrase : {f0, f1, f2, f3, centre, debit} (ceux qui ont pu être mesurés)."""
    try:
        import numpy as np
    except ImportError:
        return {}
    resultat = {}
    f0 = hauteur(echantillons, taux)
    if f0:
        resultat["f0"] = round(f0, 1)
    x = np.frombuffer(bytes(echantillons), dtype=np.int16).astype(np.float64)
    trame, pas = int(0.03 * taux), int(0.015 * taux)
    if len(x) > trame * 10:
        energie = np.array([np.sqrt(np.mean(x[d:d + trame] ** 2)) for d in range(0, len(x) - trame, pas)])
        fortes = [i for i, v in enumerate(energie) if v > 0.5 * np.max(energie)]  # cœur des voyelles
        formants = [f for i in fortes[::2] if (f := _formants(x[i * pas:i * pas + trame], taux))]
        if len(formants) >= 5:
            for k, cle in enumerate(("f1", "f2", "f3")):
                resultat[cle] = round(float(np.median([f[k] for f in formants])), 1)
        spectre = np.abs(np.fft.rfft(x[: (len(x) // trame) * trame].reshape(-1, trame) * np.hanning(trame), axis=1))
        frequences = np.fft.rfftfreq(trame, 1 / taux)
        poids = spectre[[i for i in fortes if i < len(spectre)]]
        if len(poids):
            resultat["centre"] = round(float(np.sum(poids * frequences) / (np.sum(poids) + 1e-9)), 1)
    if len(mots) >= 3:
        duree = mots[-1].get("end", 0) - mots[0].get("start", 0)
        if duree > 0.5:
            resultat["debit"] = round(len(mots) / duree, 2)
    return resultat


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
            score -= self.ecart_traits(n, hz)
            notes.append((n, score))
        return sorted(notes, key=lambda x: -x[1])

    def traits_de(self, nom):
        """{trait: (moyenne, écart type)} des traits connus de la personne (3 mesures au moins par trait)."""
        mesures = [m if isinstance(m, dict) else {"f0": m} for m in self.hauteurs.get(nom, [])]  # ancien format
        resultat = {}
        for cle in TOLERANCES:
            v = [m[cle] for m in mesures if cle in m]
            if len(v) >= 3:
                moy = sum(v) / len(v)
                resultat[cle] = (moy, math.sqrt(sum((x - moy) ** 2 for x in v) / len(v)))
        return resultat

    def hauteur_de(self, nom):
        return self.traits_de(nom).get("f0", (None, None))

    def ecart_traits(self, nom, mesure):
        """Pénalité (0 à 0,15) quand les traits de la phrase s'éloignent de ceux de la personne : chaque trait
        compte selon son écart, ramené à la variation habituelle de la personne et à une tolérance."""
        if not mesure:
            return 0.0
        mesure = mesure if isinstance(mesure, dict) else {"f0": mesure}
        connus = self.traits_de(nom)
        ecarts = [min(1.0, abs(mesure[c] - moy) / (2 * ecart + TOLERANCES[c]))
                  for c, (moy, ecart) in connus.items() if c in mesure]
        return 0.15 * sum(ecarts) / len(ecarts) if ecarts else 0.0

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
            resultat[n] = {"empreintes": len(self._empreintes(n)), "hauteur": moy, "proches": proches,
                           "traits": {c: round(m) if c != "debit" else round(m, 1)
                                      for c, (m, _) in self.traits_de(n).items()}}
        return resultat

    def enregistrer(self, nom, vecteurs, mesures=(), completer=False):
        """Enregistre la voix lue (empreintes et traits de chaque phrase). `completer` : ajoute à ce qu'Orion
        sait déjà de cette voix ; sinon remplace tout (empreintes apprises et anciens traits compris)."""
        anciennes = self._empreintes(nom) if completer and nom in self.data else []
        self.data[nom] = (anciennes + [list(v) for v in vecteurs])[-self.MAX:]
        mesures = [m for m in mesures if m]
        self.hauteurs[nom] = ((self.hauteurs.get(nom, []) if completer else []) + mesures)[-self.MAX:]
        self._sauver()

    def apprendre(self, nom, vecteur, hz=None):
        """Ajoute une empreinte (et la hauteur de voix) reconnue avec assurance ou confirmée par la personne ;
        les plus anciennes apprises cèdent la place."""
        if vecteur:
            empreintes = self._empreintes(nom) + [list(vecteur)]
            if len(empreintes) > self.MAX:
                del empreintes[5]
            self.data[nom] = empreintes
        if hz:  # traits de la phrase (dictionnaire), ou une hauteur seule
            self.hauteurs[nom] = (self.hauteurs.get(nom, []) + [hz if isinstance(hz, dict) else round(hz, 1)])[-self.MAX:]
        self._sauver()

    def retirer(self, nom):
        """Oublie la voix de la personne : empreintes et traits."""
        self.data.pop(nom, None)
        self.hauteurs.pop(nom, None)
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
        self.traits = {}           # traits de la voix de la dernière phrase complète (voir traits())
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
            self.traits = traits(self._phrase[-16000 * 2 * 12:], mots) if r.get("text") else {}  # 12 s au plus
            self.hauteur = self.traits.get("f0")
            self._phrase.clear()
            return r.get("text", ""), True, r.get("spk")
        return json.loads(self.reco.PartialResult()).get("partial", ""), False, None

    def phrase(self, sur_partiel=None):
        """Bloque jusqu'à une phrase complète ; renvoie (texte, empreinte ou None)."""
        while True:
            bloc = self.file.get()
            self._phrase += bloc
            if self.reco.AcceptWaveform(bloc):
                r = json.loads(self.reco.Result())
                self.traits = traits(self._phrase[-16000 * 2 * 12:], r.get("result", [])) if r.get("text") else {}
                self._phrase.clear()
                if r.get("text"):
                    return r["text"], r.get("spk")
            elif sur_partiel:
                partiel = json.loads(self.reco.PartialResult()).get("partial")
                if partiel:
                    sur_partiel(partiel)
