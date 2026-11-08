# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Musique, quel que soit le lecteur.

- macOS : Music (Apple), Spotify et VLC, pilotés par AppleScript ; Orion vise le lecteur demandé, sinon celui
  qui tourne, sinon il en lance un (le préféré des réglages, sinon le premier installé).
- Windows : touches multimédia (comprises par presque tous les lecteurs) ; AIMP par ses commandes s'il est là.
- Linux : playerctl (norme MPRIS, comprise par presque tous les lecteurs).
Orion dit toujours ce qui s'est vraiment passé : pas de « c'est parti » si aucun lecteur n'a répondu.
"""
import os
import shutil
import subprocess
import sys

MAC, WINDOWS = sys.platform == "darwin", sys.platform == "win32"

# macOS : nom de l'application et commandes AppleScript par lecteur
LECTEURS_MAC = {
    "musique": ("Music", {"jouer": "play", "pause": "pause", "basculer": "playpause", "suivant": "next track",
                          "precedent": "previous track", "stop": "stop"}),
    "spotify": ("Spotify", {"jouer": "play", "pause": "pause", "basculer": "playpause", "suivant": "next track",
                            "precedent": "previous track", "stop": "pause"}),
    "vlc": ("VLC", {"jouer": "play", "pause": "play", "basculer": "play", "suivant": "next",
                    "precedent": "previous", "stop": "stop"}),
}
NOMS = {"musique": "Musique", "spotify": "Spotify", "vlc": "VLC", "aimp": "AIMP"}
PHRASES = {"jouer": "C'est parti", "pause": "Pause", "basculer": "C'est fait", "suivant": "Morceau suivant",
           "precedent": "Morceau précédent", "stop": "J'arrête la musique"}


def _osa(script):
    """(réussi, sortie) ; (False, « autorisation ») si macOS attend l'accord pour piloter l'application."""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        return False, "autorisation"
    if "-1743" in r.stderr:  # « Not authorized to send Apple events » : accès refusé dans les réglages
        return False, "refusé"
    return r.returncode == 0, r.stdout.strip()


AUTORISATION = ("macOS me demande la permission de piloter {app} : accepte la fenêtre qui s'est ouverte, ou va dans "
                "Réglages Système, Confidentialité et sécurité, Automatisation, et coche {app} pour Orion.")


def installe_mac(cle):
    app = LECTEURS_MAC[cle][0]
    return any(os.path.exists(f"{d}/{app}.app") for d in ("/Applications", "/System/Applications",
                                                         os.path.expanduser("~/Applications")))


def _actif_mac(cle):
    return _osa(f'application "{LECTEURS_MAC[cle][0]}" is running')[1] == "true"


def _choisir_mac(demande, prefere, commande="jouer"):
    """Lecteur visé : le demandé ; pour jouer, le préféré des réglages ; sinon celui qui tourne ; sinon le premier
    installé."""
    if demande in LECTEURS_MAC:
        return demande
    if commande == "jouer" and prefere in LECTEURS_MAC and installe_mac(prefere):
        return prefere
    ordre = [prefere] + [c for c in LECTEURS_MAC if c != prefere] if prefere in LECTEURS_MAC else list(LECTEURS_MAC)
    return next((c for c in ordre if installe_mac(c) and _actif_mac(c)), None) or \
        next((c for c in ordre if installe_mac(c)), None)


def commander(commande, cfg, lecteur=None, recherche=None):
    """Exécute la commande (jouer, pause, basculer, suivant, precedent, stop) ; renvoie la phrase à dire."""
    if MAC:
        return _mac(commande, cfg, lecteur, recherche)
    if WINDOWS:
        return _windows(commande, cfg, lecteur)
    return _linux(commande, cfg)


def _mac(commande, cfg, lecteur, recherche):
    cle = _choisir_mac(lecteur, cfg.get("lecteur_musique"), commande)
    if not cle:
        return "Je ne trouve aucun lecteur de musique sur cet ordinateur (Musique, Spotify ou VLC)."
    app, scripts = LECTEURS_MAC[cle]
    if not installe_mac(cle):
        return f"{NOMS[cle]} n'est pas installé sur cet ordinateur."
    if commande == "jouer" and recherche and cle == "musique":  # un titre ou un artiste de la bibliothèque
        ok, sortie = _osa(f'tell application "Music" to play (first track of library playlist 1 whose name contains '
                          f'"{recherche}" or artist contains "{recherche}")')
        if sortie in ("autorisation", "refusé"):
            return AUTORISATION.format(app="Music")
        return f"Je joue {recherche} dans Musique." if ok else f"Je ne trouve pas {recherche} dans ta bibliothèque Musique."
    if commande == "jouer" and recherche and cle == "spotify":
        subprocess.run(["open", f"spotify:search:{recherche}"])
        return f"Je cherche {recherche} sur Spotify."
    if commande == "jouer" and cle == "vlc" and not _actif_mac("vlc") and cfg.get("dossier_musique"):
        subprocess.run(["open", "-a", "VLC", cfg["dossier_musique"]])  # VLC joue tout le dossier de musique
        return "Je lance ta musique dans VLC."
    if commande != "jouer" and not _actif_mac(cle):
        return "Aucune musique n'est en cours."
    ok, sortie = _osa(f'tell application "{app}" to {scripts[commande]}')
    if sortie in ("autorisation", "refusé"):
        return AUTORISATION.format(app=app)
    return f"{PHRASES[commande]} ({NOMS[cle]})." if ok else f"{NOMS[cle]} ne répond pas."


def _windows(commande, cfg, lecteur):
    aimp = cfg.get("aimp_exe", "")
    if (lecteur == "aimp" or (lecteur is None and cfg.get("lecteur_musique") == "aimp")) and os.path.exists(aimp):
        if commande == "jouer" and cfg.get("dossier_musique"):
            subprocess.Popen([aimp, "/ADD_PLAY", cfg["dossier_musique"]])
        else:
            subprocess.Popen([aimp, {"jouer": "/PLAY", "pause": "/PAUSE", "basculer": "/PAUSE", "suivant": "/NEXT",
                                     "precedent": "/PREV", "stop": "/STOP"}[commande]])
        return f"{PHRASES[commande]} (AIMP)."
    if lecteur == "spotify" and commande == "jouer":
        os.startfile("spotify:")
        return "J'ouvre Spotify."
    import ctypes  # touches multimédia : le lecteur actif (quel qu'il soit) les reçoit
    touche = {"jouer": 0xB3, "pause": 0xB3, "basculer": 0xB3, "suivant": 0xB0, "precedent": 0xB1, "stop": 0xB2}[commande]
    ctypes.windll.user32.keybd_event(touche, 0, 0, 0)
    ctypes.windll.user32.keybd_event(touche, 0, 2, 0)
    return f"{PHRASES[commande]}."


def _linux(commande, cfg):
    if not shutil.which("playerctl"):
        return "Il me faut playerctl pour piloter la musique (sudo apt install playerctl)."
    if commande == "jouer" and subprocess.run(["playerctl", "status"], capture_output=True).returncode != 0:
        if cfg.get("dossier_musique"):
            subprocess.Popen(["xdg-open", cfg["dossier_musique"]])
            return "J'ouvre ton dossier de musique."
        return "Aucun lecteur de musique n'est ouvert."
    action = {"jouer": "play", "pause": "pause", "basculer": "play-pause", "suivant": "next",
              "precedent": "previous", "stop": "stop"}[commande]
    r = subprocess.run(["playerctl", action], capture_output=True)
    return f"{PHRASES[commande]}." if r.returncode == 0 else "Aucun lecteur ne répond."
