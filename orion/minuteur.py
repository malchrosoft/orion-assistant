# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Compte à rebours interne à Orion : durée comprise à la voix, affichage sur l'hologramme, 5 bips à la fin."""
import re

UNITES = {"heure": 3600, "h": 3600, "minute": 60, "min": 60, "seconde": 1, "sec": 1, "s": 1}


def duree(t):
    """Phrase normalisée, nombres en chiffres (« 1 heure et quart », « 2 minutes 30 ») → secondes, ou None."""
    total, derniere = 0, None
    for nombre, unite in re.findall(r"(\d+)\s*(heures?|h|minutes?|min|secondes?|sec|s)\b", t):
        derniere = UNITES[unite.rstrip("s") if unite not in ("s", "h") else unite]
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
