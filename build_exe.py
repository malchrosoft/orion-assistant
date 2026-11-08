# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Construit Orion autonome (Python embarqué, rien à installer) dans dist/Orion, pour l'OS courant.

  pip install pyinstaller -r requirements.txt -r requirements-traduction.txt
  python build_exe.py

Les installateurs (.exe Windows, .dmg macOS, .deb Linux) sont ensuite créés par les scripts de packaging/
(voir .github/workflows/paquets.yml qui fait tout sur les trois OS). Les modèles vocaux et de traduction ne
sont pas inclus : ils se téléchargent sur le poste au premier lancement ou à l'ajout d'une langue.

Licences : les composants embarqués sont sous licences permissives (MIT, BSD, Apache 2.0, PSF) ou MPL-2.0
(pyttsx3, tqdm, certifi), qui autorisent cette distribution à condition de conserver leurs avis : leurs
métadonnées (avec fichiers de licence) sont copiées dans le paquet, et THIRD_PARTY_NOTICES.md les résume.
PyInstaller (GPL) est utilisé avec son exception explicite, qui autorise la distribution du résultat.
"""
import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ICI = Path(__file__).resolve().parent
sep = ";" if os.name == "nt" else ":"

# Paquets embarqués dont on conserve les métadonnées (licences incluses)
EMBARQUES = ["vosk", "sounddevice", "pyttsx3", "cffi", "requests", "tqdm", "srt", "websockets", "certifi",
             "urllib3", "idna", "charset-normalizer", "ctranslate2", "sentencepiece", "numpy", "PyYAML", "pypdf"]
if sys.platform == "win32":
    EMBARQUES += ["comtypes", "pywin32"]

options = [
    str(ICI / "lancer_orion.py"), "--name", "Orion", "--noconfirm", "--windowed", "--clean",
    "--add-data", f"{ICI / 'orion' / 'data'}{sep}orion/data",
    "--add-data", f"{ICI / 'LICENSE'}{sep}.",
    "--add-data", f"{ICI / 'LICENSES'}{sep}LICENSES",
    "--add-data", f"{ICI / 'THIRD_PARTY_NOTICES.md'}{sep}.",
    "--collect-all", "vosk",           # bibliothèque native de Vosk (Kaldi)
    "--collect-all", "ctranslate2",    # moteur de traduction (bibliothèques natives)
    "--hidden-import", "sentencepiece",
    "--hidden-import", "pyttsx3.drivers", "--hidden-import", "pyttsx3.drivers.sapi5",
    "--hidden-import", "pyttsx3.drivers.nsss", "--hidden-import", "pyttsx3.drivers.espeak",
]
if sys.platform == "win32":  # icône de l'application (logo d'Orion)
    options += ["--icon", str(ICI / "orion" / "data" / "logos" / "orion.ico")]
if sys.platform == "darwin":
    options += ["--osx-bundle-identifier", "fr.malchrosoft.orion"]
for paquet in EMBARQUES:
    options += ["--copy-metadata", paquet]

PyInstaller.__main__.run(options)

# Avis de licence regroupés et lisibles à côté de l'exécutable
dist = ICI / "dist" / ("Orion.app/Contents/Resources" if sys.platform == "darwin" else "Orion")
if dist.exists():
    for nom in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy(ICI / nom, dist / nom)
print("Prêt : dist/Orion (ou dist/Orion.app sous macOS).")
