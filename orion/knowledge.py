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

from .config import DATA
from .texte import normaliser

BASE = DATA / "savoir.db"
SOURCE = DATA / "savoir.json"         # savoir livré avec Orion
REFERENCES = DATA / "references.json"  # références livrées, par domaine et par fiche
APPRIS = DATA / "appris.json"          # ce que l'utilisateur ajoute (survit aux reconstructions)

NIVEAUX = {3: "référence solide", 2: "ouvrage reconnu", 1: "source secondaire", 0: "source internet non vérifiée"}

# Mots trop fréquents qui polluent la recherche
VIDES = set("c est quoi qu ce que un une le la les des de du d l a au aux et en sur pour comment "
            "explique moi dis parle peux tu me sais connais definition definis signifie veut dire "
            "orion s il te plait quel quelle quels quelles".split())


def _lire(chemin):
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else []


def toutes_les_fiches():
    return _lire(SOURCE) + _lire(APPRIS)


def construire():
    """(Re)crée la base à partir des fichiers JSON."""
    BASE.unlink(missing_ok=True)
    fiches = toutes_les_fiches()
    refs = json.loads(REFERENCES.read_text(encoding="utf-8")) if REFERENCES.exists() else {}
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
        ligne = db.execute("SELECT rowid, titre, contenu, domaine FROM fiches WHERE fiches MATCH ? "
                           "ORDER BY bm25(fiches, 0, 0, 0, 0, 1) LIMIT 1",
                           (f"recherche : ({requete})",)).fetchone()
        if not ligne:
            return None
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
