# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Langues de discussion supplémentaires, installées à la demande sur le poste (rien n'est stocké dans le dépôt).

Pour chaque langue : un modèle Vosk (comprendre la parole) et des modèles de traduction Argos vers et depuis le
français. Orion pense toujours en français : phrase entendue → traduite en français → cerveau → réponse →
traduite dans la langue. Internet n'est nécessaire qu'à l'installation.

Les modèles Argos sont lus directement avec CTranslate2 et SentencePiece, sans le paquet `argostranslate` :
celui-ci impose stanza et PyTorch (plus d'un Go), inadaptés aux machines modestes. Le moteur fait ~60 Mo.
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from .config import PACKAGE, UTILISATEUR
from .modeles import telecharger as telecharger_vosk

DOSSIER = UTILISATEUR / "langues"                     # langues/<code>/vosk/… ; langues/traduction/<paquet>/…
TRADUCTION = DOSSIER / "traduction"
INDEX_ARGOS = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
MOTEUR = ["ctranslate2>=4,<5", "sentencepiece>=0.2,<0.3"]
TAILLE_MOTEUR = 60_000_000  # estimation (roues ctranslate2 + sentencepiece + numpy + pyyaml)

# Le français est la langue native d'Orion : toujours présente, jamais retirée.
CATALOGUE = {
    "fr": {"nom": "français", "vosk": "vosk-model-small-fr-0.22"},
    "en": {"nom": "anglais", "vosk": "vosk-model-small-en-us-0.15"},
    "es": {"nom": "espagnol", "vosk": "vosk-model-small-es-0.42"},
    "de": {"nom": "allemand", "vosk": "vosk-model-small-de-0.15"},
    "it": {"nom": "italien", "vosk": "vosk-model-small-it-0.22"},
    "pt": {"nom": "portugais", "vosk": "vosk-model-small-pt-0.3"},
    "nl": {"nom": "néerlandais", "vosk": "vosk-model-small-nl-0.22"},
    "pl": {"nom": "polonais", "vosk": "vosk-model-small-pl-0.22"},
    "tr": {"nom": "turc", "vosk": "vosk-model-small-tr-0.3"},
    "ru": {"nom": "russe", "vosk": "vosk-model-small-ru-0.22"},
    "zh": {"nom": "chinois", "vosk": "vosk-model-small-cn-0.22"},
    "ar": {"nom": "arabe", "vosk": "vosk-model-small-ar-tn-0.1-linto"},
}

# Lexique traduit à la main : les mots qui doivent marcher même si la traduction automatique hésite.
LEXIQUE = {
    "en": {"stop": "stop|shut up|be quiet|quiet|silence|enough|wait", "oui": "yes|yeah|ok|okay|sure|go ahead",
           "non": "no|nope|cancel"},
    "es": {"stop": "para|basta|callate|silencio|espera|stop", "oui": "si|vale|claro|de acuerdo|ok", "non": "no|cancela"},
    "de": {"stop": "stopp|stop|halt|ruhe|sei still|warte|genug", "oui": "ja|ok|klar|gerne", "non": "nein|abbrechen"},
    "it": {"stop": "stop|basta|zitto|silenzio|aspetta|fermati", "oui": "si|ok|certo|va bene", "non": "no|annulla"},
    "pt": {"stop": "para|pare|chega|silencio|espera|stop", "oui": "sim|ok|claro|pode", "non": "nao|cancela"},
    "nl": {"stop": "stop|stil|wacht|genoeg|hou op", "oui": "ja|ok|prima|goed", "non": "nee|annuleer"},
    "pl": {"stop": "stop|cisza|przestan|czekaj|dosc", "oui": "tak|ok|dobrze", "non": "nie|anuluj"},
    "tr": {"stop": "dur|sus|yeter|bekle|stop", "oui": "evet|tamam|olur", "non": "hayir|iptal"},
    "ru": {"stop": "стоп|хватит|тихо|замолчи|подожди", "oui": "да|ок|хорошо|конечно", "non": "нет|отмена"},
    "zh": {"stop": "停|停止|安静|别说了|等一下", "oui": "是|好|对|可以", "non": "不|不要|取消"},
    "ar": {"stop": "توقف|اسكت|كفى|انتظر", "oui": "نعم|حسنا|موافق", "non": "لا|إلغاء"},
}


def nom(code):
    return CATALOGUE[code]["nom"]


def dossier_vosk(code):
    """Le français est livré dans models/ ; les autres langues dans langues/<code>/."""
    if code == "fr":
        return UTILISATEUR / "models"
    return DOSSIER / code


def chemin_modele_vosk(code):
    return dossier_vosk(code) / CATALOGUE[code]["vosk"]


# --- Traduction ----------------------------------------------------------------------------------------------

def _paires(code):
    """Paires de traduction nécessaires (dans les deux sens), en passant par l'anglais si besoin."""
    if code == "fr":
        return []
    if code == "en":
        return [("fr", "en"), ("en", "fr")]
    return [("fr", "en"), ("en", code), (code, "en"), ("en", "fr")]


def _index():
    with urllib.request.urlopen(urllib.request.Request(INDEX_ARGOS, headers=UA), timeout=20) as r:
        return json.load(r)


def _paquet(index, de, vers):
    paquet = next((p for p in index if (p["from_code"], p["to_code"]) == (de, vers)), None)
    if not paquet:
        raise ValueError(f"Aucun modèle de traduction {de} → {vers} n'est disponible.")
    return paquet


def _nom_paquet(de, vers):
    return f"{de}_{vers}"


def _taille(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as r:
        return int(r.headers.get("Content-Length", 0))


def moteur_present():
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
        return True
    except ImportError:
        return False


def installee(code):
    if code == "fr":
        return True
    return chemin_modele_vosk(code).is_dir() and all(
        (TRADUCTION / _nom_paquet(de, vers) / "model").is_dir() for de, vers in _paires(code))


def installees():
    return [c for c in CATALOGUE if installee(c)]


def estimer(code):
    """Avant toute installation : [(libellé, octets)] de ce qui reste à télécharger, et l'espace libre.
    Les modèles déjà présents (ex. anglais ↔ français partagé par plusieurs langues) ne sont pas recomptés."""
    lignes = []
    if not chemin_modele_vosk(code).is_dir():
        url = f"https://alphacephei.com/vosk/models/{CATALOGUE[code]['vosk']}.zip"
        lignes.append((f"Reconnaissance vocale en {nom(code)}", _taille(url)))
    index = None
    for de, vers in _paires(code):
        if not (TRADUCTION / _nom_paquet(de, vers) / "model").is_dir():
            index = index or _index()
            lignes.append((f"Traduction {nom(de)} → {nom(vers)}", _taille(_paquet(index, de, vers)["links"][0])))
    if lignes and not moteur_present():
        lignes.append(("Moteur de traduction (une seule fois, estimation)", TAILLE_MOTEUR))
    DOSSIER.mkdir(parents=True, exist_ok=True)
    return lignes, shutil.disk_usage(DOSSIER).free


def _extraire_paquet(archive, cible):
    """Ne garde que le modèle CTranslate2, SentencePiece et le README (attribution exigée par la licence
    CC-BY 4.0 des modèles OPUS-MT) ; ignore les fichiers stanza/PyTorch."""
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parties = info.filename.split("/", 1)
            if len(parties) < 2 or not parties[1] or info.is_dir():
                continue
            relatif = parties[1]
            if not (relatif.startswith("model/") or relatif in ("sentencepiece.model", "metadata.json", "README.md")):
                continue
            destination = (cible / relatif).resolve()
            if not destination.is_relative_to(cible.resolve()):
                raise ValueError(f"Archive suspecte : {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(destination, "wb") as dst:
                shutil.copyfileobj(src, dst)


def installer(code, signaler=print):
    """Télécharge ce qui manque. `signaler` reçoit des messages de progression lisibles."""
    if code not in CATALOGUE:
        raise ValueError(f"Langue inconnue : {code}")
    from . import espace
    from .config import charger
    cfg = charger()
    besoin = sum(o for _, o in estimer(code)[0])
    if not espace.place_pour(cfg, besoin):
        raise RuntimeError(f"Installer le {nom(code)} ({besoin / 1e6:.0f} Mo) dépasserait la limite de "
                           f"{espace.limite(cfg) / 1e6:.0f} Mo fixée dans les réglages d'Orion.")
    if not moteur_present() and code != "fr":
        if PACKAGE:  # la version installée embarque le moteur ; pip n'y est pas disponible
            raise RuntimeError("Le moteur de traduction est absent de cette version d'Orion.")
        signaler("Installation du moteur de traduction…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *MOTEUR])
    if not chemin_modele_vosk(code).is_dir():
        signaler(f"Téléchargement de la reconnaissance vocale en {nom(code)}…")
        telecharger_vosk(dossier_vosk(code), CATALOGUE[code]["vosk"])
    index = None
    for de, vers in _paires(code):
        cible = TRADUCTION / _nom_paquet(de, vers)
        if (cible / "model").is_dir():
            continue
        index = index or _index()
        signaler(f"Téléchargement de la traduction {nom(de)} → {nom(vers)}…")
        archive = TRADUCTION / f"{_nom_paquet(de, vers)}.argosmodel"
        TRADUCTION.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(_paquet(index, de, vers)["links"][0], headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r, open(archive, "wb") as f:
            shutil.copyfileobj(r, f)
        _extraire_paquet(archive, cible)
        archive.unlink()
    signaler(f"Le {nom(code)} est installé.")


def retirer(code):
    """Supprime une langue. Le français ne se retire jamais ; les modèles de traduction encore utiles à une
    autre langue installée (l'anglais sert de relais) sont conservés."""
    if code == "fr":
        raise ValueError("Le français est la langue d'Orion : il ne peut pas être retiré.")
    autres = [c for c in installees() if c not in ("fr", code)]
    utiles = {p for c in autres for p in _paires(c)}
    shutil.rmtree(DOSSIER / code, ignore_errors=True)
    for paire in _paires(code):
        if paire not in utiles:
            shutil.rmtree(TRADUCTION / _nom_paquet(*paire), ignore_errors=True)


def credits():
    """Attributions des modèles de traduction installés (première partie de leur README)."""
    textes = []
    for readme in sorted(TRADUCTION.glob("*/README.md")) if TRADUCTION.exists() else []:
        lignes = [l for l in readme.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        textes.append("\n".join(lignes[:8]))
    return textes


def occupe(code):
    """Espace disque utilisé par une langue (hors modèles partagés encore utiles à d'autres)."""
    total = sum(f.stat().st_size for f in (DOSSIER / code).rglob("*") if f.is_file()) if code != "fr" else 0
    return total


class Traducteur:
    """Traduit hors ligne avec les modèles installés ; charge chaque modèle une seule fois."""

    def __init__(self):
        self._cache = {}

    def _modele(self, de, vers):
        cle = (de, vers)
        if cle not in self._cache:
            import ctranslate2
            import sentencepiece
            dossier = TRADUCTION / _nom_paquet(de, vers)
            self._cache[cle] = (ctranslate2.Translator(str(dossier / "model"), device="cpu", inter_threads=1,
                                                       intra_threads=2),
                                sentencepiece.SentencePieceProcessor(model_file=str(dossier / "sentencepiece.model")))
        return self._cache[cle]

    def _directe(self, texte, de, vers):
        traducteur, sp = self._modele(de, vers)
        phrases = [p for p in re.split(r"(?<=[.!?;])\s+", texte.strip()) if p]
        jetons = [sp.encode(p, out_type=str) for p in phrases]
        resultats = traducteur.translate_batch(jetons, beam_size=2, max_decoding_length=256)
        return " ".join(sp.decode(r.hypotheses[0]) for r in resultats)

    def traduire(self, texte, de, vers):
        if de == vers or not texte:
            return texte
        if (TRADUCTION / _nom_paquet(de, vers) / "model").is_dir():
            return self._directe(texte, de, vers)
        return self._directe(self._directe(texte, de, "en"), "en", vers)  # relais par l'anglais
