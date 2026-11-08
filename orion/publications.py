# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Publications officielles téléchargées depuis la partie publique de jw.org, en fichiers EPUB.

Les conditions d'utilisation de jw.org autorisent les applications gratuites et non commerciales « conçues
pour télécharger des fichiers électroniques depuis la partie publique du site (EPUB, PDF, MP3, MP4) », mais
pas l'extraction de leur texte : Orion télécharge le fichier tel quel, le range dans les documents de
l'utilisateur et l'ouvre avec le lecteur de l'ordinateur. Il n'en lit jamais le contenu.
"""
import datetime
import json
import re
import urllib.parse
import urllib.request

from .texte import chiffres

UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
API = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
        "novembre", "decembre"]
# Publications reconnues à la voix : motif → code jw.org (sans numéro)
SIMPLES = [(r"\b(la )?bible\b", "nwt"), (r"\bvivez pour toujours\b", "lff"),
           (r"\bqu enseigne (reellement )?la bible\b", "bh")]


def _mois(t):
    """Mois cité (« de novembre », « du mois prochain »), sinon le mois en cours → date du 1er."""
    d = datetime.date.today().replace(day=1)
    m = re.search(r"\b(" + "|".join(MOIS) + r")\b", t)
    if m:
        mois = MOIS.index(m.group(1)) + 1
        annee = d.year + (1 if mois < d.month - 6 else 0)  # « janvier » dit en novembre : l'an prochain
        return datetime.date(int((re.search(r"\b(20\d\d)\b", t) or [None, annee])[1]), mois, 1)
    if re.search(r"\bmois prochain\b", t):
        return (d + datetime.timedelta(days=32)).replace(day=1)
    return d


def demande(t):
    """Phrase normalisée → [(code, numéro)] des publications demandées, ou None."""
    # « deux mille vingt-sept » → « 2 mille 27 » → « 2027 »
    t = re.sub(r"\b(\d) mille(?: (\d{1,2}))?\b", lambda m: str(int(m[1]) * 1000 + int(m[2] or 0)), chiffres(t))
    if re.search(r"\bexaminons (les )?ecritures\b|\btexte du jour\b", t):
        annees = [int(a) for a in re.findall(r"\b(20\d\d)\b", t)]  # « 2026 et 2027 » : les deux
        if not annees:
            annees = [datetime.date.today().year + bool(re.search(r"\bannee prochaine\b", t))]
        return [(f"es{an % 100:02d}", "") for an in dict.fromkeys(annees)]
    if re.search(r"\bcahier\b|\bvie et ministere\b", t):
        d = _mois(t)  # un cahier couvre deux mois : numéros de janvier, mars, mai…
        return [("mwb", f"{d.year}{d.month - (d.month + 1) % 2:02d}")]
    if re.search(r"\btour de garde\b", t):
        d = _mois(t)
        return [("w", f"{d.year}{d.month:02d}")]
    for motif, code in SIMPLES:
        if re.search(motif, t):
            return [(code, "")]
    return None


def chercher(code, numero=""):
    """{titre, url, octets, nom} du fichier EPUB français, ou None s'il n'est pas (encore) publié."""
    url = f"{API}?" + urllib.parse.urlencode({"pub": code, "issue": numero, "langwritten": "F",
                                              "fileformat": "EPUB", "output": "json", "alllangs": 0})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            f = json.load(r)["files"]["F"]["EPUB"][0]
    except Exception:
        return None
    titre = re.sub(r"\s+", " ", f["title"].replace("&nbsp;", " "))
    if titre == "Standard":
        mois = MOIS[int(numero[4:]) - 1].replace("fevrier", "février").replace("aout", "août")
        titre = {"mwb": "Cahier Vie et ministère", "w": "La Tour de Garde"}.get(code, code) \
            + f" de {mois} {numero[:4]}"
    return {"titre": titre, "url": f["file"]["url"], "octets": f["filesize"],
            "nom": f["file"]["url"].rsplit("/", 1)[-1]}


def telecharger(pub, dossier):
    """Enregistre le fichier dans `dossier` (déjà présent : rien n'est retéléchargé) ; renvoie son chemin."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / pub["nom"]
    if not chemin.exists():
        provisoire = chemin.with_suffix(".partiel")
        with urllib.request.urlopen(urllib.request.Request(pub["url"], headers=UA), timeout=120) as r, \
                open(provisoire, "wb") as f:
            while bloc := r.read(1 << 20):
                f.write(bloc)
        provisoire.rename(chemin)
    return chemin


JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_ACCENTS = [m.replace("fevrier", "février").replace("aout", "août").replace("decembre", "décembre")
                for m in MOIS]


def fichier_local(code, dossiers_possibles):
    """Fichier EPUB déjà téléchargé (dans l'un des dossiers de l'utilisateur), ou None."""
    for dossier in dossiers_possibles:
        f = dossier / f"{code}_F.epub"
        if f.exists():
            return f
    return None


def texte_du_jour(epub, date):
    """(titre, verset, commentaire) du jour dans un fichier « Examinons les Écritures » de l'utilisateur.
    Lu pour l'utilisateur seul, sur son ordinateur, comme le ferait la lecture à voix haute d'une liseuse."""
    import html
    import zipfile
    jour = f"{JOURS_SEMAINE[date.weekday()]} {date.day}(?:er)? {MOIS_ACCENTS[date.month - 1]}"
    with zipfile.ZipFile(epub) as z:
        for nom in z.namelist():
            if not nom.endswith(".xhtml"):
                continue
            page = z.read(nom).decode("utf-8", "replace")
            if not re.search(rf"<title>\s*{jour}\s*</title>", page, re.I):
                continue

            def texte(fragment):
                fragment = re.sub(r"<[^>]+>", "", fragment)
                return re.sub(r"\s+", " ", html.unescape(fragment)).strip()
            titre = texte(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
            verset = re.search(r'class="themeScrp">(.*?)</p>', page, re.S)
            corps = re.search(r'class="bodyTxt">(.*?)</div>', page, re.S)
            return (titre, texte(verset.group(1)) if verset else "",
                    " ".join(texte(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", corps.group(1), re.S)) if corps else "")
    return None


_CHAPITRES = {}  # fichier EPUB de la Bible → {« jean 3 » : nom de la page}, construit à la première lecture


def verset(epub, livre, chapitre, debut, fin=None):
    """Texte des versets `debut` à `fin` (livre au format de bible.LIVRES, ex. « 1 jean ») dans la Bible
    téléchargée par l'utilisateur, ou None. Lu pour lui seul, sur son ordinateur."""
    import html
    import zipfile
    from .texte import normaliser
    with zipfile.ZipFile(epub) as z:
        if epub not in _CHAPITRES:
            index = {}
            for nom in z.namelist():
                if nom.endswith(".xhtml") and "extracted" not in nom:
                    m = re.search(r"<title>(.*?)</title>", z.read(nom).decode("utf-8", "replace"), re.S)
                    if m:
                        titre = re.sub(r"^psaume\b", "psaumes", normaliser(html.unescape(m.group(1))))
                        index.setdefault(titre, []).append(nom)
            _CHAPITRES[epub] = index
        index = _CHAPITRES[epub]
        for nom in index.get(f"{livre} {chapitre}", []) + index.get(livre, []):  # livre d'un seul chapitre : « jude »
            page = z.read(nom).decode("utf-8", "replace")
            depart = page.find(f'id="chapter{chapitre}_verse{debut}"')
            if depart < 0:
                continue
            arret = page.find(f'id="chapter{chapitre}_verse{(fin or debut) + 1}"', depart)
            notes = re.search(r"<aside|<footer|epub:type=\"footnote\"", page[depart:])  # fin du chapitre
            fin_chapitre = depart + notes.start() if notes else page.find("</body>", depart)
            arret = fin_chapitre if arret < 0 else page.rfind("<", depart, min(arret, fin_chapitre) + 1)
            extrait = page[depart:arret]
            extrait = re.sub(r'<a epub:type="noteref"[^>]*>.*?</a>', "", extrait)   # appels de note « * »
            extrait = re.sub(r"<sup>.*?</sup>|<span class=\"w_ch\">.*?</span>", " ", extrait)  # numéros
            extrait = re.sub(r"<[^>]+>|^[^>]*>", " ", extrait)
            texte = re.sub(r"\s+", " ", html.unescape(extrait).replace("\u200b", ""))
            return re.sub(r"\s+([,.])", r"\1", texte).strip()
    return None
