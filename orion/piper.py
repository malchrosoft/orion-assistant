# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Voix naturelles hors ligne (voix Piper, synthèse neuronale), installées à la demande sur le poste.

Le moteur est sherpa-onnx (Apache 2.0, k2-fsa) : son exécutable officiel est téléchargé et lancé comme un
programme séparé, jamais inclus dans Orion. Il embarque eSpeak NG (GPL-3.0) pour la phonétisation ; Orion ne
fait que lui envoyer du texte et lire le son produit. Les voix sont les voix françaises de Piper, empaquetées
par le projet sherpa-onnx ; chacune garde sa licence.

(L'archive macOS de l'ancien moteur Piper 2023 est inutilisable : exécutable Intel sans ses bibliothèques.)
"""
import platform
import shutil
import tarfile
import urllib.request

from .config import UTILISATEUR

DOSSIER = UTILISATEUR / "voix_neuronales"
UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
# Version figée : la branche 2.x a retiré la phonétisation eSpeak NG des voix Piper (il faudrait fournir les
# phonèmes soi-même) ; la 1.13.8 fait encore tout, sur les cinq plateformes.
VERSION = "v1.13.8"
BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
ARCHIVES = {("Darwin", "arm64"): "osx-arm64-shared", ("Darwin", "x86_64"): "osx-x64-shared",
            ("Linux", "x86_64"): "linux-x64-shared", ("Linux", "aarch64"): "linux-aarch64-shared-cpu",
            ("Windows", "AMD64"): "win-x64-shared-MD-Release"}

# Voix françaises retenues : licences vérifiées (la voix « tom », sous AGPL, est volontairement exclue)
VOIX = {
    "siwis": {"nom": "Siwis — femme, la plus naturelle", "paquet": "vits-piper-fr_FR-siwis-medium",
              "genre": "feminin", "locuteur": 0, "licence": "CC-BY 4.0"},
    "jessica": {"nom": "Jessica (UPMC) — femme", "paquet": "vits-piper-fr_FR-upmc-medium",
                "genre": "feminin", "locuteur": 0, "licence": "CC-BY-SA 4.0"},
    "pierre": {"nom": "Pierre (UPMC) — homme", "paquet": "vits-piper-fr_FR-upmc-medium",
               "genre": "masculin", "locuteur": 1, "licence": "CC-BY-SA 4.0"},
    "gilles": {"nom": "Gilles — homme, plus simple", "paquet": "vits-piper-fr_FR-gilles-low",
               "genre": "masculin", "locuteur": 0, "licence": "CC0"},
}


def _archive_moteur():
    suffixe = ARCHIVES.get((platform.system(), platform.machine()))
    if not suffixe:
        raise RuntimeError("Les voix naturelles n'existent pas pour ce système : Orion garde la voix du système.")
    nom = f"sherpa-onnx-{VERSION}-{suffixe}.tar.bz2"
    return nom, f"{BASE}/{VERSION}/{nom}"


def _dossier_moteur():
    return DOSSIER / "moteur" / VERSION  # une version par dossier : un moteur d'une autre version est remplacé


def executable():
    nom = "sherpa-onnx-offline-tts.exe" if platform.system() == "Windows" else "sherpa-onnx-offline-tts"
    trouves = list(_dossier_moteur().rglob(nom)) if _dossier_moteur().exists() else []
    return trouves[0] if trouves else None


def dossier_voix(cle):
    return DOSSIER / "voix" / VOIX[cle]["paquet"]


def fichier_modele(cle):
    trouves = sorted(dossier_voix(cle).glob("*.onnx")) if dossier_voix(cle).exists() else []
    return trouves[0] if trouves else dossier_voix(cle) / "absent.onnx"


def installee(cle):
    return executable() is not None and fichier_modele(cle).exists()


def _taille(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=20) as r:
        return int(r.headers.get("Content-Length", 0))


def _url_voix(cle):
    return f"{BASE}/tts-models/{VOIX[cle]['paquet']}.tar.bz2"


def estimer(cle):
    """[(libellé, octets)] de ce qui reste à télécharger."""
    lignes = []
    if executable() is None:
        lignes.append(("Moteur de voix naturelle (sherpa-onnx, une seule fois)", _taille(_archive_moteur()[1])))
    if not fichier_modele(cle).exists():
        lignes.append((f"Voix {VOIX[cle]['nom']}", _taille(_url_voix(cle))))
    return lignes


def _telecharger_et_extraire(url, cible, signaler, libelle):
    cible.mkdir(parents=True, exist_ok=True)
    archive = cible / "telechargement.tar.bz2"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(archive, "wb") as f:
        total, recu, dernier = int(r.headers.get("Content-Length", 0)), 0, 0
        while bloc := r.read(1 << 20):
            f.write(bloc)
            recu += len(bloc)
            if total and recu * 100 // total >= dernier + 10:
                dernier = recu * 100 // total
                signaler(f"{libelle} : {dernier} %")
    with tarfile.open(archive) as t:
        t.extractall(cible, filter="data")  # refuse les chemins qui sortiraient du dossier
    archive.unlink()


def installer(cle, signaler=print):
    from . import espace
    from .config import charger
    cfg = charger()
    besoin = sum(o for _, o in estimer(cle))
    if not espace.place_pour(cfg, besoin):
        raise RuntimeError(f"Installer cette voix ({besoin / 1e6:.0f} Mo) dépasserait la limite de "
                           f"{espace.limite(cfg) / 1e6:.0f} Mo fixée dans les réglages d'Orion.")
    if (DOSSIER / "piper").exists():  # ancien moteur Piper (archive macOS défectueuse) : on nettoie
        shutil.rmtree(DOSSIER / "piper", ignore_errors=True)
    for ancien in (DOSSIER / "moteur").iterdir() if (DOSSIER / "moteur").exists() else []:
        if ancien.name != VERSION:  # moteur d'une autre version (ou ancien format) : remplacé
            shutil.rmtree(ancien, ignore_errors=True) if ancien.is_dir() else ancien.unlink()
    for reste in DOSSIER.rglob("telechargement.tar.bz2"):  # archive d'une installation interrompue
        reste.unlink()
    if executable() is None:
        nom, url = _archive_moteur()
        _telecharger_et_extraire(url, _dossier_moteur(), signaler, "Moteur de voix naturelle")
        executable().chmod(0o755)
    if not fichier_modele(cle).exists():
        _telecharger_et_extraire(_url_voix(cle), DOSSIER / "voix", signaler, f"Voix {VOIX[cle]['nom']}")
    signaler(f"La voix {VOIX[cle]['nom']} est installée.")


def retirer(cle):
    """Retire une voix (le paquet n'est supprimé que si aucune autre voix installée ne l'utilise)."""
    partage = [k for k in VOIX if k != cle and VOIX[k]["paquet"] == VOIX[cle]["paquet"] and installee(k)]
    if not partage:
        shutil.rmtree(dossier_voix(cle), ignore_errors=True)


def commande(cle, fichier_wav, texte):
    """Commande de synthèse : écrit le son dans `fichier_wav`."""
    d = dossier_voix(cle)
    return [str(executable()), f"--vits-model={fichier_modele(cle)}", f"--vits-tokens={d / 'tokens.txt'}",
            f"--vits-data-dir={d / 'espeak-ng-data'}", f"--sid={VOIX[cle]['locuteur']}", "--num-threads=2",
            f"--output-filename={fichier_wav}", texte]


def credits():
    """Attributions des voix installées (fiches MODEL_CARD, quand le paquet en contient une)."""
    if not (DOSSIER / "voix").exists():
        return []
    return [f.read_text(encoding="utf-8", errors="replace").strip()[:600]
            for f in sorted((DOSSIER / "voix").rglob("MODEL_CARD"))]
