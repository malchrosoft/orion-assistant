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
    if ajoutee(t):
        return [ajoutee(t)]
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
    indexer([dossier])  # entrées consultables aussitôt (recherche par thème)
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


def texte_du_jour(epub, date, page_lue=None):
    """(titre, verset, commentaire) du jour dans un fichier « Examinons les Écritures » de l'utilisateur.
    Lu pour l'utilisateur seul, sur son ordinateur, comme le ferait la lecture à voix haute d'une liseuse."""
    import html
    import zipfile
    jour = (f"{JOURS_SEMAINE[date.weekday()]} {date.day}(?:er)? {MOIS_ACCENTS[date.month - 1]}" if date
            else "(?:" + "|".join(JOURS_SEMAINE) + r") \d+(?:er)? \w+")

    def pages():
        if page_lue is not None:
            yield page_lue
            return
        with zipfile.ZipFile(epub) as z:
            for nom in z.namelist():
                if nom.endswith(".xhtml"):
                    yield z.read(nom).decode("utf-8", "replace")
    for page in pages():
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


def _nettoyer(extrait):
    """Fragment XHTML → texte à lire : sans appels de note, numéros de verset ni balises."""
    import html
    extrait = re.sub(r'<a epub:type="noteref"[^>]*>.*?</a>', "", extrait)   # appels de note « * »
    extrait = re.sub(r"<sup>.*?</sup>|<span class=\"w_ch\">.*?</span>", " ", extrait)  # numéros
    extrait = re.sub(r"<[^>]+>|^[^>]*>", " ", extrait)
    texte = re.sub(r"\s+", " ", html.unescape(extrait).replace("\u200b", ""))
    return re.sub(r"\s+([,.])", r"\1", texte).strip(" ,;")


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
            return _nettoyer(page[depart:arret])
    return None


# --- Index de recherche (local) : « que dit la Bible sur le pardon ? » ------------------------------------------
def _base():
    import sqlite3
    from .config import DONNEES
    db = sqlite3.connect(DONNEES / "publications.db")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(publication, lieu, texte, "
               "tokenize='unicode61 remove_diacritics 2')")
    db.execute("CREATE TABLE IF NOT EXISTS fichiers (nom TEXT PRIMARY KEY, date REAL)")
    return db


def _passages(epub):
    """[(lieu, texte)] : un verset par ligne pour la Bible, un jour pour « Examinons », un paragraphe sinon."""
    import html
    import zipfile
    from . import bible
    from .texte import normaliser
    code = epub.stem.split("_")[0]
    with zipfile.ZipFile(epub) as z:
        for nom in z.namelist():
            if not nom.endswith(".xhtml") or "extracted" in nom:
                continue
            page = z.read(nom).decode("utf-8", "replace")
            m = re.search(r"<title>(.*?)</title>", page, re.S)
            titre = _nettoyer(m.group(1)) if m else ""
            notes = re.search(r"<aside|<footer|epub:type=\"footnote\"", page)
            page = page[:notes.start()] if notes else page
            if code == "nwt":
                livre = re.sub(r"\s*\d+$", "", normaliser(html.unescape(titre)))
                livre = re.sub(r"^psaume\b", "psaumes", livre)
                morceaux = re.split(r'<span id="chapter(\d+)_verse(\d+)"></span>', page)
                for i in range(1, len(morceaux) - 2, 3):
                    texte = _nettoyer(morceaux[i + 2])
                    if texte and livre in bible.LIVRES:
                        yield f"{bible.nom_livre(livre)} {morceaux[i]}:{morceaux[i + 1]}", texte
            elif code.startswith("es"):
                r = texte_du_jour(epub, None, page)
                if r:
                    yield f"texte du {r[0][0].lower() + r[0][1:]}", f"{r[1]} {r[2]}"
            else:
                for para in re.findall(r"<p[^>]*>(.*?)</p>", page, re.S):
                    texte = _nettoyer(para)
                    if len(texte) > 60:
                        yield titre, texte


