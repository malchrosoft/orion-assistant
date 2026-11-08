# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Configuration : valeurs par défaut surchargées par config.json à la racine."""
import json
import sys
from pathlib import Path

# Version packagée (PyInstaller) : config.json et models/ sont à côté de l'exécutable
RACINE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"

DEFAUT = {
    "nom": "Orion",                      # nom de l'assistant = mot d'éveil
    "mots_eveil": ["orion"],             # variantes acceptées (minuscules, sans accents)
    "fenetre_conversation_s": 8,         # après une réponse, pas besoin de redire le nom
    "modele_vosk": "models/vosk-model-small-fr-0.22",
    "modele_locuteur": "models/vosk-model-spk-0.4",
    "seuil_locuteur": 0.55,              # similarité cosinus minimale pour reconnaître quelqu'un
    "voix_vitesse": 175,
    "langue": "fr",                      # langue de la voix d'Orion (la compréhension reste en français)
    "langue_confirmee": False,           # au premier lancement, Orion demande confirmation à voix haute
    "voix_id": "",                       # voix choisie dans le panneau ; vide = première voix de la langue
    "aimp_exe": r"C:\Program Files\AIMP\AIMP.exe",
    "dossier_musique": "",
    "hologramme": {"taille": 360, "toujours_devant": True, "transparent": True},
    "llm": {"actif": False, "url": "http://localhost:11434/api/generate", "modele": "qwen2.5:0.5b"},
}


def charger():
    cfg = json.loads(json.dumps(DEFAUT))
    fichier = RACINE / "config.json"
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
    (RACINE / "config.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
