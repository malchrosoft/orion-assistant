#!/bin/sh
# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
# Double-clic / lancement : installe Orion au premier lancement, puis le démarre.
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" || exit 1
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Installez Python 3 : https://www.python.org/downloads/"; read _; exit 1; }
  python3 install.py --auto || { read _; exit 1; }
fi
exec .venv/bin/python -m orion "$@"
