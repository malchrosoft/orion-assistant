# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Ce qu'Orion retient de chaque voix connue, uniquement sur ce poste (rien ne sort de l'ordinateur).

Pour chaque personne : tutoiement ou vouvoiement, âge, niveau scolaire, humeur récente et un historique court
(les derniers échanges, pas plus). Les voix non reconnues ne laissent aucune trace. « Oublie ce que tu sais sur
moi » efface tout pour la personne qui parle.
"""
import datetime
import json
import re

from .config import DONNEES
from .texte import chiffres, normaliser

FICHIER = DONNEES / "personnes.json"
HISTORIQUE_MAX = 20           # échanges conservés par personne
HUMEUR_VALIDITE_JOURS = 3     # au-delà, l'humeur n'est plus « récente »

NIVEAUX = {"cp": "CP", "ce1": "CE1", "ce2": "CE2", "cm1": "CM1", "cm2": "CM2", "sixieme": "sixième",
           "cinquieme": "cinquième", "quatrieme": "quatrième", "troisieme": "troisième", "seconde": "seconde",
           "premiere": "première", "terminale": "terminale"}
HUMEURS = {
    "triste": "triste", "fatigue": "fatigué·e", "fatiguee": "fatigué·e", "stresse": "stressé·e",
    "stressee": "stressé·e", "inquiet": "inquiet·ète", "inquiete": "inquiet·ète", "en colere": "en colère",
    "content": "content·e", "contente": "content·e", "heureux": "heureux·se", "heureuse": "heureux·se",
    "malade": "malade", "enerve": "énervé·e", "enervee": "énervé·e", "decourage": "découragé·e",
    "fier": "fier·ère", "fiere": "fier·ère",
}
POSITIVES = {"content·e", "heureux·se", "fier·ère"}


def _lire():
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {}


def _ecrire(data):
    FICHIER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def fiche(nom):
    return _lire().get(nom, {})


def modifier(nom, **valeurs):
    data = _lire()
    data.setdefault(nom, {}).update(valeurs)
    _ecrire(data)


def oublier(nom):
    data = _lire()
    data.pop(nom, None)
    _ecrire(data)


def raccourcir_historiques(garder):
    """Allègement : ne garde que les `garder` derniers échanges de chacun (les souvenirs demandés restent)."""
    data = _lire()
    for p in data.values():
        if "historique" in p:
            p["historique"] = p["historique"][-garder:]
    _ecrire(data)


def noter_echange(nom, question, reponse):
    data = _lire()
    p = data.setdefault(nom, {})
    historique = p.setdefault("historique", [])
    historique.append({"date": datetime.date.today().isoformat(), "question": question[:200],
                       "reponse": (reponse or "")[:200]})
    p["historique"] = historique[-HISTORIQUE_MAX:]
    _ecrire(data)


def apprendre(nom, phrase):
    """Repère ce que la personne dit d'elle-même ; renvoie un court accusé de réception, ou None."""
    t = normaliser(phrase)
    appris = []
    m = re.search(r"\bj ai (\d{1,3}) ans\b", chiffres(t))  # « douze » → 12 (seulement ici : « un peu »)
    if m and 2 < int(m.group(1)) < 120:
        modifier(nom, age=int(m.group(1)), age_note=datetime.date.today().isoformat())
        appris.append(f"tu as {m.group(1)} ans")
    m = re.search(rf"\bje suis en ({'|'.join(NIVEAUX)})\b", t)
    if m:
        modifier(nom, niveau=NIVEAUX[m.group(1)])
        appris.append(f"tu es en {NIVEAUX[m.group(1)]}")
    m = re.search(rf"\bje (?:suis|me sens)(?: un peu| tres| trop)? ({'|'.join(HUMEURS)})\b", t)
    if m:
        modifier(nom, humeur=HUMEURS[m.group(1)], humeur_date=datetime.date.today().isoformat())
        return ("Ça me fait plaisir pour toi." if HUMEURS[m.group(1)] in POSITIVES
                else "Merci de me le dire. Je suis là si tu veux en parler, ou si je peux t'aider.")
    if appris:
        return "C'est noté : " + " et ".join(appris) + "."
    return None


