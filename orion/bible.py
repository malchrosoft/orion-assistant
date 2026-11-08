# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Questions bibliques : base de connaissance externe = JW.org, wol.jw.org (Bibliothèque en ligne
Watchtower) et l'application JW Library.

Orion ne cite pas cette source spontanément, mais la donne dès qu'on lui demande d'où viennent ses
informations (voir Cerveau.SOURCE_BIBLIQUE). Il n'extrait pas le contenu des sites : il ouvre la recherche
wol.jw.org ou le verset (lien jw.org/finder, ouvert par JW Library s'il est installé), conformément
aux conditions d'utilisation de JW.org qui excluent la collecte automatisée.
"""
import datetime
import re
import urllib.parse

from .texte import chiffres, normaliser

# Ordre canonique : l'index + 1 donne le numéro de livre utilisé par jw.org/finder (BBCCCVVV)
LIVRES = ["genese", "exode", "levitique", "nombres", "deuteronome", "josue", "juges", "ruth",
          "1 samuel", "2 samuel", "1 rois", "2 rois", "1 chroniques", "2 chroniques", "esdras", "nehemie",
          "esther", "job", "psaumes", "proverbes", "ecclesiaste", "chant de salomon", "isaie", "jeremie",
          "lamentations", "ezechiel", "daniel", "osee", "joel", "amos", "abdias", "jonas", "michee", "nahum",
          "habacuc", "sophonie", "aggee", "zacharie", "malachie", "matthieu", "marc", "luc", "jean", "actes",
          "romains", "1 corinthiens", "2 corinthiens", "galates", "ephesiens", "philippiens", "colossiens",
          "1 thessaloniciens", "2 thessaloniciens", "1 timothee", "2 timothee", "tite", "philemon", "hebreux",
          "jacques", "1 pierre", "2 pierre", "1 jean", "2 jean", "3 jean", "jude", "revelation"]
ALIAS = {"psaume": "psaumes", "cantique des cantiques": "chant de salomon", "apocalypse": "revelation",
         "actes des apotres": "actes", "proverbe": "proverbes"}
ORDINAUX = {"premier": "1", "premiere": "1", "deuxieme": "2", "second": "2", "seconde": "2", "troisieme": "3"}

# Pas de prénoms courants (Pierre, Marie, Paul…) : ce sont aussi ceux de la famille
THEMES = (r"\b(bible|biblique|jehovah|jesus|christ|dieu|apotres?|evangiles?|prophetes?|prophetie|"
          r"versets?|psaumes?|moise|abraham|noe|deluge|resurrection|armageddon|satan|diable|"
          r"testament|ecritures|saintes ecritures)\b")


WOL = "https://wol.jw.org/fr/wol"

# Vocabulaire de la Bibliothèque en ligne (wol.jw.org) → page datée correspondante.
# « jour » : page d'accueil du jour (texte du jour) ; « semaine » : programme des réunions de la semaine.
RUBRIQUES = [
    (r"texte du jour|verset du jour|examinons les ecritures|ecritures chaque jour|texte quotidien|"
     r"texte (de demain|d hier|d aujourd hui)", "jour"),
    (r"reunions? (de |du |de la )?(semaine|week end|weekend|milieu de semaine|jeudi|dimanche)|vie et ministere|vie chretienne et ministere|cahier( d activites| de reunion)?|"
     r"joyaux|perles spirituelles|applique toi au ministere|etude biblique de l assemblee|"
     r"tour de garde( d etude)?|etude de la tour de garde|discours public|"
     r"lecture biblique de la semaine|programme de la semaine|cantiques? de la semaine", "semaine"),
]


def rubrique(t):
    """(« jour » | « semaine », date visée) si la phrase utilise le vocabulaire de wol.jw.org, sinon None."""
    for motif, genre in RUBRIQUES:
        if re.search(rf"\b({motif})\b", t):
            d = datetime.date.today()
            if re.search(r"\bdemain\b", t):
                d += datetime.timedelta(days=1)
            elif re.search(r"\bhier\b", t):
                d -= datetime.timedelta(days=1)
            elif re.search(r"\bsemaine (prochaine|suivante)\b", t):
                d += datetime.timedelta(weeks=1)
            elif re.search(r"\bsemaine (derniere|passee|precedente)\b", t):
                d -= datetime.timedelta(weeks=1)
            return genre, d
    return None


def est_biblique(t):
    return bool(re.search(THEMES, t)) or rubrique(t) is not None or reference(chiffres(t)) is not None


def reference(t):
    """« jean 3 16 », « premier jean 4 8 », « psaume 83 18 » → code finder BBCCCVVV, ou None."""
    for mot, chiffre in ORDINAUX.items():
        t = re.sub(rf"\b{mot}\b( livre de| epitre de)?", chiffre, t)
    for alias, livre in ALIAS.items():
        t = re.sub(rf"\b{alias}\b", livre, t)
    for i in sorted(range(len(LIVRES)), key=lambda i: -len(LIVRES[i])):
        m = re.search(rf"\b{LIVRES[i]}\s+(?:chapitre\s+)?(\d+)\s*(?:verset\s+|[:.,]\s*)?(\d+)?", t)
        if m:
            return f"{i + 1:02d}{int(m.group(1)):03d}{int(m.group(2) or 1):03d}"
    return None


def lien(question):
    """Lien à ouvrir : rubrique datée, verset cité, sinon recherche dans la Bibliothèque en ligne."""
    r = rubrique(normaliser(question))
    if r:
        genre, d = r
        if genre == "jour":
            return f"{WOL}/h/r30/lp-f/{d.year}/{d.month}/{d.day}"
        annee, semaine, _ = d.isocalendar()
        return f"{WOL}/meetings/r30/lp-f/{annee}/{semaine}"
    code = reference(chiffres(normaliser(question)))
    if code:
        return f"https://www.jw.org/finder?wtlocale=F&bible={code}"
    return "https://wol.jw.org/fr/wol/s/r30/lp-f?q=" + urllib.parse.quote(question)
