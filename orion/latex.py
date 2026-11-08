# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Rapport PDF de qualité professionnelle, composé avec LaTeX (moteur Tectonic, licence MIT).

Tectonic est un programme séparé, utilisé s'il est installé sur l'ordinateur ; à la première composition
il télécharge les extensions LaTeX dont il a besoin. Sans lui, Orion garde son générateur PDF intégré.
Style sobre et factuel : palette sarcelle, page de titre avec encart, synthèse encadrée, sources en fin.
"""
import datetime
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import UTILISATEUR

PREAMBULE = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[french]{babel}
\usepackage[a4paper,margin=2.2cm,top=2.6cm]{geometry}
\usepackage{lmodern,microtype,enumitem,xcolor,fancyhdr,hyperref}
\usepackage{titlesec}
\titleformat*{\section}{\Large\sffamily\bfseries\color{orionSombre}}
\usepackage[most]{tcolorbox}
\definecolor{orionSarcelle}{HTML}{1F8A8A}
\definecolor{orionSombre}{HTML}{0F5C5C}
\definecolor{orionPale}{HTML}{E6F2F2}
\definecolor{orionGris}{HTML}{6B7C7C}
\hypersetup{colorlinks=true,urlcolor=orionSombre,linkcolor=orionSombre}
\pagestyle{fancy}\fancyhf{}
\renewcommand{\headrulewidth}{0.4pt}\renewcommand{\headrule}{\color{orionSarcelle}\hrule}
\fancyhead[L]{\small\sffamily\color{orionGris}\leftmark}
\fancyfoot[L]{\small\sffamily\color{orionGris}Préparé par Orion}
\fancyfoot[R]{\small\sffamily\color{orionGris}\thepage}
\newtcolorbox{encart}[1][]{colback=orionPale,colframe=orionSarcelle,boxrule=0.6pt,arc=2pt,
  left=8pt,right=8pt,top=6pt,bottom=6pt,#1}
\setlength{\parskip}{0.6em}\setlength{\parindent}{0pt}
"""


def tectonic():
    """Chemin de Tectonic s'il est installé (sur l'ordinateur ou dans le dossier d'Orion), sinon None."""
    local = UTILISATEUR / "latex" / ("tectonic.exe" if shutil.which("cmd") else "tectonic")
    return shutil.which("tectonic") or (str(local) if local.exists() else None)


def echapper(texte):
    """Texte libre → LaTeX sûr (caractères spéciaux, guillemets français, tirets, liens laissés à part)."""
    remplacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                     "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    texte = "".join(remplacements.get(c, c) for c in texte)
    texte = re.sub(r"«\s*", r"\\og ", texte)
    texte = re.sub(r"\s*»", r"\\fg{}", texte)
    return texte.replace("—", "---").replace("–", "--").replace("…", r"\dots{}")


def source_latex(doc):
    e = echapper
    paragraphes = [p.strip() for p in re.split(r"\n+", doc["contenu"]) if p.strip()]
    sources = [s for s in doc.get("sources", []) if s.get("consulte", True)]
    lignes = [PREAMBULE, r"\begin{document}", r"\markboth{" + e(doc["titre"]) + "}{}",
              r"{\sffamily\color{orionSombre}\fontsize{24}{28}\selectfont\bfseries " + e(doc["titre"]) + r"\par}",
              r"\vspace{2pt}{\color{orionSarcelle}\rule{\linewidth}{1.2pt}}\vspace{6pt}",
              r"\begin{encart}\sffamily"]
    if doc.get("question"):
        lignes.append(r"\textbf{Question} : " + e(doc["question"]) + r"\\[3pt]")
    lignes.append(r"\textbf{Date} : " + datetime.date.today().strftime("%d/%m/%Y") + r"\\[3pt]")
    lignes.append(r"\textbf{Sources} : " + (f"{len(sources)} référence(s) consultée(s), en fin de document."
                                            if sources else "aucune source externe citée."))
    lignes += [r"\end{encart}", r"\section*{Synthèse}"] + [e(p) + "\n" for p in paragraphes]
    if sources:
        lignes += [r"\section*{Sources}", r"\begin{enumerate}[leftmargin=*]"]
        lignes += [r"\item " + e(s["titre"]) + (r" --- \url{" + s["url"].replace("%", r"\%").replace("#", r"\#") + "}"
                                                if s.get("url") else "") for s in sources]
        lignes.append(r"\end{enumerate}")
    lignes.append(r"\end{document}")
    return "\n".join(lignes)


def rapport(doc, dossier):
    """Compose le rapport PDF dans `dossier` ; renvoie son chemin. Lève RuntimeError si LaTeX échoue."""
    moteur = tectonic()
    if not moteur:
        raise RuntimeError("Tectonic n'est pas installé.")
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    nom = re.sub(r"[^\w-]+", "-", doc["titre"], flags=re.UNICODE).strip("-")[:60] or "rapport"
    with tempfile.TemporaryDirectory() as travail:
        tex = Path(travail) / f"{nom}.tex"
        tex.write_text(source_latex(doc), encoding="utf-8")
        r = subprocess.run([moteur, "--keep-logs", "--outdir", travail, str(tex)], capture_output=True, text=True,
                           timeout=600)
        pdf = Path(travail) / f"{nom}.pdf"
        if r.returncode or not pdf.exists():
            raise RuntimeError("La composition LaTeX a échoué : " + (r.stderr or r.stdout)[-300:])
        cible = dossier / f"{nom}-rapport.pdf"  # à côté du PDF simple, sans l'écraser
        shutil.copy(pdf, cible)
    return cible
