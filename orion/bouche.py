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
    """Voix de la langue, celles du pays principal d'abord (France pour le français, etc.)."""
    pays = {"fr": ("fr_fr", "fr-fr", "france"), "en": ("en_gb", "en-gb", "en_us", "en-us"),
            "es": ("es_es", "es-es", "espagne", "spain"), "pt": ("pt_pt", "pt-pt", "portugal")}.get(langue, ())
    voix = [v for v in lister_voix() if langue in v[2]]

    def qualite(v):  # macOS : premium > enhanced > voix standard > Eloquence (robotiques, Eddy, Flo…)
        i = v[0].lower()
        return 0 if "premium" in i else 1 if "enhanced" in i else 3 if "eloquence" in i else 2

    return sorted(voix, key=lambda v: (not any(p in f"{v[0]} {v[1]}".lower() for p in pays), qualite(v)))


def _dire_piper(ordre):
    """Voix naturelle : sherpa-onnx écrit un WAV temporaire, joué aussitôt puis supprimé."""
    import os
    import subprocess
    import sys
    import tempfile
    import wave
    import sounddevice as sd
    from . import piper
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    descripteur, chemin = tempfile.mkstemp(suffix=".wav")
    os.close(descripteur)
    try:
        resultat = subprocess.run(piper.commande(ordre["piper"], chemin, ordre["texte"]), capture_output=True,
                                  **options)
        if resultat.returncode != 0:
            raise RuntimeError(resultat.stderr.decode("utf-8", "replace").strip()[-300:])
        with wave.open(chemin) as w:
            frequence, son = w.getframerate(), w.readframes(w.getnframes())
            largeur = w.getsampwidth()
        with sd.RawOutputStream(samplerate=frequence, channels=1, dtype="int16" if largeur == 2 else "float32") as f:
            f.write(son)
    finally:
        os.unlink(chemin)


def worker(entree, sortie):
    """Boucle du processus de voix : un ordre reçu = une phrase à dire, puis « fini »."""
    moteur = None
    while True:
        ordre = entree.get()
        if ordre.get("piper"):
            try:
                _dire_piper(ordre)
                sortie.put("fini")
                continue
            except Exception as e:  # on retombe sur la voix du système, en disant pourquoi
                import sys
                print(f"[voix naturelle indisponible, voix du système utilisée] {e}", file=sys.stderr, flush=True)
        if moteur is None:
            import pyttsx3
            moteur = pyttsx3.init()
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
        self.piper = None
        cle = cfg.get("voix_piper")
        if cle and cfg.get("langue", "fr") == "fr":
            from . import piper
            if cle in piper.VOIX and piper.installee(cle):
                self.piper = cle
            else:
                import sys
                print(f"[voix naturelle « {cle} » non installée : voix du système utilisée. Dites « installe ce "
                      "qui te manque » ou passez par le panneau.]", file=sys.stderr, flush=True)
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
        entree.put({"texte": texte, "voix": self.voix, "vitesse": self.cfg["voix_vitesse"], "piper": self.piper})
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