def indexer(dossiers_possibles):
    """Indexe les EPUB téléchargés pas encore indexés (ou modifiés). Renvoie le nombre de fichiers traités."""
    db, traites = _base(), 0
    for dossier in dossiers_possibles:
        for epub in sorted(dossier.glob("*_F*.epub")) if dossier.exists() else []:
            date = epub.stat().st_mtime
            deja = db.execute("SELECT date FROM fichiers WHERE nom = ?", (epub.name,)).fetchone()
            if deja and deja[0] == date:
                continue
            db.execute("DELETE FROM passages WHERE publication = ?", (epub.stem,))  # « nwt_F », « w_F_202609 »
            db.executemany("INSERT INTO passages VALUES (?, ?, ?)", ((epub.stem, l, t) for l, t in _passages(epub)))
            db.execute("INSERT OR REPLACE INTO fichiers VALUES (?, ?)", (epub.name, date))
            db.commit()
            traites += 1
    db.close()
    return traites


def rechercher(sujet, publication=None, limite=3):
    """[(lieu, texte)] les plus pertinents pour `sujet` (mots ou débuts de mots : « pardon » → « pardonner »)."""
    from .knowledge import VIDES
    from .texte import normaliser
    questions = {"pourquoi", "quand", "qui", "quoi", "etait", "etaient", "dit", "dire", "bible", "biblique",
                 "verset", "versets", "parle", "parlent", "parlait", "cherche", "publications", "lis", "lire"}
    mots = [m for m in normaliser(sujet).split() if m not in VIDES | questions and len(m) > 2]
    if not mots:
        return []
    db = _base()
    filtre = " AND publication LIKE ?" if publication else ""  # « es » : tous les livrets d'Examinons
    try:
        for liaison in (" AND ", " OR "):  # d'abord tous les mots, sinon l'un d'eux
            # débuts de mots : « pardon » trouve « pardonnez » ; les mots longs perdent leur terminaison
            requete = "texte : (" + liaison.join(f'"{m if len(m) < 7 else m[:-2]}"*' for m in mots) + ")"
            lignes = db.execute(f"SELECT lieu, texte FROM passages WHERE passages MATCH ?{filtre} "
                                "ORDER BY rank LIMIT ?", (requete, *([publication + "%"] if publication else []), limite)).fetchall()
            if lignes:
                return lignes
        return []
    finally:
        db.close()


# --- Publications choisies par l'utilisateur sur jw.org (méthode indiquée par le site) -----------------------
# Orion ne cherche pas lui-même dans le site : il ouvre la page de recherche publique dans le navigateur ;
# l'utilisateur choisit la publication et lui donne le lien de téléchargement (bouton « Partager » / fenêtre de
# téléchargement), que les conditions d'utilisation permettent de partager.
RECHERCHE = "https://www.jw.org/fr/rechercher/?q="


def _ajoutees():
    from .config import DONNEES
    f = DONNEES / "publications_ajoutees.json"
    return f, (json.loads(f.read_text(encoding="utf-8")) if f.exists() else {})


def depuis_lien(lien):
    """(code, numéro) lus dans un lien jw.org (lien de téléchargement ou de partage), ou None."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(lien.strip()).query)
    code = (q.get("pub") or q.get("pubSym") or [None])[0]
    return (code, (q.get("issue") or [""])[0]) if code and re.fullmatch(r"[\w-]{1,20}", code) else None


def retenir(pub, code, numero=""):
    """Ajoute la publication à la liste d'Orion : on pourra ensuite la demander par son titre."""
    from .texte import normaliser
    fichier, data = _ajoutees()
    data[normaliser(re.split(r"[(:]", pub["titre"])[0])] = [code, numero]
    fichier.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def ajoutee(t):
    """Publication ajoutée par l'utilisateur dont le titre est cité dans la phrase, ou None."""
    for titre, (code, numero) in sorted(_ajoutees()[1].items(), key=lambda x: -len(x[0])):
        if titre and titre in t:
            return code, numero
    return None


