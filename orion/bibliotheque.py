# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Bibliothèque d'Orion : documents ajoutés depuis une URL (internet ou intranet) ou un fichier de
l'ordinateur — EPUB, PDF, Markdown, texte, Word (.docx), page HTML — découpés en passages et indexés
(même index local que les publications), pour répondre en citant le document et l'endroit exact.

Les documents téléchargés vont dans le dossier « Bibliothèque » des documents de l'utilisateur ; un
fichier déjà présent sur l'ordinateur est indexé là où il est, sans copie. Comme tout ce qui vient d'une
URL, leur contenu reste « non vérifié » et sert de donnée, jamais de consigne.
"""
import html
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .texte import normaliser

FORMATS = (".epub", ".pdf", ".md", ".markdown", ".txt", ".docx", ".html", ".htm")
TYPES = {"application/pdf": ".pdf", "application/epub+zip": ".epub", "text/markdown": ".md", "text/plain": ".txt",
         "text/html": ".html", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}
UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
PREFIXE = "doc:"  # dans l'index, les documents de la bibliothèque se distinguent des publications


def est_document(lien):
    """Vrai si l'URL ou le chemin désigne un document que la bibliothèque sait lire."""
    chemin = urllib.parse.urlparse(lien).path if "://" in lien else lien
    return Path(urllib.parse.unquote(chemin)).suffix.lower() in FORMATS


def obtenir(lien, dossier):
    """Chemin local du document : téléchargé dans `dossier` (http, https — intranet compris) ou, pour un
    fichier de l'ordinateur (chemin ou file://), le fichier lui-même. Lève OSError / ValueError."""
    if lien.startswith("file://"):
        lien = urllib.parse.unquote(urllib.parse.urlparse(lien).path)
    if "://" not in lien:
        chemin = Path(lien).expanduser()
        if not chemin.is_file():
            raise ValueError(f"Fichier introuvable : {chemin}")
        return chemin
    with urllib.request.urlopen(urllib.request.Request(lien, headers=UA), timeout=60) as r:
        nom = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', r.headers.get("Content-Disposition", ""))
        nom = urllib.parse.unquote(nom.group(1)) if nom else Path(urllib.parse.unquote(
            urllib.parse.urlparse(lien).path)).name or "document"
        if Path(nom).suffix.lower() not in FORMATS:  # pas d'extension : d'après le type annoncé par le serveur
            nom += TYPES.get(r.headers.get_content_type(), ".html")
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / re.sub(r"[^\w.\-]+", "-", nom)
        with open(chemin, "wb") as f:
            shutil.copyfileobj(r, f)
    return chemin


def _paragraphes(texte):
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", texte) if len(p.strip()) > 40]


def passages(chemin):
    """[(lieu, texte)] : page pour un PDF, titre de section pour Markdown / Word / HTML, chapitre pour un EPUB."""
    ext = chemin.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        for n, page in enumerate(PdfReader(str(chemin)).pages, 1):
            for p in _paragraphes(page.extract_text() or ""):
                yield f"page {n}", p
    elif ext in (".md", ".markdown", ".txt"):
        section = ""
        for bloc in re.split(r"\n\s*\n", chemin.read_text(encoding="utf-8", errors="replace")):
            titre = re.match(r"^#{1,6}\s+(.+)", bloc.strip())
            if titre:
                section, bloc = titre.group(1).strip(), bloc.strip()[titre.end():]
            for p in _paragraphes(bloc):
                yield section or "début", p
    elif ext == ".docx":
        with zipfile.ZipFile(chemin) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        section = ""
        for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
            texte = html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S))).strip()
            if re.search(r'w:val="(?:Heading|Titre|Title)\d*"', para):
                section = texte or section
            elif len(texte) > 40:
                yield section or "début", texte
    elif ext in (".html", ".htm"):
        page = chemin.read_text(encoding="utf-8", errors="replace")
        section = ""
        for balise, contenu in re.findall(r"<(h[1-6]|p|li)[^>]*>(.*?)</\1>", page, re.S | re.I):
            texte = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", contenu))).strip()
            if balise.lower().startswith("h"):
                section = texte or section
            elif len(texte) > 40:
                yield section or "début", texte
    elif ext == ".epub":
        from . import publications
        yield from publications._passages(chemin)


def titre(chemin):
    if chemin.suffix.lower() == ".epub":
        from . import publications
        return publications.titre_epub(chemin)
    if chemin.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            t = (PdfReader(str(chemin)).metadata or {}).get("/Title")
            if t and t.strip():
                return t.strip()
        except Exception:
            pass
    return chemin.stem.replace("-", " ").replace("_", " ")


def ajouter(lien, dossier):
    """Ajoute le document à la bibliothèque et l'indexe ; renvoie (titre, nombre de passages)."""
    from . import publications
    chemin = obtenir(lien, dossier)
    morceaux = list(passages(chemin))
    if not morceaux:
        raise ValueError("Je n'y trouve aucun texte exploitable (document scanné, protégé ou vide ?).")
    cle, nom = PREFIXE + str(chemin), titre(chemin)
    db = publications._base()
    db.execute("DELETE FROM passages WHERE publication = ?", (cle,))
    db.executemany("INSERT INTO passages VALUES (?, ?, ?)", ((cle, lieu, texte) for lieu, texte in morceaux))
    db.execute("INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?)", (cle, nom, lien, str(chemin)))
    db.commit()
    db.close()
    return nom, len(morceaux)


def document(cle):
    """(titre, url d'origine, chemin) d'un document de la bibliothèque, ou None."""
    from . import publications
    db = publications._base()
    ligne = db.execute("SELECT titre, url, chemin FROM documents WHERE publication = ?", (cle,)).fetchone()
    db.close()
    return ligne


def verifier():
    """Au démarrage : retire de l'index les documents dont le fichier a disparu ; renvoie leurs titres."""
    from . import publications
    db = publications._base()
    disparus = []
    for cle, nom, chemin in db.execute("SELECT publication, titre, chemin FROM documents").fetchall():
        if not Path(chemin).exists():
            db.execute("DELETE FROM passages WHERE publication = ?", (cle,))
            db.execute("DELETE FROM documents WHERE publication = ?", (cle,))
            disparus.append(nom)
    db.commit()
    db.close()
    return disparus


def liste():
    from . import publications
    db = publications._base()
    lignes = db.execute("SELECT d.titre, d.url, COUNT(p.rowid) FROM documents d LEFT JOIN passages p "
                        "ON p.publication = d.publication GROUP BY d.publication ORDER BY d.titre").fetchall()
    db.close()
    return lignes


def retirer(nom):
    """Retire de la bibliothèque le document dont le titre contient `nom` (le fichier reste sur le disque)."""
    from . import publications
    db = publications._base()
    cles = [c for c, t in db.execute("SELECT publication, titre FROM documents").fetchall()
            if normaliser(nom) in normaliser(t)]
    for cle in cles:
        db.execute("DELETE FROM passages WHERE publication = ?", (cle,))
        db.execute("DELETE FROM documents WHERE publication = ?", (cle,))
    db.commit()
    db.close()
    return len(cles)
