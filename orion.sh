#!/bin/sh
# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
# Double-clic / lancement : installe Orion au premier lancement, puis le démarre.
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" || exit 1
if [ ! -x .venv/bin/python ]; then
  # Premier Python disponible qui a Tkinter (le python3 par défaut peut en être dépourvu)
  PY=""
  for candidat in python3.12 python3.13 python3.11 python3.14 python3; do
    if command -v "$candidat" >/dev/null && "$candidat" -c "import tkinter" 2>/dev/null; then
      PY=$candidat; break
    fi
  done
  [ -n "$PY" ] || { echo "Installez Python 3 avec Tkinter (macOS : brew install python-tk@3.12)."; read _; exit 1; }
  "$PY" install.py --auto || { read _; exit 1; }
fi
exec .venv/bin/python -m orion "$@"