def a_la_deuxieme(texte):
    """« je suis allergique, mon chat » → « tu es allergique, ton chat » (pour le répéter à la personne)."""
    for motif, rempl in ((r"\bje suis\b", "tu es"), (r"\bj'ai\b", "tu as"), (r"\bj'(\w+e)\b", r"tu \1s"),
                         (r"\bje (\w+e)\b", r"tu \1s"), (r"\bje\b", "tu"),
                         (r"\bj'", "tu "), (r"\bmon\b", "ton"), (r"\bma\b", "ta"), (r"\bmes\b", "tes"),
                         (r"\bmoi\b", "toi"), (r"\bm'", "t'"), (r"\bme\b", "te")):
        texte = re.sub(motif, rempl, texte, flags=re.IGNORECASE)
    return texte


def retenir(nom, souvenir):
    """Mémorisé indéfiniment, à la demande (« retiens que… ») ; seul « oublie que… » ou « oublie tout » l'efface."""
    data = _lire()
    souvenirs = data.setdefault(nom, {}).setdefault("souvenirs", [])
    if souvenir not in [s["texte"] for s in souvenirs]:
        souvenirs.append({"texte": souvenir, "date": datetime.date.today().isoformat()})
    _ecrire(data)


def chercher_memoire(nom, mots):
    """Entrées de la mémoire de la personne qui contiennent ces mots (recherche textuelle, sans accents) :
    [(« souvenir » | « échange », position, texte lisible)], les plus récentes d'abord."""
    p, cible = fiche(nom), normaliser(mots)
    if not cible:
        return []
    trouvees = [("souvenir", i, s["texte"]) for i, s in enumerate(p.get("souvenirs", []))
                if cible in normaliser(s["texte"])]
    trouvees += [("échange", i, f"{e['question']} → {e['reponse']}") for i, e in enumerate(p.get("historique", []))
                 if cible in normaliser(e["question"] + " " + e["reponse"])]
    return list(reversed(trouvees))


def supprimer_entrees(nom, entrees):
    """Supprime les entrées trouvées par chercher_memoire ; renvoie leur nombre."""
    data = _lire()
    p = data.get(nom, {})
    for genre, cle in (("souvenir", "souvenirs"), ("échange", "historique")):
        positions = {i for g, i, _ in entrees if g == genre}
        if positions and cle in p:
            p[cle] = [e for i, e in enumerate(p[cle]) if i not in positions]
    _ecrire(data)
    return len(entrees)


def oublier_dernier(nom):
    """Oublie le dernier échange (« oublie ça ») de l'historique ; renvoie sa question, ou None."""
    data = _lire()
    p = data.get(nom, {})
    historique = p.get("historique", [])
    if not historique:
        return None
    dernier = historique.pop()
    _ecrire(data)
    return dernier["question"]


def oublier_souvenir(nom, mots):
    """Retire les souvenirs qui contiennent les mots donnés ; renvoie le nombre retiré."""
    data = _lire()
    souvenirs = data.get(nom, {}).get("souvenirs", [])
    gardes = [s for s in souvenirs if normaliser(mots) not in normaliser(s["texte"])]
    if nom in data:
        data[nom]["souvenirs"] = gardes
        _ecrire(data)
    return len(souvenirs) - len(gardes)


def humeur_recente(nom):
    p = fiche(nom)
    if not p.get("humeur"):
        return None
    jours = (datetime.date.today() - datetime.date.fromisoformat(p["humeur_date"])).days
    return p["humeur"] if jours <= HUMEUR_VALIDITE_JOURS else None


