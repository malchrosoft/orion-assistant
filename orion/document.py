# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Fiche PDF sur un sujet, au thème « Orion clair » : sobre, aéré, sources toujours citées en bas de page,
avec renvois numérotés dans le texte si on les demande."""
import datetime
import re
from pathlib import Path

from . import __version__, knowledge
from .config import UTILISATEUR
from .credits import _logo_orion
from .pdf import A4, Document

THEME = {"fond_bandeau": "#f3f8fa", "accent": "#0b7f99", "texte": "#1b2733", "doux": "#5b7683",
         "filet": "#d6e2e8"}


def _nom_fichier(titre):
    return re.sub(r"[^\w-]+", "-", titre, flags=re.UNICODE).strip("-")[:60] or "fiche"


def generer(fiche, renvois=False, dossier=None):
    """`fiche` : {titre, contenu, domaine, sources:[{titre, url, niveau, consulte}]}. Renvoie le chemin du PDF.
    Seules les sources réellement consultées sont citées (même règle que les réponses orales)."""
    sources = [s for s in fiche.get("sources", []) if s.get("consulte")]
    lectures = [s for s in fiche.get("lectures", []) if s.get("consulte")]
    dossier = Path(dossier or UTILISATEUR / "fiches")
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{_nom_fichier(fiche['titre'])}.pdf"
    doc = Document(titre=fiche["titre"], auteur="Orion")
    marge, largeur, th = 64, A4[0] - 128, THEME

    # Bandeau clair
    doc.rectangle(0, 0, A4[0], 96, th["fond_bandeau"])
    doc.ligne(0, 96, A4[0], 96, th["accent"], 1)
    _logo_orion(doc, A4[0] - marge - 44, 26, 44)
    doc.texte(marge, 44, fiche.get("domaine", "").upper(), 8.5, gras=True, couleur=th["accent"])
    doc.texte(marge, 72, fiche["titre"], 22, gras=True, couleur=th["texte"])

    # Corps
    contenu = fiche["contenu"]
    if renvois and sources:
        contenu += " " + " ".join(f"[{i}]" for i in range(1, len(sources) + 1))
    y = doc.paragraphe(marge, 140, contenu, largeur, 12, interligne=1.55, couleur=th["texte"])
    if fiche.get("avertissement"):
        y = doc.paragraphe(marge, y + 10, fiche["avertissement"], largeur, 9.5, couleur="#b26a00")

    # Sources en bas de page (toujours), puis lectures du domaine, qui ne sont pas des preuves
    def bloc(y, titre, liste, numeroter):
        doc.texte(marge, y, titre, 9, gras=True, couleur=th["doux"])
        y += 16
        for i, s in enumerate(liste, 1):
            prefixe = f"[{i}] " if numeroter else "• "
            doc.texte(marge, y, f"{prefixe}{s['titre']}"[:110], 8.5, couleur=th["texte"])
            doc.texte(marge + 16, y + 11, s["url"][:100], 8, couleur=th["accent"])
            doc.lien(marge + 16, y + 4, doc.largeur_texte(s["url"][:100], 8), 10, s["url"])
            y += 26
        return y

    hauteur = 26 * max(1, len(sources)) + 22 + (26 * len(lectures) + 30 if lectures else 0)
    y = A4[1] - 50 - hauteur
    doc.ligne(marge, y - 14, marge + 120, y - 14, th["filet"], 0.8)
    if sources:
        y = bloc(y, "Sources", sources, True)
    else:
        doc.texte(marge, y, "Sources", 9, gras=True, couleur=th["doux"])
        doc.texte(marge, y + 16, "Aucune source propre à cette fiche n'a été vérifiée.", 8.5, couleur=th["doux"])
        y += 42
    if lectures:
        bloc(y + 6, "Pour aller plus loin", lectures, False)
    doc.texte(marge, A4[1] - 28, f"Fiche créée par Orion {__version__} le {datetime.date.today():%d/%m/%Y}", 7.5,
              couleur=th["doux"])
    doc.enregistrer(str(chemin))
    return chemin


def fiche_locale(sujet):
    return knowledge.chercher(sujet)
