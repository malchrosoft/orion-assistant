# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Synthèse vocale hors ligne via les voix du système (SAPI Windows, NSSpeech macOS, eSpeak Linux).

La voix tourne dans un petit processus séparé : pour faire taire Orion, on le coupe net et on en relance
un autre. C'est la seule méthode fiable sur tous les OS (pyttsx3 ne sait pas s'interrompre proprement).
"""
import json
import subprocess
import sys
import threading

LANGUES = {"fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien",
           "pt": "portugais", "nl": "néerlandais", "ar": "arabe", "pl": "polonais", "tr": "turc",
           "zh": "chinois", "ja": "japonais", "ru": "russe"}
NOMS_ANGLAIS = {"fr": "french", "en": "english", "es": "spanish", "de": "german", "it": "italian",
                "pt": "portuguese", "nl": "dutch", "ar": "arabic", "pl": "polish", "tr": "turkish",
                "zh": "chinese", "ja": "japanese", "ru": "russian"}


def lister_voix():
    """[(id, nom, codes langue détectés)] des voix installées sur le système."""
    import pyttsx3
    moteur = pyttsx3.init()
    resultat = []
    for v in moteur.getProperty("voices"):
        infos = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()
        codes = {c for c, nom in NOMS_ANGLAIS.items()
                 if nom in infos or LANGUES[c] in infos or f"{c}_" in infos or f"{c}-" in infos}
        resultat.append((v.id, v.name, codes))
    return resultat


def voix_pour(langue):
    return [v for v in lister_voix() if langue in v[2]]


def _commande_worker():
    if getattr(sys, "frozen", False):
        return [sys.executable, "worker-voix"]
    return [sys.executable, "-m", "orion", "worker-voix"]


def worker():
    """Boucle du processus de voix : une ligne JSON en entrée = une phrase à dire."""
    import pyttsx3
    moteur = pyttsx3.init()
    for ligne in sys.stdin:
        ordre = json.loads(ligne)
        if ordre.get("voix"):
            moteur.setProperty("voice", ordre["voix"])
        moteur.setProperty("rate", ordre.get("vitesse", 175))
        moteur.say(ordre["texte"])
        moteur.runAndWait()
        print("fini", flush=True)


class Bouche:
    def __init__(self, cfg):
        self.cfg = cfg
        self.verrou = threading.Lock()
        self.voix = cfg.get("voix_id") or next(iter(v[0] for v in voix_pour(cfg["langue"])), None)
        self._demarrer()

    def _demarrer(self):
        self.proc = subprocess.Popen(_commande_worker(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1)

    def dire(self, texte):
        """Bloque jusqu'à la fin de la phrase ou jusqu'à interrompre(). Renvoie False si interrompu."""
        with self.verrou:
            proc = self.proc
        try:
            proc.stdin.write(json.dumps({"texte": texte, "voix": self.voix,
                                         "vitesse": self.cfg["voix_vitesse"]}) + "\n")
            proc.stdin.flush()
            return proc.stdout.readline().strip() == "fini"
        except (BrokenPipeError, OSError, ValueError):
            return False

    def interrompre(self):
        with self.verrou:
            self.proc.kill()
            self._demarrer()
