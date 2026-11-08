# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Dossiers où Orion enregistre les documents qu'il génère (fiches, crédits).

Ce sont des documents de l'utilisateur : ils vont dans ses dossiers, pas dans les données d'Orion, et ne comptent
pas dans la limite d'espace d'Orion. Chaque dossier a un mot-clé (« documents », « école », « travail »…) pour le
désigner à la voix : « fais une fiche PDF sur Pythagore dans école ». Réglables dans le panneau, avec la commande
`python -m orion dossiers`, ou dans config.json (clés « dossiers » et « dossier_defaut »).
"""
import os
import subprocess
import sys
from pathlib import Path

from .texte import normaliser


def documents_utilisateur():
    """Le dossier Documents du système (y compris sous un autre nom localisé sous Linux)."""
    if sys.platform.startswith("linux"):
        try:
            chemin = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True,
                                    timeout=3).stdout.strip()
            if chemin and Path(chemin).is_dir() and Path(chemin) != Path.home():
                return Path(chemin)
        except (OSError, subprocess.SubprocessError):
            pass
    if sys.platform == "win32":
        profil = Path(os.environ.get("USERPROFILE", Path.home()))
        onedrive = Path(os.environ.get("OneDrive", "")) / "Documents"
        return onedrive if os.environ.get("OneDrive") and onedrive.is_dir() else profil / "Documents"
    return Path.home() / "Documents"


def defaut():
    return {"documents": str(documents_utilisateur() / "Orion")}


def liste(cfg):
    return cfg.get("dossiers") or defaut()


def cle_par_defaut(cfg):
    d = liste(cfg)
    cle = cfg.get("dossier_defaut", "documents")
    return cle if cle in d else next(iter(d))


def trouver(cfg, phrase):
    """Mot-clé de dossier cité dans la phrase (« … dans école »), sinon None."""
    t = normaliser(phrase)
    for cle in sorted(liste(cfg), key=len, reverse=True):
        if f" {normaliser(cle)}" in f" {t}":
            return cle
    return None


def chemin(cfg, cle=None):
    """Chemin du dossier (créé au besoin). Lève OSError si on ne peut pas y écrire."""
    d = liste(cfg)
    cible = Path(os.path.expandvars(os.path.expanduser(d[cle or cle_par_defaut(cfg)])))
    cible.mkdir(parents=True, exist_ok=True)
    if not os.access(cible, os.W_OK):
        raise OSError(f"Impossible d'écrire dans {cible}")
    return cible


def ajouter(cfg, cle, chemin_dossier):
    cle = cle.strip().lower()
    if not cle or not chemin_dossier.strip():
        raise ValueError("Il faut un mot-clé et un chemin.")
    cfg["dossiers"] = {**liste(cfg), cle: chemin_dossier.strip()}


def retirer(cfg, cle):
    d = dict(liste(cfg))
    if len(d) <= 1:
        raise ValueError("Il faut garder au moins un dossier.")
    d.pop(cle, None)
    cfg["dossiers"] = d
    if cfg.get("dossier_defaut") == cle:
        cfg["dossier_defaut"] = next(iter(d))
