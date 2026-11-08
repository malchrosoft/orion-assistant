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
# Supertonic 3 n'existe que dans la branche 2.x : ce moteur-là est installé à côté, pour ces voix seulement
VERSION_SUPERTONIC = "v2.0.1"
BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
ARCHIVES = {("Darwin", "arm64"): "osx-arm64-shared", ("Darwin", "x86_64"): "osx-x64-shared",
            ("Linux", "x86_64"): "linux-x64-shared", ("Linux", "aarch64"): "linux-aarch64-shared-cpu",
            ("Windows", "AMD64"): "win-x64-shared-MD-Release"}

# Voix françaises retenues : licences vérifiées (« tom » et « tjiho », sous AGPL, sont volontairement exclues).
# Kokoro est un modèle plus récent (Apache 2.0) dont la voix française « ff_siwis » est la plus naturelle ;
# il s'appuie sur le même moteur, avec ses propres options (« moteur »: « kokoro »).
VOIX = {
    "kokoro": {"nom": "Siwis (Kokoro) — femme, la plus naturelle", "paquet": "kokoro-int8-multi-lang-v1_0",
               "genre": "feminin", "locuteur": 30, "licence": "Apache 2.0 (voix ff_siwis)", "moteur": "kokoro"},
    "siwis": {"nom": "Siwis (Piper) — femme", "paquet": "vits-piper-fr_FR-siwis-medium",
              "genre": "feminin", "locuteur": 0, "licence": "CC-BY 4.0"},
    "jessica": {"nom": "Jessica (UPMC) — femme", "paquet": "vits-piper-fr_FR-upmc-medium",
                "genre": "feminin", "locuteur": 0, "licence": "CC-BY-SA 4.0"},
    "pierre": {"nom": "Pierre (UPMC) — homme", "paquet": "vits-piper-fr_FR-upmc-medium",
               "genre": "masculin", "locuteur": 1, "licence": "CC-BY-SA 4.0"},
    # Miro : voix d'homme de bonne qualité, CC-BY-NC-ND 4.0 (usage non commercial, sans modification : c'est le
    # cas d'Orion) ; apprise sur une voix trop lente de 20 % d'après son auteur, d'où l'accélération (« debit »)
    "miro": {"nom": "Miro — homme, voix posée", "paquet": "vits-piper-fr_FR-miro-high-int8", "genre": "masculin",
             "locuteur": 0, "licence": "CC-BY-NC-ND 4.0 (usage non commercial)", "debit": 0.8},
    "gilles": {"nom": "Gilles — homme, plus simple", "paquet": "vits-piper-fr_FR-gilles-low",
               "genre": "masculin", "locuteur": 0, "licence": "CC0"},
}
# Supertonic 3 (Supertone) : modèle récent et vivant, 31 langues, plusieurs locuteurs dans un même paquet.
# Licence du modèle : OpenRAIL-M (usage libre, avec des restrictions d'usage nuisible qui s'appliquent aussi
# aux utilisateurs) ; code MIT. Locuteurs retenus à l'écoute : 1 et 3 (femmes), 6 à 9 (hommes).
for _cle, _nom, _genre, _sid in (("supertonic-f1", "femme, vive", "feminin", 1),
                                 ("supertonic-f3", "femme, enjouée", "feminin", 3),
                                 ("supertonic-h6", "homme, chaleureux", "masculin", 6),
                                 ("supertonic-h7", "homme, dynamique", "masculin", 7),
                                 ("supertonic-h8", "homme, clair", "masculin", 8),
                                 ("supertonic-h9", "homme, grave", "masculin", 9)):
    VOIX[_cle] = {"nom": f"Supertonic — {_nom}", "paquet": "sherpa-onnx-supertonic-3-tts-int8-2026-05-11",
                  "genre": _genre, "locuteur": _sid, "licence": "OpenRAIL-M (modèle) ; MIT (code)",
                  "moteur": "supertonic"}


def _version(cle=None):
    """Version du moteur qu'il faut à cette voix (Supertonic : la branche 2.x)."""
    return VERSION_SUPERTONIC if cle and VOIX[cle].get("moteur") == "supertonic" else VERSION


def _archive_moteur(version=VERSION):
    suffixe = ARCHIVES.get((platform.system(), platform.machine()))
    if not suffixe:
        raise RuntimeError("Les voix naturelles n'existent pas pour ce système : Orion garde la voix du système.")
    nom = f"sherpa-onnx-{version}-{suffixe}.tar.bz2"
    return nom, f"{BASE}/{version}/{nom}"


