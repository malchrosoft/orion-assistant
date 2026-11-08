@echo off
rem SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
rem SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
rem Double-clic : installe Orion au premier lancement, puis le démarre sans fenêtre de console.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  where py >nul 2>nul && (py -3 install.py --auto) || (
    where python >nul 2>nul && (python install.py --auto) || (
      echo Python est introuvable. Installez-le depuis la page qui va s'ouvrir
      echo en cochant "Add Python to PATH", puis relancez Orion.
      start https://www.python.org/downloads/windows/
      pause
      exit /b 1
    )
  )
)
start "" ".venv\Scripts\pythonw.exe" -m orion