def presse_papiers():
    """Texte copié (lien de téléchargement), selon le système ; chaîne vide si indisponible."""
    import platform
    import subprocess
    commandes = {"Darwin": [["pbpaste"]], "Windows": [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]],
                 "Linux": [["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"]]}
    for cmd in commandes.get(platform.system(), []):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def verifier(dossiers_possibles):
    """Au démarrage : chaque EPUB téléchargé s'ouvre-t-il ? L'index ne garde que les fichiers présents.
    Renvoie {« valides »: n, « corrompus »: [noms], « disparus »: [noms]} ; les fichiers abîmés sont mis de
    côté (« .corrompu ») pour être retéléchargés, jamais supprimés."""
    import zipfile
    bilan = {"valides": 0, "corrompus": [], "disparus": []}
    presents = set()
    for dossier in dossiers_possibles:
        if not dossier.exists():
            continue
        for reste in dossier.glob("*_F*.partiel"):  # téléchargement interrompu
            reste.unlink(missing_ok=True)
        for epub in dossier.glob("*_F*.epub"):
            try:
                with zipfile.ZipFile(epub) as z:
                    if z.testzip() is not None or not any(n.endswith(".xhtml") for n in z.namelist()):
                        raise zipfile.BadZipFile
                presents.add(epub.stem)
                bilan["valides"] += 1
            except (zipfile.BadZipFile, OSError):
                epub.rename(epub.with_suffix(".epub.corrompu"))
                bilan["corrompus"].append(epub.name)
    db = _base()
    for (nom,) in db.execute("SELECT nom FROM fichiers").fetchall():
        stem = nom.rsplit(".", 1)[0]
        if stem not in presents:  # fichier supprimé ou abîmé : ses entrées quittent l'index
            db.execute("DELETE FROM passages WHERE publication = ?", (stem,))
            db.execute("DELETE FROM fichiers WHERE nom = ?", (nom,))
            bilan["disparus"].append(nom)
    db.commit()
    db.close()
    indexer(dossiers_possibles)
    return bilan


def programme_semaine(epub, date):
    """Programme de la réunion de semaine (cahier Vie et ministère téléchargé) pour la semaine de `date` :
    (titre de la semaine, [parties « titre, durée »]) ou None. Lu pour l'utilisateur seul, chez lui."""
    import zipfile
    from .texte import normaliser
    lundi = date - datetime.timedelta(days=date.weekday())
    mois = MOIS_ACCENTS[lundi.month - 1]
    debut = rf"^{lundi.day}(?:er)?(?: {mois}(?: \d{{4}})?)?\s*[-–]"
    with zipfile.ZipFile(epub) as z:
        for nom in z.namelist():
            if not nom.endswith(".xhtml") or "extracted" in nom:
                continue
            page = z.read(nom).decode("utf-8", "replace")
            m = re.search(r"<title>(.*?)</title>", page, re.S)
            if not m or not re.search(debut, _nettoyer(m.group(1)), re.I):
                continue
            notes = re.search(r"<aside|<footer|epub:type=\"footnote\"", page)
            page = page[:notes.start()] if notes else page
            parties = []
            for titre, suite in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>(?=(.{0,300}))", page, re.S):
                # le passage de la semaine est un lien (« LAMENTATIONS 1-2 ») : on garde son texte
                titre = _nettoyer(re.sub(r'<a epub:type="noteref"[^>]*>([^<*][^<]*)</a>', r"\1", titre))
                duree = re.search(r"\((\d+) min\)", titre + _nettoyer(suite))
                if re.fullmatch(r"(?:\d )?[A-ZÉÈÏ ]+ \d+(?:-\d+)?", titre):
                    titre = "Lecture de la semaine : " + titre.title().replace("-", " à ")
                titre = re.sub(r"\s*\(\d+ min\)", "", titre).replace(" | ", ", ").strip()
                if not titre:
                    continue
                if titre.upper() == titre:  # rubriques en capitales : « JOYAUX DE LA PAROLE DE DIEU »
                    titre = re.sub(r"\b(dieu|jéhovah|bible)\b", lambda m: m[1].capitalize(),
                                   titre[:1] + titre[1:].lower())
                minutes = int(duree.group(1)) if duree else 0
                parties.append(titre + (f", {minutes} minute{'s' if minutes > 1 else ''}" if minutes else ""))
            semaine = _nettoyer(m.group(1))
            return semaine, [x for x in parties if normaliser(x) != normaliser(semaine)]
    return None
