# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Document tiré d'une réponse d'Orion : Word (.docx), Markdown (.md), page web (.html) ou PDF.

Sans dépendance : le .docx est un fichier Office Open XML minimal (ECMA-376) écrit avec zipfile ;
le PDF passe par le générateur de fiches d'Orion (document.py).
"""
import datetime
import html
import re
import zipfile
from pathlib import Path

FORMATS = {"docx": r"\b(word|docx|doc)\b", "md": r"\b(markdown|md)\b", "html": r"\b(html|page web|web)\b",
           "pdf": r"\bpdf\b"}


def format_demande(t):
    """Format cité dans la phrase normalisée (PDF par défaut ; « rapport », « qualité pro » : PDF composé en LaTeX)."""
    format_ = next((f for f, motif in FORMATS.items() if re.search(motif, t)), "pdf")
    if format_ == "pdf" and re.search(r"\b(pro|professionnel(le)?|rapport|latex|qualite)\b", t):
        return "pdf_pro"
    return format_


def _nom(titre, extension):
    base = re.sub(r"[^\w-]+", "-", titre, flags=re.UNICODE).strip("-")[:60] or "document"
    return f"{base}.{extension}"


def _paragraphes(contenu):
    return [p.strip() for p in re.split(r"\n+", contenu) if p.strip()]


def _sources(doc):
    return [s for s in doc.get("sources", []) if s.get("consulte", True)]


def markdown(doc):
    lignes = [f"# {doc['titre']}", "", f"*Question : {doc['question']}*", ""] if doc.get("question") else \
        [f"# {doc['titre']}", ""]
    lignes += [p + "\n" for p in _paragraphes(doc["contenu"])]
    if _sources(doc):
        lignes += ["## Sources", ""] + [f"- [{s['titre']}]({s['url']})" if s.get("url") else f"- {s['titre']}"
                                         for s in _sources(doc)]
    lignes += ["", f"---\n*Préparé par Orion le {datetime.date.today():%d/%m/%Y}.*"]
    return "\n".join(lignes) + "\n"


def page_html(doc):
    e = html.escape
    corps = "".join(f"<p>{e(p)}</p>" for p in _paragraphes(doc["contenu"]))
    question = f"<p class='q'>Question : {e(doc['question'])}</p>" if doc.get("question") else ""
    sources = "".join(f"<li><a href='{e(s['url'])}'>{e(s['titre'])}</a></li>" if s.get("url") else f"<li>{e(s['titre'])}</li>"
                      for s in _sources(doc))
    sources = f"<h2>Sources</h2><ol>{sources}</ol>" if sources else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{e(doc['titre'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:46em;margin:3em auto;padding:0 1em;line-height:1.6;color:#1d2433}}
h1{{color:#0b6e8a}}.q{{color:#667;font-style:italic}}footer{{margin-top:3em;color:#889;font-size:.85em}}</style></head>
<body><h1>{e(doc['titre'])}</h1>{question}{corps}{sources}
<footer>Préparé par Orion le {datetime.date.today():%d/%m/%Y}.</footer></body></html>
"""


def _docx(doc, chemin):
    """Office Open XML minimal : titre, question, paragraphes, sources (liens écrits en clair)."""
    def para(texte, style=None, italique=False):
        p = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        r = "<w:rPr><w:i/></w:rPr>" if italique else ""
        return f'<w:p>{p}<w:r>{r}<w:t xml:space="preserve">{html.escape(texte)}</w:t></w:r></w:p>'
    corps = [para(doc["titre"], "Title")]
    if doc.get("question"):
        corps.append(para(f"Question : {doc['question']}", italique=True))
    corps += [para(p) for p in _paragraphes(doc["contenu"])]
    if _sources(doc):
        corps.append(para("Sources", "Heading1"))
        corps += [para(f"{i}. {s['titre']}" + (f" — {s['url']}" if s.get("url") else ""))
                  for i, s in enumerate(_sources(doc), 1)]
    corps.append(para(f"Préparé par Orion le {datetime.date.today():%d/%m/%Y}.", italique=True))
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {w}>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="40"/>'
              '<w:color w:val="0B6E8A"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/>'
              '<w:sz w:val="28"/></w:rPr></w:style></w:styles>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {w}><w:body>'
                + "".join(corps) + "</w:body></w:document>")
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                   'package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override '
                   'PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                   'wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/'
                   'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
                   'openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/_rels/document.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
                   'openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)


def generer(doc, format_, dossier):
    """`doc` : {titre, contenu, question?, sources?:[{titre, url}]}. Renvoie le chemin du fichier créé."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    if format_ == "pdf_pro":  # qualité professionnelle : LaTeX si Tectonic est là, sinon le PDF intégré
        from . import latex
        if latex.tectonic():
            return latex.rapport(doc, dossier)
        format_ = "pdf"
    if format_ == "pdf":
        from . import document
        return document.generer({"domaine": doc.get("domaine", "Réponse d'Orion"), **doc}, bool(_sources(doc)), dossier)
    chemin = dossier / _nom(doc["titre"], format_)
    if format_ == "docx":
        _docx(doc, chemin)
    else:
        chemin.write_text(markdown(doc) if format_ == "md" else page_html(doc), encoding="utf-8")
    return chemin
