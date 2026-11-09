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

from .texte import pour_la_voix, segments_oraux

LANGUES = {"fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien",
           "pt": "portugais", "nl": "néerlandais", "ar": "arabe", "pl": "polonais", "tr": "turc",
           "zh": "chinois", "ja": "japonais", "ru": "russe"}
NOMS_ANGLAIS = {"fr": "french", "en": "english", "es": "spanish", "de": "german", "it": "italian",
                "pt": "portuguese", "nl": "dutch", "ar": "arabic", "pl": "polish", "tr": "turkish",
                "zh": "chinese", "ja": "japanese", "ru": "russian"}


def _marque():
    from .config import UTILISATEUR
    return UTILISATEUR / ".orion_parle"


def signaler_parole(en_cours):
    """Marque partagée entre programmes : une voix d'Orion est en train de parler (essai de voix du panneau…)."""
    try:
        _marque().write_text("1" if en_cours else "0")
    except OSError:
        pass


def parole_recente(marge=1.5):
    """Vrai si une voix d'Orion parle, ou vient de se taire : ce que le micro entend alors est son écho."""
    import time
    try:
        f = _marque()
        return f.read_text() == "1" or time.time() - f.stat().st_mtime < marge
    except OSError:
        return False


def bip(volume=0.12, note=None):
    """Petit carillon doux (deux notes montantes) : Orion est prêt à écouter, sans regarder l'écran. Avec
    `note` (Hz) : un seul bip à cette hauteur (celle d'un minuteur, pour le reconnaître à l'oreille).
    Synthétisé à la volée : pas de fichier son à livrer, ni de décodeur, ni de licence."""
    def jouer():
        import array, math
        try:
            import sounddevice as sd
            taux = int(sd.query_devices(kind="output")["default_samplerate"])
            sons = array.array("h")
            for frequence, duree in (((note, 0.22),) if note else ((660, 0.09), (880, 0.14))):
                n = int(taux * duree)
                for i in range(n):  # attaque et extinction en douceur, sans clic
                    enveloppe = min(1.0, i / (0.01 * taux)) * math.exp(-4 * i / n)
                    sons.append(int(32767 * volume * enveloppe * math.sin(2 * math.pi * frequence * i / taux)))
            with sd.RawOutputStream(samplerate=taux, channels=1, dtype="int16") as f:
                f.write(sons.tobytes())
        except Exception:
            pass  # pas de sortie son : le changement de couleur suffit
    threading.Thread(target=jouer, daemon=True).start()


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


def _vers_int16(son, largeur):
    """Échantillons WAV → array('h') (16 bits signés), quel que soit le format écrit par le moteur."""
    import array
    import struct
    if largeur == 2:
        return array.array("h", son)
    valeurs = struct.unpack(f"<{len(son) // 4}f", son)  # 32 bits flottants
    return array.array("h", (max(-32768, min(32767, int(v * 32767))) for v in valeurs))


def _reechantillonner(echantillons, source, cible):
    """Rééchantillonnage linéaire (sans numpy) : quelques centièmes de seconde par phrase."""
    import array
    n = len(echantillons)
    if n < 2:
        return echantillons
    rapport = source / cible
    taille = int(n / rapport)
    sortie = array.array("h", bytes(2 * taille))
    for i in range(taille):
        x = i * rapport
        j = int(x)
        k = x - j
        a = echantillons[j]
        b = echantillons[j + 1] if j + 1 < n else a
        sortie[i] = int(a + (b - a) * k)
    return sortie


