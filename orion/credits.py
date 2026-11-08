# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Crédits : énoncés à voix haute selon la question, ou générés en PDF propre avec les logos."""
import datetime
import json
from pathlib import Path

from . import __version__
from .config import DATA, UTILISATEUR
from .pdf import A4, Document
from .texte import normaliser

CREDITS = DATA / "credits.json"
LOGOS = DATA / "logos"

# Logo d'Orion dessiné en vecteurs (même tracé que logos/orion.svg) : remplacé par logos/orion.png s'il existe
ETOILES = [(70, 52, 5), (118, 57, 4), (100, 40, 2.5), (90, 100, 3.2), (100, 102, 3.2), (110, 104, 3.2),
           (76, 138, 3.5), (126, 134, 5)]
LIENS = [(0, 1), (0, 3), (1, 5), (3, 4), (4, 5), (3, 6), (5, 7), (0, 2), (2, 1)]


def donnees():
    return json.loads(CREDITS.read_text(encoding="utf-8"))


def enoncer(question):
    """Réponse orale : le composant précis si la question le vise, sinon un résumé."""
    d, t = donnees(), normaliser(question)
    for c in d["composants"]:
        if any(m in t.split() for m in c["motscles"].split() if len(m) > 3):
            return (f"Pour {c['role']}, j'utilise {c['nom']}, réalisé par {c['auteurs']}, sous licence "
                    f"{c['licence']}.")
    p = d["projet"]
    principaux = ", ".join(f"{c['nom']} pour {c['role']}" for c in d["composants"][2:5])
    return (f"Mon auteur est {p['auteur']}, de {p['editeur']}. Je m'appuie notamment sur {principaux}. "
            "Demande-moi un composant précis, ou dis « génère les crédits en PDF » pour avoir la liste complète.")


def _logo_orion(doc, x, y, taille):
    png = LOGOS / "orion.png"
    if png.exists():
        doc.image_png(str(png), x, y, taille)
        return
    k = taille / 200
    doc.rectangle(x, y, taille, taille, "#05090d")
    doc.cercle(x + 100 * k, y + 100 * k, 82 * k, "#29e0ff", epaisseur=1.4)
    for i, j in LIENS:
        (x1, y1, _), (x2, y2, _) = ETOILES[i], ETOILES[j]
        doc.ligne(x + x1 * k, y + y1 * k, x + x2 * k, y + y2 * k, "#29e0ff", 0.6, pointille=True)
    for ex, ey, r in ETOILES:
        doc.cercle(x + ex * k, y + ey * k, r * k, "#9ffcff", plein=True)


def generer_pdf(chemin=None):
    """Crée le PDF des crédits et renvoie son chemin."""
    d = donnees()
    p = d["projet"]
    chemin = Path(chemin or UTILISATEUR / "Orion-credits.pdf")
    doc = Document(titre=f"Crédits — {p['nom']} {__version__}", auteur=p["auteur"])
    marge, largeur = 56, A4[0] - 112

    def entete():
        doc.rectangle(0, 0, A4[0], 118, "#05090d")
        _logo_orion(doc, marge, 26, 66)
        doc.texte(marge + 84, 58, "Crédits", 26, gras=True, couleur="#ffffff")
        doc.texte(marge + 84, 80, f"{p['nom']} {__version__} — assistant vocal familial, léger et hors ligne", 10,
                  couleur="#9ffcff")
        doc.image_png(str(LOGOS / "malchrosoft.png"), A4[0] - marge - 52, 30, 52)
        doc.ligne(0, 118, A4[0], 118, "#29e0ff", 1.2)

    def pied(numero):
        doc.ligne(marge, A4[1] - 46, A4[0] - marge, A4[1] - 46, "#d6e2e8", 0.5)
        doc.texte(marge, A4[1] - 30, f"© {p['annee']} {p['auteur']} · {p['editeur']} · licence {p['licence']}", 8,
                  couleur="#5b7683")
        doc.texte(A4[0] - marge - 40, A4[1] - 30, f"page {numero}", 8, couleur="#5b7683")

    page = 1
    entete()
    y = 152
    y = doc.paragraphe(marge, y, f"{p['nom']} a été conçu et écrit par {p['auteur']} ({p['editeur']}). Il repose sur "
                                 "le travail des projets ci-dessous, chacun sous sa propre licence : merci à leurs "
                                 "auteurs.", largeur, 10.5, couleur="#1b2733")
    doc.texte(marge, y + 4, p["site"], 9, couleur="#0b7f99")
    doc.lien(marge, y - 6, doc.largeur_texte(p["site"], 9), 12, p["site"])
    y += 30
    for c in d["composants"]:
        hauteur = 74
        if y + hauteur > A4[1] - 70:
            pied(page)
            doc.nouvelle_page()
            page += 1
            entete()
            y = 152
        doc.rectangle(marge, y - 12, 3, hauteur - 14, "#29e0ff")
        doc.texte(marge + 14, y, c["nom"], 11.5, gras=True)
        doc.texte(A4[0] - marge - doc.largeur_texte(c["licence"], 8.5) - 4, y, c["licence"], 8.5, couleur="#0b7f99")
        y2 = doc.paragraphe(marge + 14, y + 15, f"Rôle : {c['role']}.", largeur - 14, 9.5, couleur="#33444f")
        y2 = doc.paragraphe(marge + 14, y2, f"Auteurs : {c['auteurs']}.", largeur - 14, 9.5, couleur="#33444f")
        doc.texte(marge + 14, y2, c["url"], 8.5, couleur="#0b7f99")
        doc.lien(marge + 14, y2 - 7, doc.largeur_texte(c["url"], 8.5), 11, c["url"])
        y = y2 + 26
    y += 4
    doc.paragraphe(marge, y, f"Document généré par {p['nom']} le {datetime.date.today().strftime('%d/%m/%Y')}. "
                             "Le détail des licences figure dans THIRD_PARTY_NOTICES.md.", largeur, 8.5,
                   couleur="#5b7683")
    pied(page)
    doc.enregistrer(str(chemin))
    return chemin
