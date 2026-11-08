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


def _phonetique(mot: str) -> str:
    """Forme approximative à l'oreille : « au rions », « oh rion », « orions » → « orion »."""
    m = mot.replace("eau", "o").replace("au", "o").replace("oh", "o").replace("h", "")
    m = re.sub(r"(ions|ion|iont|ient|ien)$", "ion", m)
    return re.sub(r"[stxe]$", "", m) if len(m) > 4 else m


def _est_nom(mots, noms, apres_formule=False):
    """Vrai si ces mots (1 ou 2, collés) sonnent comme l'un des noms. Juste après « dis » ou « hey »,
    « aurions » ou « orient » sont bien le nom mal transcrit : on ne les écarte pas."""
    import difflib
    if len(mots) == 1 and mots[0] in _MOTS_COURANTS and not apres_formule:
        return False
    candidat = _phonetique("".join(mots))
    return any(difflib.SequenceMatcher(None, candidat, _phonetique(normaliser(n).replace(" ", ""))).ratio() >= 0.8
               for n in noms)


def est_echo(entendu: str, dit: str, seuil=0.6):
    """Vrai si ce que le micro a entendu ressemble à ce qu'Orion vient de dire (haut-parleurs sans casque).
    Comparaison mot à mot tolérante : la transcription de sa propre voix n'est jamais exacte."""
    import difflib
    mots = [m for m in normaliser(entendu).split() if len(m) > 1]
    reference = set(normaliser(dit).split())
    if not mots or not reference:
        return False
    proches = sum(1 for m in mots if m in reference or any(
        difflib.SequenceMatcher(None, m, r).ratio() >= 0.75 for r in reference if abs(len(r) - len(m)) <= 3))
    return proches / len(mots) >= seuil


def trouver_eveil(texte: str, noms, prefixes):
    """Formule d'éveil « hey Orion » / « dis Orion » (et ses transcriptions approximatives : « et orion »,
    « eh au rions »…) dans les premiers mots. Renvoie (trouvé, reste de la phrase après la formule)."""
    mots = normaliser(texte).split()
    for i, mot in enumerate(mots[:4]):
        if mot in prefixes:
            for largeur in (1, 2):
                if len(mots) > i + largeur - 1 and _est_nom(mots[i + 1:i + 1 + largeur], noms, True):
                    return True, " ".join(mots[i + 1 + largeur:])
        # formule et nom collés par la transcription : « dirions » = « dis Orion », « eorion »…
        for p in sorted(prefixes, key=len, reverse=True):
            if mot.startswith(p) and len(mot) > len(p) + 2 and _est_nom([mot[len(p):]], noms, True):
                return True, " ".join(mots[i + 1:])
    return False, normaliser(texte)


# Vrais mots proches de « Orion » qu'il ne faut pas prendre pour son nom
_MOTS_COURANTS = {"aurions", "aurient", "orient", "orients", "oriente", "orienter", "horion", "horions", "aurons"}


def trouver_nom(texte: str, noms, debut_seulement=True):
    """(trouvé, reste de la phrase sans le nom). Tolère les transcriptions approximatives de la
    reconnaissance vocale en comparant des formes phonétiques (un ou deux mots collés)."""
    import difflib
    mots = normaliser(texte).split()
    zone = range(min(len(mots), 5)) if debut_seulement else range(len(mots))
    cibles = [_phonetique(normaliser(n).replace(" ", "")) for n in noms]
    for i in zone:
        for largeur in (1, 2):
            if i + largeur > len(mots):
                continue
            if largeur == 1 and mots[i] in _MOTS_COURANTS:
                continue
            candidat = _phonetique("".join(mots[i:i + largeur]))
            if any(c and difflib.SequenceMatcher(None, candidat, c).ratio() >= 0.8 for c in cibles):
                return True, " ".join(mots[:i] + mots[i + largeur:])
    return False, normaliser(texte)


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
