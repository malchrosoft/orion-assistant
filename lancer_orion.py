# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Point d'entrée pour PyInstaller (les imports relatifs exigent un paquet)."""
import multiprocessing

from orion.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # indispensable : le processus de la voix relance l'exécutable
    main()
