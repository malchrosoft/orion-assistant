# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Actions sur le PC : musique (voir musique.py), applications, volume."""
import subprocess
import sys
import webbrowser

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"

# Codes des touches multimédia Windows
VK = {"lecture": 0xB3, "suivant": 0xB0, "precedent": 0xB1, "stop": 0xB2,
      "volume+": 0xAF, "volume-": 0xAE, "muet": 0xAD}

APPLIS_WINDOWS = {"navigateur": "start msedge", "bloc-notes": "notepad", "calculatrice": "calc",
                  "explorateur": "explorer", "spotify": "start spotify:", "aimp": None}
APPLIS_MAC = {"navigateur": "open -a Safari", "calculatrice": "open -a Calculator",
              "explorateur": "open ~", "spotify": "open -a Spotify", "bloc-notes": "open -a TextEdit",
              "musique": "open -a Music", "vlc": "open -a VLC"}


def _touche(nom, fois=1):
    """Simule une touche multimédia : marche avec quasiment tous les lecteurs (AIMP, Spotify, VLC…)."""
    if WINDOWS:
        import ctypes
        for _ in range(fois):
            ctypes.windll.user32.keybd_event(VK[nom], 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK[nom], 0, 2, 0)
    elif MAC:
        scripts = {"volume+": "set volume output volume ((output volume of (get volume settings)) + 10)",
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
        """Musique avec le lecteur demandé, ou celui qui tourne, ou le préféré (voir musique.py)."""
        from . import musique
        return musique.commander(commande, self.cfg, lecteur, recherche)

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
