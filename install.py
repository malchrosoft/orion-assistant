"""Installation guidée d'Orion — bibliothèque standard uniquement.

  python install.py          pose 3 questions (Entrée = valeur proposée)
  python install.py --auto   aucune question
Lancé automatiquement au premier double-clic sur Orion.bat / Orion.command / orion.sh.
"""
import json
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

ICI = Path(__file__).resolve().parent
VENV = ICI / ".venv"
WINDOWS = platform.system() == "Windows"
PY = VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")
AUTO = "--auto" in sys.argv


def etape(n, texte):
    print(f"\n[{n}/5] {texte}")


def demander(question, defaut):
    if AUTO:
        return defaut
    r = input(f"  {question} [{defaut}] : ").strip()
    return r or defaut


def verifier_python():
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 ou plus récent est nécessaire : https://www.python.org/downloads/")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit("Tkinter manque (Linux : sudo apt install python3-tk).")


def installer_dependances():
    if not PY.exists():
        venv.create(VENV, with_pip=True)
    subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "-r", str(ICI / "requirements.txt")])
    if platform.system() == "Linux":
        print("  Linux : si le son ou la voix manquent → sudo apt install libportaudio2 espeak-ng")


def trouver_aimp():
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        exe = Path(base) / "AIMP" / "AIMP.exe"
        if base and exe.exists():
            return str(exe)
    return ""


def configurer():
    fichier = ICI / "config.json"
    cfg = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}
    cfg["nom"] = demander("Nom de l'assistant", cfg.get("nom", "Orion"))
    aimp = trouver_aimp()
    if aimp:
        print(f"  AIMP trouvé : {aimp}")
        cfg["aimp_exe"] = aimp
    musique = Path.home() / ("Music" if (Path.home() / "Music").exists() else "Musique")
    cfg["dossier_musique"] = demander("Dossier de musique", cfg.get("dossier_musique") or str(musique))
    fichier.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg["nom"]


def raccourci_bureau(nom):
    bureau = Path.home() / "Desktop"
    if not bureau.exists():
        bureau = Path.home() / "Bureau"
    if not bureau.exists():
        return None
    if WINDOWS:  # raccourci .lnk via PowerShell (aucune dépendance)
        lien = bureau / f"{nom}.lnk"
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lien}');"
              f"$s.TargetPath='{ICI / 'Orion.bat'}';$s.WorkingDirectory='{ICI}';"
              f"$s.WindowStyle=7;$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    elif platform.system() == "Darwin":
        lien = bureau / f"{nom}.command"
        if not lien.exists():
            lien.symlink_to(ICI / "Orion.command")
    else:
        lien = bureau / f"{nom.lower()}.desktop"
        lien.write_text(f"[Desktop Entry]\nType=Application\nName={nom}\nExec={ICI / 'orion.sh'}\n"
                        f"Path={ICI}\nTerminal=false\n")
        lien.chmod(0o755)
    return lien


def main():
    print("=== Installation d'Orion ===")
    etape(1, "Vérification de Python")
    verifier_python()
    etape(2, "Installation des composants (quelques minutes)")
    installer_dependances()
    etape(3, "Téléchargement des modèles de reconnaissance vocale (≈ 55 Mo)")
    sys.path.insert(0, str(ICI))
    from orion import modeles
    modeles.installer(ICI / "models")
    etape(4, "Réglages (Entrée pour garder la proposition)")
    nom = configurer()
    subprocess.run([str(PY), "-m", "orion", "savoir"], cwd=ICI)
    etape(5, "Raccourci sur le bureau")
    lien = raccourci_bureau(nom)
    print(f"  {lien or 'Bureau introuvable : lancez Orion depuis ce dossier.'}")
    print(f"\n✓ Terminé. Double-cliquez sur « {nom} » pour le lancer."
          f"\n  Clic droit sur l'hologramme : se taire, panneau (voix, famille, savoir), quitter.")


if __name__ == "__main__":
    main()