def resume(nom):
    """« Qu'est-ce que tu sais sur moi ? »"""
    p = fiche(nom)
    elements = []
    if p.get("age"):
        elements.append(f"tu avais {p['age']} ans le {p['age_note']}")
    if p.get("niveau"):
        elements.append(f"tu es en {p['niveau']}")
    if humeur_recente(nom):
        elements.append(f"récemment, tu te sentais {humeur_recente(nom)}")
    if p.get("tutoiement") is not None:
        elements.append("on se tutoie" if p["tutoiement"] else "on se vouvoie")
    if p.get("souvenirs"):
        elements.append("tu m'as demandé de retenir : " + ", ".join(a_la_deuxieme(s["texte"]) for s in p["souvenirs"]))
    n = len(p.get("historique", []))
    if n:
        elements.append("je garde notre dernier échange" if n == 1 else f"je garde nos {n} derniers échanges")
    if not elements:
        return f"Je ne sais encore presque rien de toi, {nom}."
    return (f"Voici ce que je sais de toi, {nom} : " + " ; ".join(elements) + ". Tout reste sur cet ordinateur. "
            "Dis « oublie ce que tu sais sur moi » pour tout effacer.")


# --- Tutoiement / vouvoiement ---------------------------------------------------------------------------------
# Les réponses d'Orion sont écrites au tutoiement ; on les convertit si la personne préfère le vouvoiement.
_VERBES = {"peux": "pouvez", "veux": "voulez", "es": "êtes", "as": "avez", "sais": "savez", "dis": "dites",
           "fais": "faites", "vas": "allez", "connais": "connaissez", "prends": "prenez", "réponds": "répondez",
           "souhaites": "souhaitez", "trouves": "trouvez", "préfères": "préférez", "parles": "parlez",
           "te sentais": "vous sentiez", "avais": "aviez", "étais": "étiez", "pourras": "pourrez",
           "m'as": "m'avez", "confirmes": "confirmez", "veux vraiment": "voulez vraiment"}
_IMPERATIFS = {"Vérifie": "Vérifiez", "Demande": "Demandez", "Ouvre": "Ouvrez", "Recoupe": "Recoupez",
               "Donne": "Donnez", "Dis": "Dites", "Réponds": "Répondez", "Fais": "Faites", "Prends": "Prenez",
               "double-clique": "double-cliquez", "Méfie-toi": "Méfiez-vous", "vérifie": "vérifiez",
               "demande": "demandez", "recoupe": "recoupez", "ouvre": "ouvrez", "dis": "dites",
               "Pense": "Pensez", "Essaie": "Essayez", "Écoute": "Écoutez"}


def vouvoyer(texte):
    """Conversion pragmatique tu → vous, pour les tournures qu'emploie Orion."""
    for tu, vous in _IMPERATIFS.items():  # impératif : seulement en tête de phrase ou de membre de phrase
        texte = re.sub(rf"(^|[.:;!?,]\s+|«\s*){re.escape(tu)}(?=[\s,.!?-]|$)", lambda m: m.group(1) + vous, texte)
    for tu, vous in _VERBES.items():
        texte = re.sub(rf"\b([Tt])u {tu}\b", lambda m: ("V" if m.group(1) == "T" else "v") + f"ous {vous}", texte)
    remplacements = [(r"\bTu\b", "Vous"), (r"\btu\b", "vous"), (r"\bton\b", "votre"), (r"\bta\b", "votre"),
                     (r"\btes\b", "vos"), (r"\bTon\b", "Votre"), (r"\bTa\b", "Votre"), (r"\bTes\b", "Vos"),
                     (r"\btoi\b", "vous"), (r"\bte\b", "vous"), (r"\bt'", "vous "), (r"\bT'", "Vous "),
                     (r"\bpour toi\b", "pour vous")]
    for motif, rempl in remplacements:
        texte = re.sub(motif, rempl, texte)
    return texte


# Couleur de chaque personne (halo de l'hologramme quand Orion la reconnaît)
COULEURS = {"rouge": "#ff4d4d", "orange": "#ff9a3c", "jaune": "#ffe14d", "vert": "#4dff88", "turquoise": "#3ce0d0",
            "bleu": "#4d8bff", "violet": "#a86bff", "rose": "#ff6bc1", "blanc": "#f2f2f2", "or": "#ffcc33",
            "dore": "#ffcc33", "argent": "#c8d0d8", "marron": "#b07040", "corail": "#ff7f6b", "lavande": "#b9a6ff"}


def couleur(nom):
    return fiche(nom).get("couleur")
