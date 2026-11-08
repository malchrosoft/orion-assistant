# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Relations entre les fenêtres d'Orion. L'hologramme est la fenêtre maîtresse :
- un seul panneau à la fois (programme séparé) : un second lancement ramène celui qui est ouvert ;
- quitter l'hologramme ferme le panneau ;
- la position de chaque fenêtre est retenue d'une fois sur l'autre (toujours ramenée dans l'écran).
Le panneau gère lui-même ses fenêtres secondaires (une seule de chaque sorte, fermées avec lui)."""
import json
import os
import signal
import time

from .config import UTILISATEUR

VERROU = UTILISATEUR / ".panneau.pid"
DEVANT = UTILISATEUR / ".panneau.devant"
POSITIONS = UTILISATEUR / ".fenetres.json"


def _vivant(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def panneau_ouvert():
    """PID du panneau en cours, ou None (verrou absent ou laissé par un panneau fermé brutalement)."""
    try:
        pid = int(VERROU.read_text())
    except (OSError, ValueError):
        return None
    return pid if pid != os.getpid() and _vivant(pid) else None


def prendre_verrou():
    VERROU.write_text(str(os.getpid()))


def rendre_verrou():
    try:
        if VERROU.read_text() == str(os.getpid()):
            VERROU.unlink()
    except OSError:
        pass


def ramener_panneau():
    """Demande au panneau ouvert de revenir au premier plan (il surveille ce fichier)."""
    DEVANT.write_text(str(time.time()))


def fermer_panneau():
    """L'hologramme se ferme : le panneau aussi."""
    pid = panneau_ouvert()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def position(nom):
    """Géométrie retenue (« LxH+X+Y » ou « +X+Y »), ou None."""
    try:
        return json.loads(POSITIONS.read_text()).get(nom)
    except (OSError, ValueError):
        return None


def retenir(nom, geometrie):
    try:
        positions = json.loads(POSITIONS.read_text()) if POSITIONS.exists() else {}
        positions[nom] = geometrie
        POSITIONS.write_text(json.dumps(positions))
    except (OSError, ValueError):
        pass


def dans_l_ecran(fenetre, geometrie):
    """Applique une géométrie retenue en la ramenant dans l'écran (l'écran a pu changer depuis)."""
    import re
    m = re.match(r"(?:(\d+)x(\d+))?\+(-?\d+)\+(-?\d+)$", geometrie or "")
    if not m:
        return False
    sl, sh = fenetre.winfo_screenwidth(), fenetre.winfo_screenheight()
    l, h = (min(int(m[1]), sl - 40), min(int(m[2]), sh - 100)) if m[1] else (fenetre.winfo_reqwidth(),
                                                                           fenetre.winfo_reqheight())
    x, y = min(max(0, int(m[3])), max(0, sl - l)), min(max(25, int(m[4])), max(0, sh - h - 60))
    fenetre.geometry(f"{l}x{h}+{x}+{y}" if m[1] else f"+{x}+{y}")
    return True
