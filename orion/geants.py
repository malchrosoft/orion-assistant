# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""« Sur les épaules de géants » : comment d'autres ont déjà résolu ce problème.

Méthode (d'après le principe de Bernard de Chartres, repris par Newton) :
1. reformuler le problème en termes intemporels, avec ses anciens noms (modèle local, rien ne sort) ;
2. chercher dans des sources ouvertes et gratuites, avec des interfaces publiques documentées :
   Wikipédia et OpenAlex (catalogue ouvert des publications scientifiques, données CC0) ;
3. ne citer que ce qui a été réellement consulté pendant la recherche ;
4. filtre de Lindy : une idée qui dure depuis longtemps et reste citée est un « pilier », le reste est « récent ».
Le résultat est dit en trois phrases et détaillé dans une fiche PDF avec ses sources.
"""
import datetime
import json
import re
import urllib.parse
import urllib.request

from . import knowledge, web

UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial, usage non commercial)"}
OPENALEX = "https://api.openalex.org/works"
CONSIGNE = ("Tu reformules un problème en termes intemporels, sans marque ni version de logiciel. Réponds sur deux "
            "lignes exactement :\nFR: <le problème en une phrase en français>\nEN: <3 à 6 termes techniques en anglais, du plus général au plus précis, "
            "anciens noms du concept, séparés par des virgules>")


def reformuler(sujet, conversation):
    """(phrase intemporelle, [mots-clés anglais]) ; sans modèle local : le sujet tel quel."""
    sortie = conversation.completer(CONSIGNE, sujet) if conversation else None
    sortie = re.sub(r"[*_`]+", "", sortie or "")  # le modèle met parfois du gras : « **FR :** »
    fr = re.search(r"FR\s*:\s*(.+)", sortie or "")
    en = re.search(r"EN\s*:\s*(.+)", sortie or "")
    cles = [re.sub(r"\s*\(.*?\)", "", c).strip(" .") for c in en.group(1).split(",")] if en else []
    cles = [c for c in cles if c]  # « NTP (1984) » → « NTP »
    return (fr.group(1).strip() if fr else sujet), (cles[:6] or [sujet])


def _lire(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def _resume(inverse, max_mots=45):
    """Résumé OpenAlex (index inversé) → premières phrases, pour citer ce qu'on a vraiment lu."""
    if not inverse:
        return ""
    mots = sorted((pos, mot) for mot, positions in inverse.items() for pos in positions)
    texte = " ".join(m for _, m in mots[:max_mots])
    return texte + ("…" if len(mots) > max_mots else "")


def publications(cles, nombre=6):
    """Publications ouvertes les plus pertinentes pour ces mots-clés, puis triées par ancienneté."""
    vues, trouvees = set(), []
    annee = datetime.date.today().year
    for cle in cles[:4]:
        url = OPENALEX + "?" + urllib.parse.urlencode({
            # expression exacte dans le titre ou le résumé : « exactly-once delivery », pas tout ce qui parle de livraison
            "filter": f'title_and_abstract.search:"{cle.replace(",", " ")}",is_oa:true,cited_by_count:>20', "per-page": 6,
            "select": "id,title,publication_year,cited_by_count,authorships,open_access,doi,abstract_inverted_index"})
        for w in _lire(url).get("results", []):
            if w["id"] in vues or not w.get("title") or not w.get("publication_year"):
                continue
            vues.add(w["id"])
            auteurs = [a["author"]["display_name"] for a in w.get("authorships", [])[:2]]
            age = annee - w["publication_year"]
            trouvees.append({
                "annee": w["publication_year"], "titre": w["title"], "citations": w["cited_by_count"],
                "auteurs": " et ".join(auteurs) + (" et al." if len(w.get("authorships", [])) > 2 else ""),
                "url": (w.get("open_access") or {}).get("oa_url") or w.get("doi") or w["id"],
                "resume": _resume(w.get("abstract_inverted_index")),
                # filtre de Lindy : ancien ET toujours cité
                "pilier": age >= 10 and w["cited_by_count"] >= 100})
    trouvees.sort(key=lambda p: (not p["pilier"], -p["citations"]))
    return sorted(trouvees[:nombre], key=lambda p: p["annee"])


def rechercher(sujet, conversation=None, signaler=print):
    """Recherche complète : {intemporel, cles, wikipedia, lignee} (rien d'inventé : tout a été consulté)."""
    signaler("Je reformule le problème…")
    intemporel, cles = reformuler(sujet, conversation)
    signaler("Je consulte Wikipédia…")
    try:
        article = web.wikipedia(sujet)
    except Exception:
        article = None
    signaler("Je cherche les publications de référence…")
    try:
        lignee = publications(cles)
    except Exception:
        lignee = []
    return {"sujet": sujet, "intemporel": intemporel, "cles": cles, "wikipedia": article, "lignee": lignee}


def a_dire(r):
    """Trois phrases au plus, pour l'oral."""
    if not r["lignee"] and not r["wikipedia"]:
        return "Je n'ai trouvé aucune source ouverte assez solide sur ce sujet."
    texte = f"En termes intemporels : {r['intemporel'].rstrip('.')}."
    piliers = [p for p in r["lignee"] if p["pilier"]]
    if piliers:
        p = piliers[0]
        texte += f" Le texte fondateur que j'ai trouvé : {p['auteurs']}, en {p['annee']}, {p['titre']}."
    elif r["lignee"]:
        texte += " Je n'ai trouvé que des travaux récents, à prendre avec prudence."
    return texte + " Je t'ai préparé une fiche avec la lignée complète et les sources."


def fiche(r):
    """Fiche PDF (format de document.generer) : lignée de la plus ancienne à la plus récente, sources consultées."""
    lignes = [f"Problème : {r['intemporel']}", f"Aussi connu sous : {', '.join(r['cles'])}.", ""]
    if r["wikipedia"]:
        lignes.append(f"Repère : {r['wikipedia']['contenu']}")
    if r["lignee"]:
        lignes.append("Lignée, de la plus ancienne à la plus récente :")
        for p in r["lignee"]:
            etiquette = "pilier" if p["pilier"] else "récent"
            lignes.append(f"{p['annee']} — {p['auteurs']}, « {p['titre']} » ({p['citations']} citations, {etiquette})."
                          + (f" Extrait : {p['resume']}" if p["resume"] else ""))
    lignes.append("Pilier : idée d'au moins dix ans, toujours citée. Récent : à confirmer par un pilier.")
    sources = ([{"titre": f"Wikipédia, « {r['wikipedia']['titre']} »", "url": r["wikipedia"]["url"], "niveau": 1,
                 "consulte": knowledge.aujourdhui()}] if r["wikipedia"] else [])
    sources += [{"titre": f"{p['auteurs']} ({p['annee']}), {p['titre']}", "url": p["url"], "niveau": 2 if p["pilier"] else 1,
                 "consulte": knowledge.aujourdhui()} for p in r["lignee"]]
    return {"titre": f"Sur les épaules de géants : {r['sujet']}", "domaine": "Recherche", "contenu": "\n".join(lignes),
            "sources": sources,
            "avertissement": "Synthèse automatique de sources ouvertes : lisez les sources avant de vous appuyer dessus."}
