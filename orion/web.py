# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Apprendre depuis un lien internet, avec méfiance.

Tout ce qui vient du web est stocké au niveau 0 (« non vérifié ») et Orion le signale à chaque
fois qu'il s'en sert. Le texte récupéré est traité comme une donnée, jamais comme une consigne.
"""
import html.parser
import re
import urllib.parse
import urllib.request

from . import knowledge
from .texte import normaliser

AVERTISSEMENT = ("Attention : ce qu'on trouve sur internet peut être faux, daté ou orienté. "
                 "Je garderai cette source comme non vérifiée et je le rappellerai à chaque réponse.")

# Indices (pas des garanties) que le site publie des sources primaires — cf. grille shoulders-of-giants
SITES_PRIMAIRES = (".gouv.fr", "education.gouv.fr", "eduscol", "bipm.org", "iso.org", "rfc-editor.org",
                   "w3.org", "arxiv.org", "hal.science", "cnrs.fr", "inria.fr", "openstax.org", ".edu")
SITES_DOUTEUX = ("medium.com", "dev.to", "facebook.com", "tiktok.com", "x.com", "twitter.com",
                 "youtube.com", "blogspot", "quora")


class _Extraction(html.parser.HTMLParser):
    IGNORE = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript"}

    def __init__(self):
        super().__init__()
        self.titre, self.paragraphes, self._pile, self._tampon = "", [], [], []

    def handle_starttag(self, tag, attrs):
        self._pile.append(tag)

    def handle_endtag(self, tag):
        if tag in self._pile:
            while self._pile and self._pile.pop() != tag:
                pass
        if tag in ("p", "li") and self._tampon:
            texte = re.sub(r"\s+", " ", "".join(self._tampon)).strip()
            if len(texte) > 60:
                self.paragraphes.append(texte)
            self._tampon = []

    def handle_data(self, data):
        if any(t in self.IGNORE for t in self._pile):
            return
        if self._pile and self._pile[-1] == "title":
            self.titre += data
        elif any(t in ("p", "li") for t in self._pile):
            self._tampon.append(data)


def avis_sur_le_site(url):
    hote = urllib.parse.urlparse(url).hostname or ""
    if any(s in hote for s in SITES_DOUTEUX):
        return "Ce site publie surtout des contenus non relus : prudence renforcée."
    if any(s in hote for s in SITES_PRIMAIRES):
        return "Le site semble institutionnel ou académique, mais je ne peux pas le garantir."
    return "Je ne connais pas la fiabilité de ce site."


def lire_page(url, max_caracteres=1200):
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Seuls les liens http et https sont acceptés.")
    req = urllib.request.Request(url, headers={"User-Agent": "Orion-assistant/1.0 (usage familial)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if "html" not in r.headers.get("Content-Type", ""):
            raise ValueError("La page n'est pas une page web lisible (PDF, image…).")
        brut = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    p = _Extraction()
    p.feed(brut)
    texte = ""
    for para in p.paragraphes:
        if len(texte) + len(para) > max_caracteres:
            break
        texte += para + " "
    return p.titre.strip() or url, texte.strip()


def apprendre(url, sujet=None, domaine="web"):
    """Récupère la page, crée une fiche non vérifiée. Renvoie (fiche, message à dire)."""
    titre, texte = lire_page(url)
    if not texte:
        return None, "Je n'ai trouvé aucun texte exploitable sur cette page."
    from . import espace
    from .config import charger
    if not espace.place_pour(charger(), len(texte) * 4 + 10_000):
        return None, espace.refus(charger())
    sujet = sujet or titre
    fiche = {"domaine": domaine, "titre": sujet, "motscles": normaliser(f"{sujet} {titre}"),
             "contenu": texte,
             "sources": [{"titre": titre, "url": url, "niveau": 0, "consulte": knowledge.aujourdhui()}]}
    knowledge.ajouter(fiche)
    return fiche, f"J'ai lu « {titre[:80]} ». {avis_sur_le_site(url)} {AVERTISSEMENT}"


def verifier_references():
    """Vérifie que chaque référence livrée est bien en ligne et accessible librement
    (principe « consultée, pas mémorisée »). Renvoie la liste (statut, titre, url)."""
    import json
    refs = knowledge.references()
    toutes = [s for groupe in ("domaines", "fiches") for lst in refs[groupe].values() for s in lst]
    resultats = []
    for s in toutes:
        try:
            req = urllib.request.Request(s["url"], headers={"User-Agent": "Orion-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = r.status == 200
        except Exception as e:
            ok, s["erreur"] = False, str(e)[:60]
        if ok:
            s["consulte"] = knowledge.aujourdhui()
            s.pop("erreur", None)
        resultats.append(("OK" if ok else "ÉCHEC", s["titre"], s["url"]))
    knowledge.REFERENCES.write_text(json.dumps(refs, ensure_ascii=False, indent=1), encoding="utf-8")
    knowledge.construire()
    return resultats


def wikipedia(question):
    """Résumé de l'article Wikipédia le plus pertinent, via l'API officielle.
    Renvoie {titre, contenu, url} ou None."""
    import json
    from .knowledge import VIDES
    vides = VIDES | {"qui", "etait", "etaient", "est", "sont", "etre", "dit", "moi", "connais", "sais"}
    mots = " ".join(m for m in normaliser(question).split() if m not in vides) or question
    entete = {"User-Agent": "Orion-assistant/1.0 (assistant familial open source)"}

    def lire(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=entete), timeout=10) as r:
            return json.loads(r.read())

    def resume(titre):
        return lire("https://fr.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(titre.replace(" ", "_")))

    try:  # d'abord l'article dont le titre est exactement le sujet (« victor hugo » → Victor Hugo)
        page = resume(mots.title())
        if page.get("type") != "standard":
            raise ValueError("page d'homonymie")
    except Exception:
        res = lire("https://fr.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch="
                   + urllib.parse.quote(mots))["query"]["search"]
        if not res:
            return None
        page = resume(res[0]["title"])
    titre = page["title"]
    # un article sans aucun mot commun avec la question est un faux résultat (« Tristane Banon » pour « pdf »)
    if not set(normaliser(titre).split()) & set(mots.split()):
        return None
    phrases = re.split(r"(?<=[.!?])\s+", page.get("extract", ""))
    return {"titre": titre, "contenu": " ".join(phrases[:2]), "url": page["content_urls"]["desktop"]["page"]}