def _synthetiser(ordre, texte, native):
    """Phrase → échantillons int16 à la fréquence de la carte son, silences du début et de la fin retirés
    (les pauses entre phrases sont alors exactement celles voulues : ni rebond ni précipitation)."""
    import os
    import subprocess
    import sys
    import tempfile
    import wave
    from . import piper
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    descripteur, chemin = tempfile.mkstemp(suffix=".wav")
    os.close(descripteur)
    try:
        resultat = subprocess.run(piper.commande(ordre["piper"], chemin, texte), capture_output=True, **options)
        if resultat.returncode != 0:
            raise RuntimeError(resultat.stderr.decode("utf-8", "replace").strip()[-300:])
        with wave.open(chemin) as w:
            frequence, son, largeur = w.getframerate(), w.readframes(w.getnframes()), w.getsampwidth()
    finally:
        os.unlink(chemin)
    echantillons = _vers_int16(son, largeur)
    # macOS (CoreAudio) refuse souvent une fréquence autre que celle de la carte son : on convertit
    if native != frequence:
        echantillons = _reechantillonner(echantillons, frequence, native)
    fort = [i for i, v in enumerate(echantillons) if abs(v) > 400]
    if fort:  # on garde 40 ms autour de la voix pour ne pas couper l'attaque ni la chute
        marge = int(native * 0.04)
        echantillons = echantillons[max(0, fort[0] - marge):fort[-1] + marge]
    return echantillons


def _dire_piper(ordre):
    """Voix naturelle : chaque morceau (titre, ligne, paragraphe) est synthétisé pendant que le précédent est
    joué, dans un seul flux audio continu, avec un silence dosé entre les morceaux."""
    import queue
    import threading
    import sounddevice as sd
    native = int(sd.query_devices(kind="output")["default_samplerate"])
    prets = queue.Queue(maxsize=2)

    def preparer():
        try:
            for texte, pause in ordre["segments"]:
                prets.put((_synthetiser(ordre, texte, native), pause))
            prets.put(None)
        except Exception as e:
            prets.put(e)
    threading.Thread(target=preparer, daemon=True).start()
    with sd.RawOutputStream(samplerate=native, channels=1, dtype="int16") as f:
        while (morceau := prets.get()) is not None:
            if isinstance(morceau, Exception):
                raise morceau
            echantillons, pause = morceau
            f.write(echantillons.tobytes() + bytes(2 * int(native * pause)))


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
        for texte, _ in ordre["segments"]:  # voix du système : elle marque d'elle-même la fin des phrases
            moteur.say(texte)
        moteur.runAndWait()
        sortie.put("fini")


class Bouche:
    def __init__(self, cfg):
        self.cfg = cfg
        self.verrou = threading.Lock()
        self.recharger(cfg, annoncer=True)
        self._demarrer()

    def recharger(self, cfg, annoncer=False):
        """Applique la voix configurée (après une installation ou un réglage du panneau), sans redémarrer."""
        self.cfg = cfg
        self.voix = cfg.get("voix_id") or next(iter(v[0] for v in voix_pour(cfg["langue"])), None)
        self.piper = None
        cle = cfg.get("voix_piper")
        if cle and cfg.get("langue", "fr") == "fr":
            from . import piper
            if cle in piper.VOIX and piper.installee(cle):
                self.piper = cle
            elif annoncer:
                import sys
                print(f"[voix naturelle « {cle} » non installée : voix du système utilisée. Dites « installe ce "
                      "qui te manque » ou passez par le panneau.]", file=sys.stderr, flush=True)

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
        langue = self.cfg.get("langue", "fr")  # « .pdf » → « point P D F »
        segments = [(pour_la_voix(self.prononcer(phrase), langue), pause) for phrase, pause in segments_oraux(texte)]
        with self.verrou:
            proc, entree, sortie = self.proc, self.entree, self.sortie
        entree.put({"segments": segments, "voix": self.voix, "vitesse": self.cfg["voix_vitesse"], "piper": self.piper})
        signaler_parole(True)  # le panneau (autre programme) parle aussi : l'écoute d'Orion doit l'ignorer
        try:
            while proc.is_alive():  # interrompre() tue le processus : on rend la main aussitôt
                try:
                    return sortie.get(timeout=0.2) == "fini"
                except Exception:  # queue.Empty
                    continue
            return False
        finally:
            signaler_parole(False)

    def interrompre(self):
        with self.verrou:
            self.proc.kill()
            self._demarrer()

    def fermer(self):
        self.proc.kill()
