# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Configuration et emplacements.

En développement, tout vit dans le dépôt. Une fois installé (version packagée), le dossier de l'application
est en lecture seule : les données livrées (DATA) y restent, et tout ce qui s'écrit (réglages, modèles,
langues, base de savoir, voix de la famille) va dans le dossier de l'utilisateur (UTILISATEUR).
"""
import json
import os
import sys
from pathlib import Path

PACKAGE = getattr(sys, "frozen", False)
RACINE = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"  # données livrées, en lecture seule une fois installé


def _dossier_utilisateur():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Orion"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Orion"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "orion"


UTILISATEUR = _dossier_utilisateur() if PACKAGE else RACINE
DONNEES = UTILISATEUR / "donnees" if PACKAGE else DATA  # base, fiches apprises, voix de la famille
DONNEES.mkdir(parents=True, exist_ok=True)

DEFAUT = {
    "nom": "Orion",                      # nom de l'assistant = mot d'éveil
    "mots_eveil": ["orion"],             # variantes acceptées (minuscules, sans accents)
    "fenetre_conversation_s": 8,         # quand Orion vient de poser une question, on peut répondre sans le nom
    "formules_eveil": ["hey", "he", "eh", "et", "dis", "dit", "di", "j", "ok"],  # « hey Orion », « dis Orion » (+ transcriptions)
    "modele_vosk": "models/vosk-model-small-fr-0.22",
    "modele_locuteur": "models/vosk-model-spk-0.4",
    "seuil_locuteur": 0.55,
    "confiance_min": 0.6,                # en dessous, Orion dit « je n'ai pas bien compris » au lieu de répondre              # similarité cosinus minimale pour reconnaître quelqu'un
    "voix_vitesse": 175,
    "langue": "fr",                      # langue de la voix d'Orion (la compréhension reste en français)
    "langue_confirmee": False,           # au premier lancement, Orion demande confirmation à voix haute
    "voix_piper": "",                    # voix naturelle Piper (siwis, jessica, pierre, gilles) ; vide = voix système
    "voix_id": "",                       # voix choisie dans le panneau ; vide = première voix de la langue
    "limite_disque_mo": 1024,            # espace maximal des données d'Orion (hors documents générés)
    "dossiers": {},                      # {mot-clé: chemin} où enregistrer les PDF ; vide = Documents/Orion
    "dossier_defaut": "documents",            # espace maximal occupé par Orion (réglable au panneau / en commande)
    "langue_discussion": "fr",           # langue dans laquelle on parle à Orion (voir onglet Langues)
    "nom_phonetique": "",                # facultatif : comment prononcer le nom (ex. « Oh-ri-on »)
    "genre": "neutre",                   # présentation : neutre (« Orion »), feminin ou masculin
    "aimp_exe": r"C:\Program Files\AIMP\AIMP.exe",
    "dossier_musique": "",
    "hologramme": {"taille": 420, "toujours_devant": True, "transparent": True,
                   "densite": 800},           # points du visage : baisser (400) sur une machine modeste
    "conversation": {},                  # discussion libre (voir orion/conversation.py : modèle local, Claude)
}


def charger():
    cfg = json.loads(json.dumps(DEFAUT))
    fichier = UTILISATEUR / "config.json"
    if fichier.exists():
        for k, v in json.loads(fichier.read_text(encoding="utf-8")).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    if cfg["nom"].lower() not in cfg["mots_eveil"]:
        cfg["mots_eveil"].append(cfg["nom"].lower())
    return cfg


def sauver(cfg):
    """Écrit dans config.json uniquement ce qui diffère des valeurs par défaut."""
    diff = {k: v for k, v in cfg.items() if v != DEFAUT.get(k)}
    (UTILISATEUR / "config.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
