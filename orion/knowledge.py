# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Mini-base de savoir locale : SQLite + recherche plein texte (FTS5), zéro dépendance.

Chaque fiche peut citer des références, classées selon la grille « shoulders of giants » :
  3 = norme / texte officiel / publication fondatrice (★★★)
  2 = ouvrage classique ouvert, implémentation de référence (★★)
  1 = article de vulgarisation renvoyant à une source primaire (★)
  0 = page web ajoutée à la demande, NON VÉRIFIÉE (toujours mise en doute)
"""
import datetime
import json
import sqlite3

from .config import DATA, DONNEES
from .texte import normaliser

BASE = DONNEES / "savoir.db"
SOURCE = DATA / "savoir.json"            # savoir livré avec Orion
REFERENCES_LIVREES = DATA / "references.json"
REFERENCES = DONNEES / "references.json"  # copie mise à jour par « verifier » (identique en développement)
APPRIS = DONNEES / "appris.json"          # ce que l'utilisateur ajoute (survit aux reconstructions)


def references():
    """Références vérifiées localement si elles existent, sinon celles livrées avec Orion."""
    return json.loads((REFERENCES if REFERENCES.exists() else REFERENCES_LIVREES).read_text(encoding="utf-8"))

NIVEAUX = {3: "référence solide", 2: "ouvrage reconnu", 1: "source secondaire", 0: "source internet non vérifiée"}

# Mots trop fréquents qui polluent la recherche
VIDES = set("c est quoi qu ce que un une le la les des de du d l a au aux et en sur pour comment "
            "explique moi dis parle peux tu me sais connais definition definis signifie veut dire "
            "orion s il te plait quel quelle quels quelles je tu il elle on nous vous ils elles me te se "
            "mon ma mes ton ta tes son sa ses suis es est sommes etes sont vais vas va vont ai as avons avez ont "
            "fait faire veux peux dois pas ne plus tres bien oui non merci alors donc mais ou car ca cela ceci "
            "y en lui leur qui quoi dont tout tous toute toutes".split())


def _couverture(mots, texte_fiche):
    """Part des mots de la question présents dans la fiche (préfixe de 5 lettres pour les mots longs)."""
    jetons = texte_fiche.split()
    trouves = sum(1 for m in mots if any(j == m or (len(m) >= 5 and j.startswith(m[:5])) for j in jetons))
    return trouves / len(mots)


def _lire(chemin):
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else []


def toutes_les_fiches():
    return _lire(SOURCE) + _lire(APPRIS)


def construire():
    """(Re)crée la base à partir des fichiers JSON."""
    BASE.unlink(missing_ok=True)
    fiches = toutes_les_fiches()
    refs = references()
    with sqlite3.connect(BASE) as db:
        db.execute("CREATE VIRTUAL TABLE fiches USING fts5(domaine, titre, motscles, contenu, recherche, "
                   "tokenize='unicode61 remove_diacritics 2')")
        db.execute("CREATE TABLE refs (fiche INTEGER, titre TEXT, url TEXT, niveau INTEGER, consulte TEXT, portee TEXT)")
        for f in fiches:
            rowid = db.execute("INSERT INTO fiches VALUES (?,?,?,?,?)",
                               (f["domaine"], f["titre"], f["motscles"], f["contenu"],
                                normaliser(f"{f['titre']} {f['titre']} {f['motscles']}"))).lastrowid
            # « fiche » : appuie précisément ce qui est dit ; « domaine » : lecture pour aller plus loin
            sources = [(s, "fiche") for s in f.get("sources", []) + refs.get("fiches", {}).get(f["titre"], [])] \
                + [(s, "domaine") for s in refs.get("domaines", {}).get(f["domaine"], [])]
            db.executemany("INSERT INTO refs VALUES (?,?,?,?,?,?)",
                           [(rowid, s["titre"], s["url"], s["niveau"], s.get("consulte"), portee)
                            for s, portee in sources])
    return len(fiches)


def chercher(question: str):
    """Renvoie {titre, contenu, domaine, sources:[…]} de la meilleure fiche, ou None."""
    if not BASE.exists():
        construire()
    mots = [m for m in normaliser(question).replace(",", " ").replace(".", " ").split()
            if m not in VIDES and len(m) > 1]
    if not mots:
        return None
    requete = " OR ".join(f'"{m}"*' for m in mots)
    with sqlite3.connect(BASE) as db:
        candidats = db.execute("SELECT rowid, titre, contenu, domaine, recherche FROM fiches WHERE fiches MATCH ? "
                               "ORDER BY bm25(fiches, 0, 0, 0, 0, 1) LIMIT 8",
                               (f"recherche : ({requete})",)).fetchall()
        # Une fiche ne répond que si elle couvre au moins la moitié des mots utiles de la question :
        # « je vais me coucher » ne doit pas tomber sur le Jeu de la vie parce que « vie » y figure.
        notes = [(c, _couverture(mots, c[4])) for c in candidats]
        notes = [(c, n) for c, n in notes if n >= 0.5]
        if not notes:
            return None
        ligne = max(notes, key=lambda cn: cn[1])[0]  # max() garde le premier ex aequo : l'ordre bm25
        sources = [dict(zip(("titre", "url", "niveau", "consulte", "portee"), r)) for r in
                   db.execute("SELECT titre, url, niveau, consulte, portee FROM refs WHERE fiche=? "
                              "ORDER BY portee = 'fiche' DESC, niveau DESC", (ligne[0],))]
    return {"titre": ligne[1], "contenu": ligne[2], "domaine": ligne[3], "sources": sources}


def ajouter(fiche):
    """Ajoute une fiche utilisateur (ex. apprise depuis une URL) et réindexe."""
    appris = _lire(APPRIS)
    appris = [f for f in appris if f["titre"] != fiche["titre"]] + [fiche]
    APPRIS.write_text(json.dumps(appris, ensure_ascii=False, indent=1), encoding="utf-8")
    construire()


def oublier(titre):
    APPRIS.write_text(json.dumps([f for f in _lire(APPRIS) if f["titre"] != titre],
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    construire()


def aujourdhui():
    return datetime.date.today().isoformat()


if __name__ == "__main__":
    print(f"{construire()} fiches indexées dans {BASE}")
