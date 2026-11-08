# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Conversation libre, quand les règles et le savoir local n'ont pas de réponse — uniquement en local.

Orion installe lui-même, à la demande, le moteur llama.cpp (MIT, 12 à 24 Mo, lancé comme programme séparé)
et un modèle de langage ouvert (GGUF) dans son propre dossier : rien n'est installé dans le système et rien ne
sort de l'ordinateur. Le moteur démarre au premier besoin et s'arrête après quelques minutes d'inactivité
pour rendre la mémoire.
"""
import atexit
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile

from . import personnes
from .config import UTILISATEUR
from .persona import accord

DOSSIER = UTILISATEUR / "conversation"
UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
HISTORIQUE_MAX = 12          # messages gardés par personne pendant la session (contexte de la discussion)
ARRET_INACTIF_S = 600        # le moteur rend sa mémoire après 10 minutes sans conversation

LLAMA_VERSION = "b12195"     # version figée de llama.cpp (reproductible) ; archives CPU officielles
LLAMA_ARCHIVES = {("Darwin", "arm64"): "macos-arm64.tar.gz", ("Darwin", "x86_64"): "macos-x64.tar.gz",
                  ("Linux", "x86_64"): "ubuntu-x64.tar.gz", ("Linux", "aarch64"): "ubuntu-arm64.tar.gz",
                  ("Windows", "AMD64"): "win-cpu-x64.zip", ("Windows", "ARM64"): "win-cpu-arm64.zip"}

# Modèles proposés (licences vérifiées) ; le premier est le choix par défaut
MODELES = {
    "ministral-3b": {"nom": "Ministral 3 3B — très bon en français (Mistral AI)", "licence": "Apache 2.0",
                     "depot": "mistralai/Ministral-3-3B-Instruct-2512-GGUF",
                     "fichier": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf", "memoire_go": 3},
    "qwen3-1.7b": {"nom": "Qwen3 1.7B — plus léger", "licence": "Apache 2.0",
                   "depot": "Qwen/Qwen3-1.7B-GGUF", "fichier": "Qwen3-1.7B-Q8_0.gguf", "memoire_go": 2.2},
    "gemma3-1b": {"nom": "Gemma 3 1B — pour les très petites machines", "licence": "conditions d'utilisation Gemma",
                  "depot": "ggml-org/gemma-3-1b-it-GGUF", "fichier": "gemma-3-1b-it-Q4_K_M.gguf", "memoire_go": 1.2},
}
DEFAUT = "ministral-3b"


def choix(cfg):
    cle = cfg.get("conversation", {}).get("modele", DEFAUT)
    return cle if cle in MODELES else DEFAUT


# --- Installation ---------------------------------------------------------------------------------------------
def _archive_moteur():
    suffixe = LLAMA_ARCHIVES.get((platform.system(), platform.machine()))
    if not suffixe:
        raise RuntimeError("Le moteur de conversation n'existe pas pour ce système.")
    nom = f"llama-{LLAMA_VERSION}-bin-{suffixe}"
    return nom, f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_VERSION}/{nom}"


def executable():
    nom = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    trouves = list((DOSSIER / "moteur").rglob(nom)) if (DOSSIER / "moteur").exists() else []
    return trouves[0] if trouves else None


def fichier_modele(cle):
    return DOSSIER / "modeles" / MODELES[cle]["fichier"]


def _url_modele(cle):
    m = MODELES[cle]
    return f"https://huggingface.co/{m['depot']}/resolve/main/{m['fichier']}"


def installe(cle):
    return executable() is not None and fichier_modele(cle).exists()


def _taille(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=30) as r:
        return int(r.headers.get("Content-Length", 0))


def estimer(cle):
    lignes = []
    if executable() is None:
        lignes.append(("Moteur de conversation llama.cpp (une seule fois)", _taille(_archive_moteur()[1])))
    if not fichier_modele(cle).exists():
        lignes.append((f"Modèle {MODELES[cle]['nom']}", _taille(_url_modele(cle))))
    return lignes


def _telecharger(url, destination, signaler, libelle):
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_name(destination.name + ".partiel")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(partiel, "wb") as f:
        total, recu, dernier = int(r.headers.get("Content-Length", 0)), 0, 0
        while bloc := r.read(1 << 20):
            f.write(bloc)
            recu += len(bloc)
            if total and recu * 100 // total >= dernier + 5:
                dernier = recu * 100 // total
                signaler(f"{libelle} : {dernier} %")
    partiel.replace(destination)


def installer(cle, signaler=print):
    from . import espace
    from .config import charger
    cfg = charger()
    besoin = sum(o for _, o in estimer(cle))
    if not espace.place_pour(cfg, besoin):
        raise RuntimeError(f"Il faut {besoin / 1e9:.1f} Go : cela dépasserait la limite de "
                           f"{espace.limite(cfg) / 1e9:.1f} Go fixée dans les réglages d'Orion.")
    if executable() is None:
        nom, url = _archive_moteur()
        archive = DOSSIER / nom
        _telecharger(url, archive, signaler, "Moteur de conversation")
        cible = DOSSIER / "moteur"
        cible.mkdir(parents=True, exist_ok=True)
        if nom.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                for membre in z.namelist():
                    if not (cible / membre).resolve().is_relative_to(cible.resolve()):
                        raise ValueError(f"Archive suspecte : {membre}")
                z.extractall(cible)
        else:
            with tarfile.open(archive) as t:
                t.extractall(cible, filter="data")
        archive.unlink()
        executable().chmod(0o755)
    if not fichier_modele(cle).exists():
        _telecharger(_url_modele(cle), fichier_modele(cle), signaler, "Modèle de conversation")
    signaler(f"La conversation est prête ({MODELES[cle]['nom']}).")


def retirer(cle):
    fichier_modele(cle).unlink(missing_ok=True)
    if not any(fichier_modele(k).exists() for k in MODELES):
        shutil.rmtree(DOSSIER / "moteur", ignore_errors=True)


# --- Moteur local ---------------------------------------------------------------------------------------------
class Moteur:
    """llama-server lancé à la demande sur 127.0.0.1, arrêté après inactivité (et à la fermeture d'Orion)."""

    def __init__(self):
        self.proc, self.port, self.cle, self.dernier_usage = None, None, None, 0.0
        self.verrou = threading.Lock()
        atexit.register(self.arreter)
        threading.Thread(target=self._surveiller, daemon=True).start()

    def _surveiller(self):
        while True:
            time.sleep(30)
            if self.proc and time.time() - self.dernier_usage > ARRET_INACTIF_S:
                self.arreter()

    def arreter(self):
        with self.verrou:
            if self.proc:
                self.proc.terminate()
                self.proc = None

    def url(self, cle):
        """Démarre le moteur si besoin et renvoie son adresse (None si impossible)."""
        with self.verrou:
            self.dernier_usage = time.time()
            if self.proc and self.proc.poll() is None and self.cle == cle:
                return f"http://127.0.0.1:{self.port}"
            if self.proc:
                self.proc.terminate()
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                self.port = s.getsockname()[1]
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            self.proc = subprocess.Popen(
                [str(executable()), "-m", str(fichier_modele(cle)), "--host", "127.0.0.1", "--port", str(self.port),
                 "-c", "4096", "-t", str(max(1, (os.cpu_count() or 2) - 1)), "--jinja"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
            self.cle = cle
        adresse = f"http://127.0.0.1:{self.port}"
        for _ in range(120):  # chargement du modèle : quelques secondes à une minute selon la machine
            try:
                with urllib.request.urlopen(adresse + "/health", timeout=1) as r:
                    if r.status == 200:
                        return adresse
            except Exception:
                if self.proc.poll() is not None:
                    return None
                time.sleep(0.5)
        return None


MOTEUR = None


class Conversation:
    def __init__(self, cfg):
        self.cfg = cfg
        self.historiques = {}
        self.signaler = lambda message: None

    def local_disponible(self):
        return installe(choix(self.cfg))

    # --- Contexte -------------------------------------------------------------------------------------------
    def _systeme(self, locuteur):
        nom, connu = self.cfg["nom"], locuteur != "invité"
        p = personnes.fiche(locuteur) if connu else {}
        tutoie = p.get("tutoiement") is not False
        role = accord(self.cfg, "un assistant vocal familial (présente-toi simplement par ton nom)",
                      "une assistante vocale familiale", "un assistant vocal familial")
        lignes = [
            f"Tu es {nom}, {role}, sur un ordinateur de la maison. Tu parles français.",
            "Tes réponses sont dites à voix haute : une ou deux phrases courtes, simples et directes, sans "
            "liste, sans mise en forme, sans émoji, sans parenthèses. Pas d'emphase, de lyrisme ni de formule "
            "creuse (« Ah, », « Bien sûr ! », « Excellente question »).",
            "Tu peux discuter de tout, avec bienveillance et humour léger, en adaptant ton vocabulaire à "
            "l'interlocuteur. Pour un fait précis (date, chiffre, science, santé, droit), dis que tu peux vérifier "
            "dans une source si on te le demande, et n'invente jamais de source ni de chiffre.",
            "Si on te demande ce que tu sais faire : tu réponds aux questions de connaissance en consultant "
            "Wikipédia, tu affiches la météo, tu lis la musique, règles le volume, ouvres des applications et "
            "crées des fiches PDF. Il suffit de te le demander directement.",
            "Tu ne prétends pas avoir fait une action sur l'ordinateur : les commandes (musique, volume, "
            "applications) sont traitées ailleurs.",
            "N'invente jamais la signification d'un sigle ni une définition : si tu ne sais pas, dis-le. Tu ne "
            "peux rien noter, retenir ni enregistrer toi-même : propose de dire « retiens que… ».",
            "Tu n'as pas de vie personnelle : n'invente jamais ce que tu fais, lis, vois ou ressens, ni de souvenir "
            "commun. Réponds à ce qu'on te dit, sans relancer systématiquement par une question.",
            ("Tu tutoies toujours ton interlocuteur : n'emploie jamais « vous » pour t'adresser à lui."
             if tutoie else "Tu vouvoies toujours ton interlocuteur."),
            "N'accorde jamais au féminin ou au masculin ce qui concerne ton interlocuteur (pas « prête » ni "
            "« prêt ») : tourne la phrase autrement.",
            accord(self.cfg, "Parle de toi sans accord de genre (évite « ravi », « content », « prêt »).",
                   "Tu es de genre féminin : accorde au féminin ce qui te concerne (ravie, contente, prête).",
                   "Tu es de genre masculin : accorde au masculin ce qui te concerne (ravi, content, prêt)."),
        ]
        if connu:  # ces informations restent sur l'ordinateur (modèle local)
            lignes.append(f"Tu parles avec {locuteur}.")
            if p.get("age"):
                lignes.append(f"{locuteur} a environ {p['age']} ans.")
            if p.get("niveau"):
                lignes.append(f"{locuteur} est en {p['niveau']}.")
            humeur = personnes.humeur_recente(locuteur)
            if humeur:
                lignes.append(f"Récemment, {locuteur} se sentait {humeur}.")
            for s in p.get("souvenirs", [])[:10]:
                lignes.append(f"{locuteur} t'a demandé de retenir : {s['texte']}.")
        return "\n".join(lignes)

    # Exemples de ton (plus efficaces qu'une consigne sur un petit modèle)
    # Exemples sans sujet précis : un petit modèle recopie le thème des exemples dans ses réponses
    # (un exemple qui raconte un fait, « j'ai réussi mon contrôle », était repris comme un souvenir réel)
    EXEMPLES = [{"role": "user", "content": "Tu es là ?"},
                {"role": "assistant", "content": "Oui, je t'écoute."},
                {"role": "user", "content": "Merci pour ton aide."},
                {"role": "assistant", "content": "Avec plaisir."}]

    def _noter(self, locuteur, phrase, reponse):
        h = self.historiques.setdefault(locuteur, [])
        h += [{"role": "user", "content": phrase}, {"role": "assistant", "content": reponse}]
        self.historiques[locuteur] = h[-HISTORIQUE_MAX:]

    # --- Réponse --------------------------------------------------------------------------------------------
    def completer(self, consigne, texte, max_tokens=120):
        """Appel ponctuel au modèle local (sans historique ni personnalité), ou None s'il est absent."""
        global MOTEUR
        MOTEUR = MOTEUR or Moteur()
        adresse = MOTEUR.url(choix(self.cfg))
        if not adresse:
            return None
        corps = json.dumps({"messages": [{"role": "system", "content": consigne}, {"role": "user", "content": texte}],
                            "max_tokens": max_tokens, "temperature": 0.2,
                            "chat_template_kwargs": {"enable_thinking": False}}).encode()
        try:
            req = urllib.request.Request(adresse + "/v1/chat/completions", corps, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                texte = json.load(r)["choices"][0]["message"]["content"]
        except Exception:
            return None
        return re.sub(r"<think>.*?</think>", "", texte, flags=re.S).strip()

    def repondre_local(self, phrase, locuteur):
        global MOTEUR
        cle = choix(self.cfg)
        MOTEUR = MOTEUR or Moteur()
        if not (MOTEUR.proc and MOTEUR.proc.poll() is None and MOTEUR.cle == cle):
            self.signaler("Je réveille mon modèle de conversation…")
        adresse = MOTEUR.url(cle)
        self.signaler("")
        if not adresse:
            return None
        messages = ([{"role": "system", "content": self._systeme(locuteur)}] + self.EXEMPLES
                    + self.historiques.get(locuteur, []) + [{"role": "user", "content": phrase}])
        corps = json.dumps({"messages": messages, "max_tokens": 90, "temperature": 0.5,
                            "chat_template_kwargs": {"enable_thinking": False}}).encode()
        try:
            req = urllib.request.Request(adresse + "/v1/chat/completions", corps,
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                texte = json.load(r)["choices"][0]["message"]["content"]
        except Exception:
            return None
        texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.S).strip()  # Qwen3 : pas de réflexion lue
        texte = re.sub(r"[*_#`]+", "", texte)                                  # pas de mise en forme à l'oral
        texte = re.sub(r"\s+", " ", texte).strip()                              # pas de retours à la ligne
        texte = re.sub(r"^(?:(?:ah|oh|eh bien|bien sûr|absolument|excellente question|quelle (?:belle|bonne) "
                       r"question|bonne question)\s*[,!.…]+\s*)+", "", texte, flags=re.I)  # débuts creux
        texte = texte[:1].upper() + texte[1:]
        phrases = re.split(r"(?<=[.!?…])\s+", texte)
        texte = " ".join(phrases[:self.cfg.get("phrases_max", 2)])               # réponse brève à l'oral
        if texte:
            self._noter(locuteur, phrase, texte)
        return texte or None
