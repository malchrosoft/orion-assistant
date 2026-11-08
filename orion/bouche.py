# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Synthèse vocale hors ligne via les voix du système (SAPI Windows, NSSpeech macOS, eSpeak Linux).

La voix tourne dans un petit processus séparé : pour faire taire Orion, on le coupe net et on en relance
un autre. C'est la seule méthode fiable sur tous les OS (pyttsx3 ne sait pas s'interrompre proprement).
On passe par multiprocessing (et non par stdin/stdout) : un exécutable sans console n'a pas toujours de
sortie standard sous Windows.
"""
import multiprocessing
import re
import threading

LANGUES = {"fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien",
           "pt": "portugais", "nl": "néerlandais", "ar": "arabe", "pl": "polonais", "tr": "turc",
           "zh": "chinois", "ja": "japonais", "ru": "russe"}
NOMS_ANGLAIS = {"fr": "french", "en": "english", "es": "spanish", "de": "german", "it": "italian",
                "pt": "portuguese", "nl": "dutch", "ar": "arabic", "pl": "polish", "tr": "turkish",
                "zh": "chinese", "ja": "japanese", "ru": "russian"}


def lister_voix():
    """[(id, nom, codes langue détectés, genre ou None)] des voix installées sur le système."""
    import pyttsx3
    from .persona import genre_de_voix
    moteur = pyttsx3.init()
    resultat = []
    for v in moteur.getProperty("voices"):
        infos = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()
        codes = {c for c, nom in NOMS_ANGLAIS.items()
                 if nom in infos or LANGUES[c] in infos or f"{c}_" in infos or f"{c}-" in infos}
        resultat.append((v.id, v.name, codes, genre_de_voix(v.name, getattr(v, "gender", None))))
    return resultat


def voix_pour(langue):
    return [v for v in lister_voix() if langue in v[2]]


def worker(entree, sortie):
    """Boucle du processus de voix : un ordre reçu = une phrase à dire, puis « fini »."""
    import pyttsx3
    moteur = pyttsx3.init()
    while True:
        ordre = entree.get()
        if ordre.get("voix"):
            moteur.setProperty("voice", ordre["voix"])
        moteur.setProperty("rate", ordre.get("vitesse", 175))
        moteur.say(ordre["texte"])
        moteur.runAndWait()
        sortie.put("fini")


class Bouche:
    def __init__(self, cfg):
        self.cfg = cfg
        self.verrou = threading.Lock()
        self.voix = cfg.get("voix_id") or next(iter(v[0] for v in voix_pour(cfg["langue"])), None)
        self._demarrer()

    def _demarrer(self):
        self.entree, self.sortie = multiprocessing.Queue(), multiprocessing.Queue()
        self.proc = multiprocessing.Process(target=worker, args=(self.entree, self.sortie), daemon=True)
        self.proc.start()

    def prononcer(self, texte):
        """Remplace le nom par sa phonétique, si elle est renseignée (ex. « Orion » → « Oh-ri-on »)."""
        phon = self.cfg.get("nom_phonetique", "").strip()
        if not phon:
            return texte
        return re.sub(rf"\b{re.escape(self.cfg['nom'])}\b", phon, texte, flags=re.IGNORECASE)

    def dire(self, texte):
        """Bloque jusqu'à la fin de la phrase ou jusqu'à interrompre(). Renvoie False si interrompu."""
        texte = self.prononcer(texte)
        with self.verrou:
            proc, entree, sortie = self.proc, self.entree, self.sortie
        entree.put({"texte": texte, "voix": self.voix, "vitesse": self.cfg["voix_vitesse"]})
        while proc.is_alive():  # interrompre() tue le processus : on rend la main aussitôt
            try:
                return sortie.get(timeout=0.2) == "fini"
            except Exception:  # queue.Empty
                continue
        return False

    def interrompre(self):
        with self.verrou:
            self.proc.kill()
            self._demarrer()

    def fermer(self):
        self.proc.kill()
