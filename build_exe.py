# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Version packagée (facultative) : un dossier « Orion » avec Orion.exe, sans Python à installer.

  pip install pyinstaller && python build_exe.py
Les modèles vocaux ne sont pas inclus (paquet léger) : ils se téléchargent au premier lancement.
Construire sur l'OS cible (Windows pour un .exe).
"""
import os
import PyInstaller.__main__

sep = ";" if os.name == "nt" else ":"
PyInstaller.__main__.run([
    "lancer_orion.py", "--name", "Orion", "--noconfirm", "--windowed",
    "--add-data", f"orion/data{sep}orion/data",
    "--collect-all", "vosk",           # bibliothèque native de Vosk
    "--hidden-import", "pyttsx3.drivers", "--hidden-import", "pyttsx3.drivers.sapi5",
    "--hidden-import", "pyttsx3.drivers.nsss", "--hidden-import", "pyttsx3.drivers.espeak",
])
print("Dossier prêt : dist/Orion — à zipper et partager.")
