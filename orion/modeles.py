# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Téléchargement des modèles Vosk (bibliothèque standard uniquement : utilisable avant l'installation)."""
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://alphacephei.com/vosk/models/{}.zip"
MODELES = {"vosk-model-small-fr-0.22": "reconnaissance vocale française (42 Mo)",
           "vosk-model-spk-0.4": "reconnaissance des voix de la famille (13 Mo)"}


def manquants(dossier: Path):
    return [n for n in MODELES if not (dossier / n).is_dir()]


def telecharger(dossier: Path, nom: str):
    dossier.mkdir(parents=True, exist_ok=True)
    archive = dossier / f"{nom}.zip"

    def progression(blocs, taille_bloc, total):
        if total > 0:
            pct = min(100, blocs * taille_bloc * 100 // total)
            sys.stdout.write(f"\r  {nom} : {pct:3d} %")
            sys.stdout.flush()

    urllib.request.urlretrieve(URL.format(nom), archive, progression)
    print()
    with zipfile.ZipFile(archive) as z:
        racine = dossier.resolve()
        for membre in z.namelist():  # refuse les chemins qui sortiraient du dossier
            if not (dossier / membre).resolve().is_relative_to(racine):
                raise ValueError(f"Archive suspecte : {membre}")
        z.extractall(dossier)
    archive.unlink()


def installer(dossier: Path):
    for nom in manquants(dossier):
        print(f"Téléchargement : {MODELES[nom]}")
        telecharger(dossier, nom)
