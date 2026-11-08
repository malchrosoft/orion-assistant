# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Petits utilitaires de normalisation du français."""
import re
import unicodedata


def sans_accents(t: str) -> str:
    """Minuscules sans accents, en gardant tous les alphabets (cyrillique, arabe, chinois…)."""
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9,.\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_VALEURS = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
            "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
            "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40,
            "cinquante": 50, "soixante": 60, "cent": 100, "cents": 100}


def chiffres(t: str) -> str:
    """« psaume quatre vingt trois dix huit » → « psaume 83 18 » (la reconnaissance vocale écrit en lettres).
    Deux nombres qui se suivent sont séparés quand le second ne peut pas compléter le premier."""
    sortie, courant = [], None
    for mot in t.split():
        v = _VALEURS.get(mot)
        if v is None:
            if mot == "et" and courant is not None:
                continue
            if courant is not None:
                sortie.append(str(courant))
                courant = None
            sortie.append(mot)
        elif courant is None:
            courant = v
        elif v == 100:
            courant = max(courant, 1) * 100
        elif v == 20 and courant % 100 == 4:
            courant += 76  # quatre-vingt
        elif (courant % 100 in (60, 80) and v < 20) or (courant % 10 == 0 and courant % 100 >= 20 and v < 10) \
                or (courant % 100 == 0 and courant >= 100 and v < 100) or (courant % 100 == 10 and 7 <= v <= 9):
            courant += v
        else:
            sortie.append(str(courant))
            courant = v
    if courant is not None:
        sortie.append(str(courant))
    return " ".join(sortie)
