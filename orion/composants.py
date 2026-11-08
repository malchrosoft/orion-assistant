# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Composants facultatifs qu'Orion installe lui-même : voix naturelle (Piper) et conversation (llama.cpp)."""
from . import conversation, piper

MODULES = {"voix": piper, "conversation": conversation}
LIBELLES = {"voix": "une voix plus naturelle", "conversation": "de quoi discuter librement"}


def manquants(cfg):
    liste = []
    cle_voix = cfg.get("voix_piper") or "siwis"
    if not piper.installee(cle_voix):
        liste.append(("voix", cle_voix))
    if not conversation.installe(conversation.choix(cfg)):
        liste.append(("conversation", conversation.choix(cfg)))
    return liste


def estimer(composants):
    return [ligne for genre, cle in composants for ligne in MODULES[genre].estimer(cle)]


def installer(cfg, composants, signaler=print):
    """Installe dans l'ordre et met la configuration à jour (voix et modèle choisis)."""
    from .config import sauver
    for genre, cle in composants:
        MODULES[genre].installer(cle, signaler)
        if genre == "voix" and not cfg.get("voix_piper"):
            cfg.update(voix_piper=cle, genre=piper.VOIX[cle]["genre"])
        if genre == "conversation":
            cfg["conversation"] = {**cfg.get("conversation", {}), "modele": cle}
    sauver(cfg)