def _dossier_moteur(version=VERSION):
    return DOSSIER / "moteur" / version  # une version par dossier : les versions inutiles sont retirées


def executable(cle=None):
    nom = "sherpa-onnx-offline-tts.exe" if platform.system() == "Windows" else "sherpa-onnx-offline-tts"
    dossier = _dossier_moteur(_version(cle))
    trouves = list(dossier.rglob(nom)) if dossier.exists() else []
    return trouves[0] if trouves else None


def dossier_voix(cle):
    return DOSSIER / "voix" / VOIX[cle]["paquet"]


def fichier_modele(cle):
    trouves = sorted(dossier_voix(cle).glob("*.onnx")) if dossier_voix(cle).exists() else []
    return trouves[0] if trouves else dossier_voix(cle) / "absent.onnx"


def installee(cle):
    return executable(cle) is not None and fichier_modele(cle).exists()


def _taille(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=20) as r:
        return int(r.headers.get("Content-Length", 0))


def _url_voix(cle):
    return f"{BASE}/tts-models/{VOIX[cle]['paquet']}.tar.bz2"


def estimer(cle):
    """[(libellé, octets)] de ce qui reste à télécharger."""
    lignes = []
    if executable(cle) is None:
        lignes.append((f"Moteur de voix naturelle (sherpa-onnx {_version(cle)}, une seule fois)",
                       _taille(_archive_moteur(_version(cle))[1])))
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
        if ancien.name not in (VERSION, VERSION_SUPERTONIC):  # autre version (ou ancien format) : remplacé
            shutil.rmtree(ancien, ignore_errors=True) if ancien.is_dir() else ancien.unlink()
    for reste in DOSSIER.rglob("telechargement.tar.bz2"):  # archive d'une installation interrompue
        reste.unlink()
    if executable(cle) is None:
        nom, url = _archive_moteur(_version(cle))
        _telecharger_et_extraire(url, _dossier_moteur(_version(cle)), signaler, "Moteur de voix naturelle")
        executable(cle).chmod(0o755)
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
    if VOIX[cle].get("moteur") == "supertonic":
        modele = [f"--supertonic-{partie}={d / f'{partie.replace(chr(45), chr(95))}.int8.onnx'}"
                  for partie in ("duration-predictor", "text-encoder", "vector-estimator", "vocoder")]
        modele += [f"--supertonic-tts-json={d / 'tts.json'}", f"--supertonic-unicode-indexer={d / 'unicode_indexer.bin'}",
                   f"--supertonic-voice-style={d / 'voice.bin'}", "--lang=fr"]
    elif VOIX[cle].get("moteur") == "kokoro":  # modèle multilingue : la langue est donnée explicitement
        modele = [f"--kokoro-model={fichier_modele(cle)}", f"--kokoro-voices={d / 'voices.bin'}",
                  f"--kokoro-tokens={d / 'tokens.txt'}", f"--kokoro-data-dir={d / 'espeak-ng-data'}",
                  f"--kokoro-dict-dir={d / 'dict'}", f"--kokoro-lexicon={d / 'lexicon-us-en.txt'},{d / 'lexicon-zh.txt'}",
                  "--kokoro-lang=fr"]
    else:
        modele = [f"--vits-model={fichier_modele(cle)}", f"--vits-tokens={d / 'tokens.txt'}",
                  f"--vits-data-dir={d / 'espeak-ng-data'}", f"--vits-length-scale={VOIX[cle].get('debit', 1.0)}"]
    return [str(executable(cle)), *modele, f"--sid={VOIX[cle]['locuteur']}", "--num-threads=2",
            f"--output-filename={fichier_wav}", texte]


def credits():
    """Attributions des voix installées (fiches MODEL_CARD, quand le paquet en contient une)."""
    if not (DOSSIER / "voix").exists():
        return []
    return [f.read_text(encoding="utf-8", errors="replace").strip()[:600]
            for f in sorted((DOSSIER / "voix").rglob("MODEL_CARD"))] + \
        [f"Kokoro (hexgrad), voix française ff_siwis : Apache 2.0 — {f.parent.name}"
         for f in sorted((DOSSIER / "voix").glob("kokoro-*/LICENSE"))]
