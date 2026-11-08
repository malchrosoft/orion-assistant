# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Informations sur l'ordinateur, en lecture seule : disques, espace libre, système, versions, fichiers.

Rien ne sort de l'ordinateur et rien n'est modifié. La recherche de fichiers se limite au dossier personnel
(et s'arrête au bout de quelques secondes) pour rester rapide et ne pas fouiller le système.
"""
import os
import platform
import re
import shutil
import string
import subprocess
import sys
import time
from pathlib import Path

from .texte import normaliser


def _go(octets):
    return f"{octets / 1e9:.0f} gigaoctets" if octets >= 10e9 else f"{octets / 1e9:.1f} gigaoctets".replace(".", ",")


def disques():
    """[(nom, chemin, total, libre)] des disques et volumes montés."""
    if platform.system() == "Windows":
        points = [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
    elif platform.system() == "Darwin":
        points = ["/"] + [str(p) for p in Path("/Volumes").iterdir() if p.is_dir() and not p.is_symlink()]
    else:
        points = ["/"] + [p for racine in ("/media", "/mnt", f"/media/{os.environ.get('USER', '')}", "/run/media")
                          if os.path.isdir(racine) for p in (str(x) for x in Path(racine).iterdir()) if os.path.ismount(p)]
    vus, resultat = set(), []
    for p in points:
        try:
            u = shutil.disk_usage(p)
        except OSError:
            continue
        if (u.total, u.free) in vus:  # le même disque vu par deux chemins (« / » et « /Volumes/Macintosh HD »)
            continue
        vus.add((u.total, u.free))
        nom = "le disque principal" if p in ("/", os.environ.get("SystemDrive", "C:") + "\\") else (Path(p).name or p)
        resultat.append((nom, p, u.total, u.free))
    return resultat


def espace_libre():
    lignes = [f"{nom} : {_go(libre)} libres sur {_go(total)}" for nom, _, total, libre in disques()]
    return (" ; ".join(lignes)[:1].upper() + " ; ".join(lignes)[1:] + ".") if lignes else "Je n'arrive pas à lire les disques."


def liste_disques():
    d = disques()
    if not d:
        return "Je ne vois aucun disque."
    noms = ", ".join(nom for nom, *_ in d)
    return f"Je vois {len(d)} disque{'s' if len(d) > 1 else ''} : {noms}."


def memoire():
    """Mémoire vive totale en octets, ou None."""
    try:
        if platform.system() == "Darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        if platform.system() == "Linux":
            kb = re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text())
            return int(kb.group(1)) * 1024 if kb else None
        if platform.system() == "Windows":
            import ctypes

            class Etat(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("reste", ctypes.c_ulonglong * 6)]
            e = Etat(dwLength=ctypes.sizeof(Etat))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e))
            return e.ullTotalPhys
    except (OSError, ValueError, AttributeError):
        return None


def nom_systeme():
    s = platform.system()
    if s == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    if s == "Windows":
        return f"Windows {platform.release()} (version {platform.version()})"
    try:
        nom = re.search(r'PRETTY_NAME="([^"]+)"', Path("/etc/os-release").read_text())
        return nom.group(1) if nom else f"Linux {platform.release()}"
    except OSError:
        return f"Linux {platform.release()}"


def infos():
    ram = memoire()
    processeur = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        processeur = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                    text=True).stdout.strip() or processeur
    texte = (f"Cet ordinateur s'appelle {platform.node().split('.')[0]}. Il fonctionne sous {nom_systeme()}, "
             f"avec un processeur {processeur} à {os.cpu_count()} cœurs")
    return texte + (f" et {round(ram / 2**30)} gigaoctets de mémoire." if ram else ".")


def versions():
    from . import __version__
    return (f"Je suis Orion version {__version__}. L'ordinateur est sous {nom_systeme()}, "
            f"et je fonctionne avec Python {platform.python_version()}.")


def chercher(nom, dossiers=False, limite=5, delai=4.0):
    """Fichiers (ou dossiers) du dossier personnel dont le nom contient `nom` : [Path], les plus récents d'abord."""
    racine, cible = Path.home(), normaliser(nom)
    if not cible:
        return []
    trouves = []
    if platform.system() == "Darwin":  # index Spotlight : instantané
        try:
            sortie = subprocess.run(["mdfind", "-onlyin", str(racine), "-name", nom], capture_output=True,
                                    text=True, timeout=delai).stdout.splitlines()
            trouves = [Path(p) for p in sortie if Path(p).is_dir() == dossiers and cible in normaliser(Path(p).name)]
        except (OSError, subprocess.TimeoutExpired):
            trouves = []
    if not trouves:
        fin = time.monotonic() + delai
        for dossier, sous, fichiers in os.walk(racine):
            sous[:] = [d for d in sous if not d.startswith(".") and d not in ("Library", "AppData", "node_modules")]
            for n in (sous if dossiers else fichiers):
                if cible in normaliser(n):
                    trouves.append(Path(dossier) / n)
            if time.monotonic() > fin or len(trouves) > 50:
                break
    trouves.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return trouves[:limite]


def decrire(chemins, dossiers=False):
    if not chemins:
        return f"Je n'ai trouvé aucun {'dossier' if dossiers else 'fichier'} de ce nom dans ton dossier personnel."
    lignes = [f"{p.name}, dans " + ("ton dossier personnel" if p.parent == Path.home() else f"le dossier {p.parent.name}")
              for p in chemins[:3]]
    debut = f"J'ai trouvé {len(chemins)} {'dossier' if dossiers else 'fichier'}{'s' if len(chemins) > 1 else ''}"
    return f"{debut} : " + " ; ".join(lignes) + ". Dis « ouvre le premier » pour l'afficher."
