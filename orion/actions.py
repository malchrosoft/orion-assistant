"""Actions sur le PC : musique (AIMP, Spotify, touches multimédia), applications, volume."""
import os
import subprocess
import sys
import time
import webbrowser

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"

# Codes des touches multimédia Windows
VK = {"lecture": 0xB3, "suivant": 0xB0, "precedent": 0xB1, "stop": 0xB2,
      "volume+": 0xAF, "volume-": 0xAE, "muet": 0xAD}

APPLIS_WINDOWS = {"navigateur": "start msedge", "bloc-notes": "notepad", "calculatrice": "calc",
                  "explorateur": "explorer", "spotify": "start spotify:", "aimp": None}
APPLIS_MAC = {"navigateur": "open -a Safari", "calculatrice": "open -a Calculator",
              "explorateur": "open ~", "spotify": "open -a Spotify", "bloc-notes": "open -a TextEdit"}


def _touche(nom, fois=1):
    """Simule une touche multimédia : marche avec quasiment tous les lecteurs (AIMP, Spotify, VLC…)."""
    if WINDOWS:
        import ctypes
        for _ in range(fois):
            ctypes.windll.user32.keybd_event(VK[nom], 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK[nom], 0, 2, 0)
    elif MAC:
        scripts = {"lecture": 'tell application "Spotify" to playpause',
                   "suivant": 'tell application "Spotify" to next track',
                   "precedent": 'tell application "Spotify" to previous track',
                   "stop": 'tell application "Spotify" to pause',
                   "volume+": "set volume output volume ((output volume of (get volume settings)) + 10)",
                   "volume-": "set volume output volume ((output volume of (get volume settings)) - 10)",
                   "muet": "set volume with output muted"}
        subprocess.run(["osascript", "-e", scripts[nom]], capture_output=True)
    else:  # Linux : playerctl / pactl
        cmd = {"lecture": "playerctl play-pause", "suivant": "playerctl next", "precedent": "playerctl previous",
               "stop": "playerctl stop", "volume+": "pactl set-sink-volume @DEFAULT_SINK@ +10%",
               "volume-": "pactl set-sink-volume @DEFAULT_SINK@ -10%",
               "muet": "pactl set-sink-mute @DEFAULT_SINK@ toggle"}[nom]
        subprocess.run(cmd, shell=True, capture_output=True)


class Actions:
    def __init__(self, cfg):
        self.cfg = cfg

    # --- Musique -------------------------------------------------------------
    def musique(self, commande, lecteur=None, recherche=None):
        if commande == "jouer" and lecteur == "spotify":
            return self.spotify(recherche)
        if lecteur == "aimp" or (commande == "jouer" and self._aimp_dispo()):
            return self.aimp(commande)
        _touche({"jouer": "lecture", "pause": "lecture", "suivant": "suivant",
                 "precedent": "precedent", "stop": "stop"}[commande])
        return {"jouer": "C'est parti.", "pause": "Pause.", "suivant": "Morceau suivant.",
                "precedent": "Morceau précédent.", "stop": "J'arrête la musique."}[commande]

    def _aimp_dispo(self):
        return WINDOWS and os.path.exists(self.cfg["aimp_exe"])

    def aimp(self, commande):
        if not self._aimp_dispo():
            return "Je ne trouve pas AIMP. Vérifie le chemin aimp_exe dans la configuration."
        exe = self.cfg["aimp_exe"]
        if commande == "jouer" and self.cfg.get("dossier_musique"):
            subprocess.Popen([exe, "/ADD_PLAY", self.cfg["dossier_musique"]])
        else:
            arg = {"jouer": "/PLAY", "pause": "/PAUSE", "suivant": "/NEXT",
                   "precedent": "/PREV", "stop": "/STOP"}[commande]
            subprocess.Popen([exe, arg])
        return "AIMP s'en occupe."

    def spotify(self, recherche=None):
        uri = f"spotify:search:{recherche}" if recherche else "spotify:"
        if WINDOWS:
            os.startfile(uri)
        elif MAC:
            subprocess.run(["open", uri])
        else:
            subprocess.Popen(["xdg-open", uri])
        time.sleep(2.5)
        _touche("lecture")
        return f"Je cherche {recherche} sur Spotify." if recherche else "J'ouvre Spotify."

    # --- Système -------------------------------------------------------------
    def volume(self, sens):
        if sens == "muet":
            _touche("muet")
            return "Son coupé."
        _touche("volume+" if sens == "plus" else "volume-", fois=5)
        return "Je monte le son." if sens == "plus" else "Je baisse le son."

    def ouvrir(self, appli):
        table = APPLIS_WINDOWS if WINDOWS else APPLIS_MAC
        if appli == "aimp" and WINDOWS:
            subprocess.Popen([self.cfg["aimp_exe"]])
        elif appli in table and table[appli]:
            subprocess.Popen(table[appli], shell=True)
        else:
            return f"Je ne sais pas encore ouvrir {appli}."
        return f"J'ouvre {appli}."

    def ouvrir_lien(self, url):
        """Ouvre un lien (navigateur, ou application associée comme JW Library pour jw.org/finder)."""
        webbrowser.open(url)

    def recherche_web(self, sujet):
        webbrowser.open(f"https://fr.wikipedia.org/w/index.php?search={sujet}")
        return f"Je cherche {sujet} sur Wikipédia."
