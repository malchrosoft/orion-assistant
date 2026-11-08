# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Façon dont Orion se présente : neutre par défaut, accordée au féminin ou au masculin si l'on choisit
une voix correspondante. Les tournures neutres évitent tout accord (« Je m'appelle Orion », pas
« ton assistant·e »)."""
import random

GENRES = {"neutre": "neutre (simplement « Orion »)", "feminin": "féminin", "masculin": "masculin"}

# Prénoms de voix système courants, quand le moteur ne précise pas le genre (SAPI, macOS, eSpeak)
VOIX_FEMININES = ("hortense", "julie", "amelie", "amélie", "audrey", "aurelie", "marie", "virginie", "denise",
                  "zira", "hazel", "susan", "samantha", "victoria", "karen", "moira", "tessa", "fiona",
                  "helena", "monica", "paulina", "alice", "anna", "sara", "joana", "female", "femme")
VOIX_MASCULINES = ("thomas", "paul", "nicolas", "daniel", "david", "mark", "george", "alex", "fred", "jorge",
                   "diego", "luca", "yannick", "male", "homme")


def genre_de_voix(nom, genre_moteur=None):
    """« feminin », « masculin » ou None si on ne peut pas le savoir."""
    g = (genre_moteur or "").lower()
    if g in ("female", "feminine", "femme"):
        return "feminin"
    if g in ("male", "masculine", "homme"):
        return "masculin"
    n = nom.lower()
    if any(p in n for p in VOIX_FEMININES):
        return "feminin"
    if any(p in n for p in VOIX_MASCULINES):
        return "masculin"
    return None


def accord(cfg, neutre, feminin, masculin):
    return {"feminin": feminin, "masculin": masculin}.get(cfg.get("genre", "neutre"), neutre)


def salutation(cfg):
    """Courte, pour le démarrage."""
    return random.choice([f"Bonjour, je m'appelle {cfg['nom']}.", f"Bonjour ! Ici {cfg['nom']}.",
                          f"Bonjour, c'est {cfg['nom']}."])


def presentation(cfg):
    """Réponse à « qui es-tu ? »."""
    nom = cfg["nom"]
    role = accord(cfg, f"Je m'appelle {nom}, et je suis là pour toute la famille",
                  f"Je m'appelle {nom}, ton assistante pour toute la famille",
                  f"Je m'appelle {nom}, ton assistant pour toute la famille")
    return (f"{role}. Je reconnais chacun à sa voix, je lance la musique, je calcule, et je réponds sur les "
            "maths, la mécanique, l'électronique et le bâtiment. Si je ne sais pas, je te demande avant de "
            "chercher ailleurs.")
