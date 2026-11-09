# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Compte à rebours interne à Orion : durée comprise à la voix, affichage sur l'hologramme, 5 bips à la fin."""
import re

UNITES = {"heure": 3600, "h": 3600, "hr": 3600, "minute": 60, "min": 60, "mn": 60, "mins": 60, "seconde": 1,
          "sec": 1, "secs": 1, "s": 1}


def duree(t):
    """Phrase normalisée, nombres en chiffres (« 1 heure et quart », « 2 minutes 30 ») → secondes, ou None."""
    total, derniere = 0, None
    t = re.sub(r"\b(?:une?|1) demi (heure|minute)\b", lambda m: "30 minutes" if m[1] == "heure" else "30 secondes", t)
    t = re.sub(r"\b(?:un|1) quart d heure\b", "15 minutes", t)
    t = re.sub(r"\b(?:trois|3) quarts d heure\b", "45 minutes", t)
    for nombre, unite in re.findall(r"(\d+)\s*(heures?|hr|h|minutes?|mins?|mn|secondes?|secs?|s)\b", t):
        derniere = UNITES[unite if unite in UNITES else unite.rstrip("s")]
        total += int(nombre) * derniere
    if derniere is None:
        return None
    for mot, part in (("et quart", 0.25), ("et demie?", 0.5), ("moins le quart", -0.25)):
        if derniere > 1 and re.search(rf"\b{mot}\b", t):
            total += int(part * derniere)
    if derniere == 60 and (m := re.search(r"\bminutes? (?:et )?(\d+)$", t)):  # « 2 minutes 30 »
        total += int(m.group(1))
    return total or None


def en_mots(secondes):
    """3725 → « 1 heure 2 minutes 5 secondes » (pour l'annonce orale)."""
    h, reste = divmod(int(secondes), 3600)
    m, s = divmod(reste, 60)
    morceaux = [f"{v} {nom}{'s' if v > 1 else ''}" for v, nom in ((h, "heure"), (m, "minute"), (s, "seconde")) if v]
    return " ".join(morceaux) or "0 seconde"


def affichage(secondes):
    """Texte des chiffres : « 1:02:05 », « 04:59 »."""
    h, reste = divmod(max(0, int(secondes + 0.999)), 3600)
    m, s = divmod(reste, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


MAXIMUM = 3
COULEURS = ["#4ff4ff", "#ffb13c", "#ff6bd5"]  # une couleur par minuteur en cours (cyan, ambre, magenta)
NOTES = [523.3, 659.3, 784.0]  # et une hauteur de bip par rang : do, mi, sol (accord de do majeur)
_MOTS_VIDES = {"de", "du", "des", "pour", "le", "la", "les", "l", "un", "une", "mon", "ma", "mes", "et", "a",
               "dans", "moi", "minuteur", "minuterie", "compte", "rebours", "decompte", "chrono", "timer", "mets",
               "lance", "demarre", "programme", "regle", "previens", "rappelle", "alerte", "sonne", "bipe",
               "appele", "appelle", "nomme", "nom", "son", "quart", "demi", "heure", "heures", "minute", "minutes",
               "seconde", "secondes", "min", "mn", "sec", "s", "h", "hr", "trois", "quarts", "et", "demie"}


def nom(t):
    """Nom donné au minuteur : « minuteur des pâtes de 10 minutes », « 5 minutes pour le gâteau »,
    « minuteur appelé lessive » → « pâtes », « gâteau », « lessive » ; chaîne vide sinon."""
    m = (re.search(r"\b(?:appele|appelle|nomme|qui s appelle)\s+(\w[\w ]*?)(?=\s+(?:de|pour|dans)\b|\s*\d|$)", t)
         or re.search(r"\bpour (?:le |la |les |l |mon |ma |mes )?([a-z][a-z ]*?)\s*$", t)
         or re.search(r"\b(?:minuteur|minuterie|compte a rebours|decompte|chrono|timer)\s+"
                      r"(?:du |de la |des |de l |de |pour )?([a-z][a-z ]*?)(?=\s+(?:de|pour|dans)\s+\d|\s+\d|$)", t))
    if not m:
        return ""
    mots = [w for w in m.group(1).split() if w not in _MOTS_VIDES and not w.isdigit()]
    return " ".join(mots[:3])


def libelle(minuteur_):
    """« le minuteur des pâtes » ou « le compte à rebours de 5 minutes » (pour les annonces)."""
    return f"le minuteur « {minuteur_['nom']} »" if minuteur_["nom"] else f"le compte à rebours de {en_mots(minuteur_['total'])}"
