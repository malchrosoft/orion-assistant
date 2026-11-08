# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Compréhension des demandes : règles simples + calcul + base de savoir (+ LLM local optionnel)."""
import ast
import contextlib
import datetime
import json
import math
import operator
import os
import random
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import bible, dossiers, espace, export, knowledge, meteo, minuteur, personnes, publications, systeme, web
from .conversation import Conversation
from .persona import presentation
from .texte import chiffres, normaliser, sans_accents

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

NOMBRES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
           "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
           "cinquante": 50, "soixante": 60, "cent": 100, "mille": 1000}

# Ordre important : expressions longues d'abord
OPERATEURS = [("multiplie par", "*"), ("divise par", "/"), ("puissance", "**"), ("au carre", "**2"),
              ("au cube", "**3"), ("racine carree de", "sqrt "), ("racine de", "sqrt "),
              ("plus", "+"), ("moins", "-"), ("fois", "*"), ("sur", "/"), ("x", "*")]

# Questions qui appellent un fait vérifiable : on cherche une source avant de laisser un modèle répondre
FACTUELLE = (r"\b(c est quoi|qu est ce que|qu est ce qu|qui est|qui etait|qui a (invente|ecrit|decouvert|cree)|"
             r"quand (a|est|etait|ont)|en quelle annee|combien (de|d|y a)|ou se trouve|definition|explique|"
             r"comment fonctionne|pourquoi (le|la|les|l)|quelle est la (capitale|population|distance|hauteur))\b")

METEO = r"\b(meteo|quel temps|va t il (pleuvoir|neiger|faire beau)|il va pleuvoir|previsions?)\b"
CAPACITES = json.loads((Path(__file__).parent / "data" / "capacites.json").read_text(encoding="utf-8"))
CAPACITES_TOT = (r"^comment (?:je |on |est ce qu on |faire pour |puis je |peut on |dois je |tu )?"
                 r"|\b(que|quoi|qu est ce que) (tu sais|sais tu|tu peux|peux tu) faire\b"
                 r"|\btu sais faire quoi\b|\btes (fonctions|capacites)\b|\ba quoi tu sers\b")
OUI = r"^(oui|ouais|ok|d accord|vas y|va s y|bien sur|volontiers|je veux bien|oui merci|si|fais le|c est parti|(tele)?charge)\b"
NON = r"^(non|pas la peine|laisse tomber|non merci|annule)\b"

DECISION = (r"\b(devrais je|dois je|faut il|vaut il mieux|est il preferable|tu me conseilles|"
            r"conseille moi|que choisir|lequel choisir|est ce une bonne idee)\b")

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def _evaluer(noeud):
    """Évaluation sûre d'une expression arithmétique (pas d'eval)."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in OPS:
        g, d = _evaluer(noeud.left), _evaluer(noeud.right)
        if isinstance(noeud.op, ast.Pow) and abs(d) > 100:
            raise ValueError("trop grand")
        return OPS[type(noeud.op)](g, d)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in OPS:
        return OPS[type(noeud.op)](_evaluer(noeud.operand))
    if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "sqrt" and len(noeud.args) == 1:
        return math.sqrt(_evaluer(noeud.args[0]))
    raise ValueError("expression non supportée")


def calculer(t):
    expr = re.sub(r"^.*?(combien (font|fait|ca fait)|calcule|resultat de)\s*", "", t)
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
    for mot, sym in OPERATEURS:
        expr = re.sub(rf"\b{mot}\b", f" {sym} ", expr)
    expr = " ".join(str(NOMBRES.get(m, m)) for m in expr.split())
    expr = re.sub(r"sqrt\s+([\d.]+)", r"sqrt(\1)", expr)
    if not re.search(r"\d", expr) or re.search(r"[a-z]", expr.replace("sqrt", "")):
        return None
    try:
        r = _evaluer(ast.parse(expr, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None
    r = round(r, 4)
    return str(int(r) if r == int(r) else r).replace(".", ",")


class Cerveau:
    def __init__(self, cfg, actions):
        self.cfg, self.actions = cfg, actions
        self.derniere_fiche = None
        self.en_attente = None        # action proposée, exécutée si l'utilisateur répond « oui »
        self.derniere_origine = None  # pour répondre à « quelle est ta source ? »
        self.ville_demandee = None        # phrase météo en attente de « pour quelle ville ? »
        self.symboliser = lambda libelle: None  # feuille qui s'écrit sur l'hologramme (branchée par la boucle vocale)
        self.derniere_reponse = None      # dernière réponse donnée : « fais-en un document Word »
        self.export_en_cours = False
        self.derniers_fichiers = []       # résultats de la dernière recherche de fichiers (« ouvre le premier »)
        self.minuteur = None              # compte à rebours en cours : {fin (monotonic), total, pour}
        self.duree_demandee = False       # Orion vient de demander « pour combien de temps ? »
        self.question_tutoiement = None   # nom de la personne à qui l'on vient de demander « on se tutoie ? »
        self.oubli_a_confirmer = None     # (nom, mots ou None pour « tout ») en attente d'un « oui »
        self.demande_enrolement = None    # prénom dont la boucle vocale doit enregistrer la voix
        self.conversation = Conversation(cfg)
        self.signaler = lambda message: None  # avancement des tâches longues (branché par la boucle vocale)
        self.a_recharger = False              # la boucle vocale recharge la configuration (voix, modèle…)
        self.retrait_voix = None          # prénom dont on attend la confirmation de retrait de la voix
        self.tutoiement_demande = set()   # une seule fois par session et par personne
        self.signaler_inconnu = False     # mode vocal : prévenir quand une voix n'est pas reconnue
        self.inconnu_signale = False
        self.alerte_espace_donnee = False  # « j'approche de ma limite » : une fois par session

    def repondre(self, phrase: str, locuteur: str):
        """Renvoie (texte à dire, tâche) ; tâche est une fonction à exécuter (état « exécution ») ou None.
        Ajoute à la réponse brute la relation avec la personne : tutoiement, mémoire locale, voix inconnue."""
        connu = locuteur != "invité"
        t = normaliser(phrase)

        # Confirmation du retrait d'une voix
        if self.retrait_voix:
            nom, self.retrait_voix = self.retrait_voix, None
            if re.search(OUI, t):
                from .voix import PROFILS
                import json
                profils = json.loads(PROFILS.read_text()) if PROFILS.exists() else {}
                profils.pop(nom, None)
                PROFILS.write_text(json.dumps(profils))
                return f"C'est fait, {nom} : je ne reconnaîtrai plus ta voix.", None
            if re.search(NON, t):
                return "D'accord, je garde ta voix.", None

        # Confirmation d'un oubli demandé juste avant
        if self.oubli_a_confirmer:
            nom, mots = self.oubli_a_confirmer
            self.oubli_a_confirmer = None
            if nom == locuteur and re.search(OUI, t):
                if mots is None:
                    personnes.oublier(nom)
                    return self._adapter("C'est fait. Comme pour Peter Parker, j'ai tout oublié de toi… "
                                         "sauf ta voix, pour pouvoir encore te reconnaître.", locuteur), None
                n = personnes.oublier_souvenir(nom, mots)
                return self._adapter("C'est oublié." if n else "Je n'avais rien retenu de tel.", locuteur), None
            if re.search(NON, t):
                return self._adapter("D'accord, je garde tout en mémoire.", locuteur), None

        # Réponse à « est-ce qu'on se tutoie ? »
        if self.question_tutoiement and re.search(OUI + "|" + NON, t):
            nom, self.question_tutoiement = self.question_tutoiement, None
            tutoie = bool(re.search(OUI, t))
            personnes.modifier(nom, tutoiement=tutoie)
            return ("Super, on se tutoie !" if tutoie else "Entendu, je vous vouvoierai."), None
        self.question_tutoiement = None

        if re.search(r"\b(recharge toi|recharge ta configuration|recharge tes reglages|relis tes reglages)\b", t):
            self.a_recharger = True
            return "D'accord, je recharge mes réglages.", None

        # --- Installer ce qui manque (voix naturelle, conversation) -------------------
        if re.search(r"\bce qu(i| il) te manque\b", t) or (re.search(r"\b(installe|telecharge|ajoute)s?\b", t) and re.search(
                r"\b(voix naturelle|ta voix|conversation|discuter|modele|tout)\b", t)):
            return self._installer_manquants(locuteur), None

        # --- Voix de la famille, à l'oral ---------------------------------------
        m = re.search(r"\b(?:memorise|enregistre|retiens|apprends) (?:ma|mon) voix\b(?:.*?\b(?:je suis|je m appelle|c est) (\w+))?", t)
        if m:
            prenom = (m.group(1) or "").capitalize() or (locuteur if connu else None)
            if not prenom:
                self.en_attente = None
                return "D'accord ! Dis-moi d'abord ton prénom : « mémorise ma voix, je suis… ».", None
            self.demande_enrolement = prenom
            return (f"D'accord {prenom}. Lis-moi cinq phrases à voix haute, l'une après l'autre, comme tu veux. "
                    "Je te dirai quand c'est fini."), None
        if re.search(r"\b(retire|supprime|efface|oublie) (ma|mon) (voix|empreinte)\b", t):
            if not connu:
                return "Je ne reconnais pas ta voix : il n'y a rien à retirer.", None
            self.retrait_voix = locuteur
            return f"Tu veux vraiment que j'oublie ta voix, {locuteur} ? Je ne te reconnaîtrais plus. Dis oui pour confirmer.", None
        m = re.search(r"^(?:je suis|je m appelle|moi c est|c est) (\w+)$", t)
        if m and m.group(1) not in ("la", "le", "ici", "moi", "toi", "pas", "content", "contente", "triste",
                                    "fatigue", "fatiguee", "malade", "en"):
            prenom = m.group(1).capitalize()
            if connu and normaliser(locuteur) == normaliser(prenom):
                return f"Oui, je t'ai reconnu à ta voix, {prenom} !", None

            def enroler():
                self.demande_enrolement = prenom
                return f"Lis-moi cinq phrases à voix haute, {prenom}, l'une après l'autre."
            self.en_attente = enroler
            if connu:
                return (f"Pourtant, je croyais entendre {locuteur}. Tu veux que j'enregistre ta voix sous le nom "
                        f"{prenom} ?"), None
            return f"Enchanté, {prenom} ! Tu veux que j'enregistre ta voix pour te reconnaître ensuite ?", None

        if re.search(r"\b(vouvoie moi|vouvoyez moi|on se vouvoie|ne me tutoie pas|vouvoyons nous)\b", t):
            if not connu:
                return "Je ne reconnais pas ta voix : je ne peux pas m'en souvenir pour toi.", None
            personnes.modifier(locuteur, tutoiement=False)
            return "Entendu, je vous vouvoierai désormais.", None
        if re.search(r"\b(tutoie moi|tutoyez moi|on se tutoie|tu peux me tutoyer|vous pouvez me tutoyer)\b", t):
            if not connu:
                return "Je ne reconnais pas ta voix : je ne peux pas m'en souvenir pour toi.", None
            personnes.modifier(locuteur, tutoiement=True)
            return "D'accord, on se tutoie !", None
        if re.search(r"\b(que sais tu de moi|qu est ce que tu sais (de|sur) moi|tu me connais)\b", t):
            return self._adapter(personnes.resume(locuteur) if connu else
                                 "Je n'ai pas reconnu ta voix, et je ne garde rien sur les personnes que je ne "
                                 "connais pas.", locuteur), None
        m = re.search(r"^(?:retiens|souviens toi|rappelle toi|memorise|n oublie pas) (?:que |qu )?(.+)$", t)
        if m and not re.search(r"\b(de|a) me rappeler\b", t):
            if not connu:
                return "Je ne reconnais pas ta voix : je ne peux rien retenir pour toi.", None
            souvenir = re.sub(r"^(?:retiens|souviens-toi|rappelle-toi|mémorise|n'oublie pas)\s+(?:que |qu')?", "",
                              phrase.strip(), flags=re.IGNORECASE).rstrip(" .")
            if not espace.place_pour(self.cfg, 10_000):
                return self._adapter(espace.refus(self.cfg), locuteur), None
            personnes.retenir(locuteur, souvenir)
            return self._adapter("C'est retenu, sans limite de temps : " + personnes.a_la_deuxieme(souvenir) + ".",
                                 locuteur), None
        m = re.search(r"^oublie (?:que |qu )(.+)$", t)
        if m and connu:
            self.oubli_a_confirmer = (locuteur, m.group(1))
            texte = re.sub(r"^\s*oublie\s+(?:que |qu')", "", phrase.strip(), flags=re.IGNORECASE).rstrip(" .?!")
            return self._adapter(f"Tu veux vraiment que j'oublie que {personnes.a_la_deuxieme(texte)} ? "
                                 "Dis oui pour confirmer.", locuteur), None
        if re.search(r"\b(oublie (tout )?ce que tu sais (de|sur) moi|oublie moi|oublie tout|efface (mes donnees|ma memoire))\b", t):
            if not connu:
                return "Je n'ai pas reconnu ta voix, et je ne garde rien sur les personnes que je ne connais pas.", None
            self.oubli_a_confirmer = (locuteur, None)
            return self._adapter("Attention : comme pour Peter Parker dans Spider-Man : No Way Home, je ne me "
                                 "souviendrais plus de rien te concernant — ni ce que tu m'as demandé de retenir, ni "
                                 "nos échanges. Seule ta voix resterait, pour te reconnaître. Tu confirmes ? Réponds "
                                 "oui ou non.", locuteur), None

        if re.search(r"\b(limite|espace|memoire|place)\b", t) and re.search(
                r"\b(augmente|diminue|change|modifie|regle|agrandis|reduis|passe)\b", t):
            return self._adapter("Ce réglage ne se change pas à la voix, par sécurité : passe par le panneau, onglet "
                                 "Réglages, ou par la commande orion limite.", locuteur), None
        # la place qu'occupe Orion (« tu prends combien de place ? ») ; l'espace libre de l'ordinateur est plus loin
        if re.search(r"\b(combien de place|quelle place|espace disque|combien d espace|ta memoire est pleine)\b", t) \
                and not re.search(r"\b(libre|disponible|reste|disques?|ordinateur|ordi|pc|mac)\b", t):
            o, l, r = espace.etat(self.cfg)
            return self._adapter(f"J'occupe {espace.mo(o)} sur les {espace.mo(l)} autorisés, "
                                 f"soit {r * 100:.0f} %.", locuteur), None

        prefixe = ""
        if not connu and self.signaler_inconnu and not self.inconnu_signale and not re.search(OUI + "|" + NON, t):
            self.inconnu_signale = True
            prefixe = "Je n'ai pas reconnu ta voix, je te réponds de façon générale. "
        if connu:
            accuse = personnes.apprendre(locuteur, phrase)
            if accuse:
                return self._adapter(accuse, locuteur), None

        reponse, tache = self._repondre(phrase, locuteur)
        if connu and re.search(r"^(bonjour|salut|coucou|bonsoir)\b", t):
            humeur = personnes.humeur_recente(locuteur)
            if humeur and humeur not in personnes.POSITIVES:
                reponse = f"{reponse} Tu te sens mieux ? L'autre jour, tu étais {humeur}."
        if tache:
            def tache_adaptee():
                texte = self._finaliser(prefixe + tache(), phrase, locuteur)
                return texte
            return None, tache_adaptee
        return self._finaliser(prefixe + reponse, phrase, locuteur), None

    def _fiche_pdf(self, sujet, renvois, cle=None):
        """Fiche PDF : base locale d'abord ; sinon Wikipédia, après accord (comme pour les réponses orales)."""
        from . import document
        a = self.actions
        fiche = knowledge.chercher(sujet)

        def produire(f):
            try:
                dossier = dossiers.chemin(self.cfg, cle)
                with self._redaction(f"la fiche sur {f['titre']}") as mesure:
                    chemin = document.generer(f, renvois, dossier)
            except OSError as e:
                return f"Je n'arrive pas à enregistrer la fiche : {e}."
            return self._document_pret(chemin, "la fiche", mesure["duree"])
        if fiche:
            if any(s["niveau"] == 0 for s in fiche["sources"] if s["consulte"]):
                fiche["avertissement"] = ("Attention : cette fiche provient d'une page internet non vérifiée. "
                                          "Recoupez-la avec une source sûre.")
            fiche["lectures"] = [s for s in fiche["sources"] if s["portee"] == "domaine"]
            fiche["sources"] = [s for s in fiche["sources"] if s["portee"] == "fiche"]
            return None, lambda: produire(fiche)

        def depuis_wikipedia():
            try:
                article = web.wikipedia(sujet)
            except Exception:
                return "Je n'arrive pas à joindre ma base externe. Vérifie la connexion internet."
            if not article:
                return "Je n'ai rien trouvé de fiable sur ce sujet."
            return produire({"titre": article["titre"], "contenu": article["contenu"], "domaine": "Wikipédia",
                             "avertissement": "Extrait de Wikipédia, encyclopédie collaborative (CC BY-SA 4.0) : "
                                              "vérifiez les points importants.",
                             "sources": [{"titre": f"Wikipédia, article « {article['titre']} »", "url": article["url"],
                                          "niveau": 1, "consulte": knowledge.aujourdhui()}]})
        if self._libre("wikipedia"):
            return None, depuis_wikipedia
        self.en_attente = depuis_wikipedia
        return "Je n'ai pas ce sujet dans ma mémoire locale. Puis-je consulter ma base de connaissance externe ?", None

    def _installer_manquants(self, locuteur):
        """À la voix : annonce la taille et demande l'accord ; la limite d'espace ne se change pas à l'oral."""
        from . import composants
        liste = composants.manquants(self.cfg)
        if not liste:
            return "J'ai déjà tout ce qu'il me faut."
        try:
            total = sum(o for _, o in composants.estimer(liste))
        except Exception:
            return "Je n'arrive pas à vérifier ce qu'il faut télécharger. Vérifie la connexion internet."
        quoi = " et ".join(composants.LIBELLES[g] for g, _ in liste)
        if espace.occupe() + total > espace.limite(self.cfg):
            return (f"Pour installer {quoi}, il me faut {espace.mo(total)}, plus que ma limite de "
                    f"{espace.mo(espace.limite(self.cfg))}. Cette limite se change dans le panneau : il y a un "
                    "bouton « Installer ce qui manque ».")

        def installer():
            self.signaler("Je commence l'installation.")
            try:
                composants.installer(self.cfg, liste, self.signaler)
            except Exception as e:
                return f"L'installation n'a pas abouti : {e}"
            self.a_recharger = True
            return "C'est terminé ! Tout est installé, et je l'utilise dès maintenant."
        self.en_attente = installer
        return f"Je peux installer {quoi} : cela fait {espace.mo(total)} à télécharger. Je m'en occupe ?"

    def _adapter(self, texte, locuteur):
        if locuteur != "invité" and personnes.fiche(locuteur).get("tutoiement") is False:
            return personnes.vouvoyer(texte)
        return texte

    def _finaliser(self, texte, phrase, locuteur):
        """Vouvoiement si besoin, mémoire locale, et une fois par session : « on se tutoie ? »."""
        if (not self.export_en_cours and texte and not texte.rstrip().endswith("?")
                and len(phrase.split()) > 2 and not re.search(OUI + "|" + NON, normaliser(phrase))):
            sources = [s for s in (self.derniere_fiche or {}).get("sources", []) if s.get("consulte")] \
                if self.derniere_origine in ("locale", "wikipedia") else []
            self.derniere_reponse = {"question": phrase, "contenu": texte, "sources": sources}
        self.export_en_cours = False
        if locuteur == "invité":
            return texte
        texte = self._adapter(texte, locuteur)
        if espace.place_pour(self.cfg, 2_000):  # l'historique n'est pas essentiel : sans place, on ne l'écrit pas
            personnes.noter_echange(locuteur, phrase, texte)
        if not self.alerte_espace_donnee and espace.alerte(self.cfg) and "plus de place" not in texte:
            self.alerte_espace_donnee = True
            texte += " " + self._adapter(espace.alerte(self.cfg), locuteur)
        if (personnes.fiche(locuteur).get("tutoiement") is None and locuteur not in self.tutoiement_demande
                and not self.en_attente and not texte.rstrip().endswith("?")):
            self.tutoiement_demande.add(locuteur)
            self.question_tutoiement = locuteur
            texte += f" Au fait, {locuteur}, est-ce qu'on se tutoie ?"
        return texte

    def _repondre(self, phrase: str, locuteur: str):
        """Réponse brute, toujours rédigée au tutoiement."""
        t = normaliser(phrase)
        for mot in self.cfg["mots_eveil"]:
            t = re.sub(rf"^(ok |dis |hey |salut )?{mot}\b[ ,]*", "", t)
        prenom = "" if locuteur == "invité" else f" {locuteur}"
        a = self.actions

        # --- Réponse à une proposition (« Puis-je consulter… ? ») -------------
        if self.duree_demandee:  # réponse à « pour combien de temps ? »
            self.duree_demandee = False
            d = minuteur.duree(chiffres(t))
            if d:
                return self._lancer_minuteur(d, locuteur)

        if self.ville_demandee is not None:  # réponse à « pour quelle ville ? »
            demande, self.ville_demandee = self.ville_demandee, None
            if re.search(NON, t):
                return "D'accord, pas de météo.", None
            if re.search(r"\b(devine|detecte|trouve|localise)|" + OUI, t):
                return None, lambda: self._meteo_devinee(demande)
            return None, lambda: self._meteo(re.sub(r"^(a|pour|sur) ", "", t), demande, retenir=True)

        attente, self.en_attente = self.en_attente, None
        if attente and re.search(OUI, t):
            return None, attente
        if attente and re.search(NON, t):
            return "D'accord, je n'y touche pas.", None
        if attente and len(t.split()) <= 2:  # « charge », « les coins » : mal entendu, on redemande
            self.en_attente = attente
            return "Pardon, c'est oui ou non ?", None

        # --- Sur les épaules de géants : comment d'autres ont déjà résolu ce problème (sources ouvertes) ---
        if re.search(r"\b(epaules? d(?:e|es) geants?|recherche approfondie|etat de l art|qui a deja resolu|"
                     r"comment (?:les autres|d autres|on) (?:ont|a) (?:deja )?resolu)\b", t) \
                and not re.match(r"comment (?:je|on|faire|tu)\b(?! .*resolu)", t):  # « comment je fais une… » : aide
            sujet = re.sub(r"^.*?\b(?:geants?|approfondie|de l art|resolu)\b\s*", "", t)
            sujet = re.sub(r"^(?:(?:sur|pour|de|du|des|a propos d[eu]?|concernant|le|la|les|l)\s+)+", "", sujet).strip()
            if len(sujet.split()) < 2:
                return "Sur quel problème veux-tu que je cherche comment d'autres l'ont résolu ?", None
            return self._geants(sujet)

        # --- Blagues : réserve locale relue (JokeAPI filtrée seulement si « blagues_internet » est activé) ---
        if re.search(r"\b(blagues?|histoire drole|fais moi rire|une autre)\b", t) and (
                "blague" in t or "rire" in t or "drole" in t or self.derniere_origine == "blague"):
            return self._blague(), None

        # --- Ce qu'Orion sait faire : réponse courte, ciblée selon la question ---
        if re.search(CAPACITES_TOT, t):
            reponse = self._capacites(t, generique=not t.startswith("comment"))
            if reponse:
                return reponse, None

        # --- Compte à rebours (interne à Orion, affiché sur l'hologramme) ---
        if re.search(r"\b(compte a rebours|minuteur|minuterie|chrono|timer)\b", t):
            if re.search(r"\b(annule|arrete|stop|supprime|enleve)", t):
                if not self.minuteur:
                    return "Il n'y a pas de compte à rebours en cours.", None
                self.minuteur = None
                return "Compte à rebours annulé.", None
            d = minuteur.duree(chiffres(t))
            if d:
                return self._lancer_minuteur(d, locuteur)
            if self.minuteur and re.search(r"\b(reste|combien|ou en)", t):
                restant = self.minuteur["fin"] - time.monotonic()
                return f"Il reste {minuteur.en_mots(restant)}.", None
            self.duree_demandee = True
            return "Pour combien de temps ?", None

        # --- Ordinateur (lecture seule) : disques, espace, système, versions, fichiers ---
        reponse = self._ordinateur(t)
        if reponse:
            return reponse

        if re.search(r"\b(ta source|tes sources|d ou tu tiens|d ou ca vient|d ou viennent|"
                     r"ou as tu trouve|ou tu as trouve|qui te l a dit)\b", t):
            return self._annoncer_source(), None

        # --- Crédits ----------------------------------------------------------
        if re.search(r"\bcredits?\b", t) and re.search(r"\b(pdf|document|genere|imprime|fichier)\b", t):
            cle = dossiers.trouver(self.cfg, t) if re.search(r"\b(dans|vers)\b", t) else None

            def generer():
                from .credits import generer_pdf
                try:
                    chemin = generer_pdf(dossiers.chemin(self.cfg, cle) / "Orion-credits.pdf")
                except OSError as e:
                    return f"Je n'arrive pas à enregistrer le document : {e}."
                a.ouvrir_lien(chemin.as_uri())
                return "Voilà la liste complète des crédits, en PDF."
            return None, generer
        cle = dossiers.trouver(self.cfg, t) if re.search(r"\b(dans|vers)\b", t) else None
        t_sujet = re.sub(rf"\s+(?:dans|vers) (?:le dossier |mon dossier |mes )?{normaliser(cle)}\b", "", t) if cle else t
        # document tiré de la réponse précédente : « fais-en un document Word », « exporte ça en HTML »
        if re.search(r"\b(fais|fait|genere|cree|exporte|enregistre|mets|transforme|prepare)\b", t) and re.search(
                r"\b(document|fichier|word|docx|markdown|html|page web|pdf)\b", t) and (
                re.search(r"\b(en|ca|cela|ta reponse|la reponse|ce que tu (?:viens de|as) dit|de tout ca)\b", t)
                and not re.search(r"\b(?:sur|a propos de|concernant) \w+", t)):
            return self._exporter(export.format_demande(t), cle)

        m = re.search(r"\b(?:fiche|document|pdf|resume)\b.*?\b(?:sur|de|du|des|a propos de|concernant) (?:la |le |les |l )?(.+?)(?: avec (?:des )?renvois?| en pdf)*$", t_sujet)
        if m and re.search(r"\b(pdf|fiche|document)\b", t) and re.search(r"\b(fais|fait|genere|cree|prepare|imprime|donne)\b", t):
            return self._fiche_pdf(m.group(1), bool(re.search(r"\brenvois?\b", t)), cle)
        if re.search(r"\b(credits?|bibliotheques?|librairies?|composants?|logiciels? libres?|"
                     r"qui t a (fait|programme|developpe)|avec quoi (tu es|es tu) fait)\b", t):
            from .credits import enoncer
            return enoncer(t), None

        # --- Politesse ------------------------------------------------------
        if not t:
            return f"Oui{prenom} ?", None
        if re.search(r"^(bonjour|salut|coucou|hello|bonsoir)\b", t):
            return random.choice([f"Bonjour{prenom} !", f"Salut{prenom}, que puis-je faire ?"]), None
        if re.search(r"\b(qui suis je|qui je suis|tu me reconnais|qui parle|tu sais qui (je suis|c est))\b", t):
            return (f"Tu es{prenom}." if prenom else "Je ne reconnais pas ta voix. "
                    "Tu peux l'enregistrer avec la commande enroler."), None
        if re.search(r"\b(je vais (me coucher|dormir)|bonne nuit|a demain|je vais au lit)\b", t):
            return random.choice([f"Bonne nuit{prenom}, dors bien !", f"Bonne nuit{prenom}. À demain !"]), None
        if re.search(r"\b(qui es tu|comment tu t appelles|ton nom|presente toi|presentez vous|tu es qui)\b", t):
            return presentation(self.cfg), None
        if re.search(r"\b(merci)\b", t):
            return random.choice(["Avec plaisir.", "De rien !", "À ton service."]), None
        if re.search(r"\b(au revoir|a plus)\b", t):
            return f"À bientôt{prenom}.", None

        # --- Musique --------------------------------------------------------
        if re.search(r"\b(musique|morceau|chanson|spotify|aimp|playlist|joue|mets)\b", t):
            lecteur = "spotify" if "spotify" in t else "aimp" if "aimp" in t else None
            if re.search(r"\b(suivant|suivante|passe|next)\b", t):
                cmd = "suivant"
            elif re.search(r"\b(precedent|precedente|reviens)\b", t):
                cmd = "precedent"
            elif re.search(r"\b(pause)\b", t):
                cmd = "pause"
            elif re.search(r"\b(arrete|stop|coupe)\b", t):
                cmd = "stop"
            else:
                cmd = "jouer"
            m = re.search(r"\b(?:joue|mets|lance|ecouter)\s+(?!la musique|de la musique|spotify|aimp)(.+?)"
                          r"(?:\s+sur\s+spotify)?$", t)
            recherche = m.group(1) if m and cmd == "jouer" and lecteur == "spotify" else None
            return None, lambda: a.musique(cmd, lecteur, recherche)
        if re.search(r"\b(suivant|morceau d apres)\b", t):
            return None, lambda: a.musique("suivant")
        if re.search(r"\b(pause|reprends)\b", t):
            return None, lambda: a.musique("pause")

        # --- Volume / applis --------------------------------------------------
        if re.search(r"\bvolume\b", t) or re.search(r"\b(monte|baisse|augmente|diminue|coupe|remets)\w* (le |du )?son\b", t):
            if re.search(r"\b(coupe|muet)\b", t):
                return None, lambda: a.volume("muet")
            sens = "moins" if re.search(r"\b(baisse|moins|diminue)\b", t) else "plus"
            return None, lambda: a.volume(sens)
        m = re.search(r"\b(?:ouvre|lance|demarre)\s+(?:le |la |l )?(.+)$", t)
        if m and (bible.est_biblique(t) or re.search(r"\b(cahier|tour de garde|programme|reunion)\b", t)):
            m = None  # « ouvre le cahier de la semaine » : une publication, pas une application
        if m:
            appli = m.group(1).replace("bloc notes", "bloc-notes")
            return None, lambda: a.ouvrir(appli)
        m = re.search(r"\b(?:cherche|recherche)\s+(?!dans (?:mes|les) publications|(?:la |une |des )?publications?\b)(.+?)(?:\s+sur (internet|wikipedia|le web))?$", t)
        if m:
            return None, lambda: a.recherche_web(m.group(1))

        if re.search(r"\b(apprends|retiens|ajoute une source|ajoute une reference)\b", t):
            return ("Donne-moi le lien dans le panneau d'Orion ou avec la commande apprendre. "
                    "Je le lirai, mais je considérerai toujours ce qui vient d'internet comme non vérifié."), None

        # --- Heure / date / calcul ------------------------------------------
        now = datetime.datetime.now()
        if re.search(r"\b(quelle heure|l heure)\b", t):
            return f"Il est {now.hour} heure{'s' if now.hour > 1 else ''} {now.minute:02d}.", None
        if re.search(r"\b(quel jour|la date|on est quel)\b", t):
            return f"Nous sommes le {JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}.", None
        if re.search(r"\b(combien|calcule|resultat)\b", t) or re.search(r"\d\s*(plus|moins|fois|x|divise)\s*\d", t):
            r = calculer(t)
            if r is not None:
                return f"Ça fait {r}.", None

        # --- Météo : dite d'après Open-Meteo ; La Chaîne Météo ouverte à l'écran sur demande ---
        if re.search(r"\bchanger? (de |ma )ville\b", t):
            self.ville_demandee = ""
            return "Quelle ville ? Ou dis « devine » pour que je la trouve d'après ta connexion.", None
        if re.search(METEO, t):
            ville = meteo.ville_dans(t)
            if ville or self.cfg.get("ville_meteo"):
                return None, lambda: self._meteo(ville or self.cfg["ville_meteo"], t)
            self.ville_demandee = t
            return ("Pour quelle ville ? Je peux aussi la deviner d'après ta connexion internet, "
                    "si tu me dis « devine ».", None)

        # --- Publications jw.org : recherche par l'utilisateur dans le site, puis lien de téléchargement ---
        m = re.search(r"\b(?:cherche|trouve)\b.*\bpublications?\b\s+(?:sur |de |du |des |a propos d[eu]? )?(.+)$", t)
        if m and not re.search(r"\bdans (?:mes|les) publications\b", t):
            sujet = m.group(1)
            a.ouvrir_lien(publications.RECHERCHE + urllib.parse.quote(sujet))
            return ("Je t'ouvre la recherche de jw.org. Choisis la publication, copie son lien de téléchargement, "
                    "puis dis-moi « télécharge le lien copié »."), None
        if re.search(r"\b(telecharge|recupere)\b.*\blien\b", t):
            return self._telecharger_lien(publications.presse_papiers())

        # --- Publications officielles (fichiers EPUB, téléchargement autorisé), après accord sur la taille ---
        if re.search(r"\b(telecharge|recupere|enregistre|procure)", t) and publications.demande(t):
            pubs = [p for p in (publications.chercher(*d) for d in publications.demande(t)) if p]
            if not pubs:
                return "Je ne trouve pas cette publication : elle n'est peut-être pas encore parue.", None
            cle = dossiers.trouver(self.cfg, t) if re.search(r"\b(dans|vers)\b", t) else None
            return self._proposer_publications(pubs, cle)

        # --- Couleur de la personne (halo de l'hologramme) ---
        m = re.search(r"\b(?:ma couleur|choisis|prends|mets)\b.*?\b(" + "|".join(personnes.COULEURS) + r")\b", t)
        if m and re.search(r"\bcouleur\b|\bpour moi\b", t):
            if locuteur == "invité":
                return "Je ne reconnais pas encore ta voix : enregistre-la d'abord pour avoir ta couleur.", None
            personnes.modifier(locuteur, couleur=personnes.COULEURS[m.group(1)])
            return f"C'est noté{prenom} : ton halo sera {m.group(1)} quand je te reconnais.", None

        # --- Recherche par thème dans les publications téléchargées (index local) ---
        m = re.search(r"\b(?:que dit la bible|ce que dit la bible|versets?|textes? du jour|cherche dans (?:mes|les) "
                      r"publications)\b.*?\b(?:sur|a propos d[eu]?|parlant d[eu]?|qui parlen?t? d[eu]?|parlait d[eu]?)"
                      r"\s+(?:l |la |le |les |d )?(.+)$", t)
        if m and not bible.reference(chiffres(t)):
            return self._chercher_publications(m.group(1), t)

        # --- Questions bibliques : base externe, source donnée seulement sur demande ---
        self.derniere_fiche = None
        if bible.est_biblique(t):
            lien = bible.lien(phrase)
            code_verset = bible.reference(chiffres(t))
            if code_verset:  # verset cité : d'abord la Bible téléchargée
                return self._verset(code_verset, chiffres(t), lien)
            r = bible.rubrique(t)
            if r and r[0] == "jour":  # texte du jour : d'abord le livret téléchargé, sinon proposition
                return self._texte_du_jour(r[1], lien)
            if r and r[0] == "semaine":  # réunions : le cahier ou la Tour de Garde d'étude, en EPUB
                return self._publication_de_la_semaine(r[1], t, lien)
            # question biblique générale : d'abord les publications téléchargées (index local)
            publications.indexer(self._dossiers_publications())
            trouves = publications.rechercher(phrase)
            if trouves:
                self.derniere_origine = "bible"
                return " ".join(f"{lieu} : {texte}" for lieu, texte in trouves[:2]), None
            if not publications.fichier_local("nwt", self._dossiers_publications()):
                bible_epub = publications.chercher("nwt")
                if bible_epub:
                    return self._proposer_publications(
                        [bible_epub], ouvrir=False, puis=lambda: self._chercher_publications(phrase, "bible")[0],
                        question="Je n'ai pas encore la Bible pour chercher. Je la télécharge ({taille}) ?")

            def ouvrir_bible():
                a.ouvrir_lien(lien)
                self.derniere_origine = "bible"
                return "Voilà, je t'affiche la réponse à l'écran."
            if self._libre("jw"):
                return None, ouvrir_bible
            self.en_attente = ouvrir_bible
            return "Puis-je consulter ma base de connaissance externe ?", None

        if re.search(r"\b(sais tu|tu sais|est ce que tu (sais|peux)|peux tu|tu peux|tu es capable)\b", t):
            reponse = self._capacites(t, generique=False)
            if reponse:
                return reponse, None

        # --- Savoir sourcé (principes « shoulders of giants ») ------------------
        decision = re.search(DECISION, t)
        fiche = knowledge.chercher(t)
        self.derniere_fiche = fiche
        if fiche:
            self.derniere_origine = "locale"
            return self._reponse_sourcee(fiche, decision), None
        if decision:
            return "Je n'ai pas de source fiable pour t'aider à décider ça. Demande à quelqu'un du métier.", None

        # --- Base externe : Wikipédia, après accord ----------------------------
        def consulter_wikipedia():
            try:
                article = web.wikipedia(phrase)
            except Exception:
                return "Je n'arrive pas à joindre ma base externe. Vérifie la connexion internet."
            if not article:
                return "Je n'ai rien trouvé de fiable sur ce sujet."
            self.derniere_origine = "wikipedia"
            self.derniere_fiche = {"titre": article["titre"], "contenu": article["contenu"], "domaine": "web",
                                   "sources": [{"titre": f"Wikipédia — {article['titre']}", "url": article["url"],
                                                "niveau": 1, "consulte": knowledge.aujourdhui(),
                                                "portee": "fiche"}]}
            return (f"{article['contenu']} Source : Wikipédia, article {article['titre']}. "
                    "C'est une encyclopédie collaborative : vérifie les points importants.")
        # Question factuelle → d'abord une source (Wikipédia, après accord)
        if re.search(FACTUELLE, t):
            if self._libre("wikipedia"):
                return None, consulter_wikipedia
            self.en_attente = consulter_wikipedia
            return "Je n'ai pas ça dans ma mémoire locale. Puis-je consulter ma base de connaissance externe ?", None

        # --- Discussion libre : modèle local uniquement (rien ne sort de l'ordinateur) ------
        if self.conversation.local_disponible():
            r = self.conversation.repondre_local(phrase, locuteur)
            if r:
                self.derniere_origine = "conversation_locale"
                return r, None
        return random.choice(["Je ne sais pas encore discuter de ça.",
                              "Je ne sais pas encore répondre à ça. Pour discuter plus librement, on peut m'ajouter "
                              "un modèle de conversation dans le panneau, onglet Réglages."]), None

    def _meteo(self, ville, demande="", retenir=False):
        """Dit la météo de `ville` (ou l'affiche si on demande à la voir) ; la ville donnée en réponse à
        « pour quelle ville ? » est retenue (changeable à la voix)."""
        self.derniere_origine = "meteo"
        if re.search(r"\b(montre|affiche|ouvre|voir)\b", demande):
            self.actions.ouvrir_lien("https://www.google.com/search?q="
                                     + urllib.parse.quote(f"La Chaîne Météo {ville}"))
            texte = f"Voilà la météo pour {ville.title()}, à l'écran."
        else:
            try:
                texte = meteo.bulletin(ville, demande)
            except Exception:
                return "Je n'arrive pas à joindre le service météo. Vérifie la connexion internet."
            if not texte:
                self.ville_demandee = demande
                return f"Je ne trouve pas la ville {ville}. Tu peux la redire ?"
        if retenir and ville != self.cfg.get("ville_meteo"):
            from .config import sauver
            self.cfg["ville_meteo"] = ville
            sauver(self.cfg)
            texte += " Je retiens cette ville ; pour en changer, dis « change ma ville »."
        return texte

    def _meteo_devinee(self, demande=""):
        """Ville estimée d'après l'adresse internet (service ipapi.co), seulement sur demande explicite."""
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    "https://ipapi.co/json/", headers={"User-Agent": "Orion-assistant/1.0"}), timeout=10) as r:
                ville = json.load(r).get("city")
        except Exception:
            ville = None
        if not ville:
            self.ville_demandee = demande
            return "Je n'arrive pas à deviner ta ville. Dis-moi laquelle ?"
        return f"D'après ta connexion, tu es vers {ville}. " + self._meteo(normaliser(ville), demande, retenir=True)

    def _verset(self, code, t, lien):
        """Lit le verset dans la Bible téléchargée ; sinon propose de la télécharger ; sinon l'ouvre."""
        livre, chapitre, debut = bible.LIVRES[int(code[:2]) - 1], int(code[2:5]), int(code[5:])
        # « 3 à 5 », « 3 et 4 » (le « et » disparaît à la conversion des nombres : « 21 3 4 »)
        m = re.search(rf"\b{chapitre}\D+{debut}\s*(?:a|au|jusqu a|et)?\s*(?:versets?\s*)?(\d+)\b", t)
        fin = int(m.group(1)) if m and int(m.group(1)) > debut else None
        nom = f"{bible.nom_livre(livre)} {chapitre}, {'versets' if fin else 'verset'} {debut}{f' à {fin}' if fin else ''}"
        self.derniere_origine = "bible"
        epub = publications.fichier_local("nwt", self._dossiers_publications())
        texte = publications.verset(epub, livre, chapitre, debut, fin) if epub else None
        if texte:
            return f"{nom} : {texte}", None

        def ouvrir():
            self.actions.ouvrir_lien(lien)
            return "Je n'ai pas trouvé ce verset dans la Bible téléchargée : je te l'affiche à l'écran."
        pub = None if epub else publications.chercher("nwt")
        if not pub:
            return None, ouvrir

        def telecharger_puis_lire():
            try:
                publications.telecharger(pub, dossiers.chemin(self.cfg))
            except OSError:
                return ouvrir()
            return self._verset(code, t, lien)[0] or ouvrir()
        self.en_attente = telecharger_puis_lire
        return (f"Je n'ai pas encore la Bible dans tes documents. Je la télécharge "
                f"({espace.mo(pub['octets'])}) pour te lire ce verset ?"), None

    def _chercher_publications(self, sujet, t):
        """Lit les deux passages les plus proches du sujet (Bible, ou textes du jour si on les demande)."""
        self.derniere_origine = "bible"
        publications.indexer(self._dossiers_publications())  # rapide : seuls les nouveaux fichiers sont lus
        source = ("es" if re.search(r"\btextes? du jour\b", t) else
                  "nwt" if re.search(r"\b(bible|versets?)\b", t) else None)
        trouves = publications.rechercher(sujet, source)
        if not trouves:
            return (f"Je ne trouve rien sur {sujet} dans tes publications téléchargées. Pour la Bible, "
                    "demande-moi « télécharge la Bible »."), None
        if source == "es":
            lieu, texte = trouves[0]
            texte = re.sub(r"\s*\[…\]\s*", " ", texte).replace("[", "").replace("]", "")
            return f"Le {lieu[len('texte du '):]} en parlait : {texte}", None
        return " ".join(f"{lieu} : {texte}" for lieu, texte in trouves[:2]), None

    def _telecharger_lien(self, lien):
        """Lien de téléchargement jw.org copié par l'utilisateur → EPUB proposé, puis retenu par son titre."""
        d = publications.depuis_lien(lien) if "jw.org" in lien else None
        if not d:
            return ("Je ne trouve pas de lien de téléchargement jw.org copié. Sur la page de la publication, "
                    "ouvre la fenêtre de téléchargement et copie le lien de l'EPUB."), None
        pub = publications.chercher(*d)
        if not pub:
            return "Cette publication n'existe pas en EPUB en français.", None
        publications.retenir(pub, *d)
        return self._proposer_publications([pub])

    def _proposer_publications(self, pubs, cle=None, ouvrir=True, puis=None, question=None):
        """Annonce la taille des EPUB, puis (sur « oui ») les télécharge, les ouvre ou enchaîne sur `puis`."""
        titres = " et ".join(f"« {p['titre']} »" for p in pubs)
        taille = espace.mo(sum(p["octets"] for p in pubs))

        def telecharger():
            try:
                for pub in pubs:
                    chemin = publications.telecharger(pub, dossiers.chemin(self.cfg, cle))
                    if ouvrir:
                        self.actions.ouvrir_lien(chemin.as_uri())
            except OSError as e:
                return f"Le téléchargement n'a pas abouti : {e}."
            self.derniere_origine = "bible"
            return puis() if puis else f"Voilà {titres}, dans le dossier {cle or dossiers.cle_par_defaut(self.cfg)}."
        self.en_attente = telecharger
        if question:
            return question.format(titres=titres, taille=taille), None
        return (f"{titres} {'font' if len(pubs) > 1 else 'fait'} {taille}"
                f"{' en tout' if len(pubs) > 1 else ''}. Je {'les' if len(pubs) > 1 else 'le'} télécharge ?"), None

    def _publication_de_la_semaine(self, date, t, lien):
        """Réunion de semaine → cahier Vie et ministère ; week-end → Tour de Garde d'étude (parue deux mois
        avant). Ouvre le fichier déjà téléchargé, sinon propose de le télécharger ; la page web en dernier."""
        if re.search(r"\b(tour de garde|week end|weekend|dimanche|samedi|etude de la tour)\b", t):
            mois = date.replace(day=1) - datetime.timedelta(days=1)
            mois = mois.replace(day=1) - datetime.timedelta(days=1)  # deux mois plus tôt
            code, numero = "w", f"{mois.year}{mois.month:02d}"
        else:
            code, numero = "mwb", f"{date.year}{date.month - (date.month + 1) % 2:02d}"
        self.derniere_origine = "bible"
        ouvrir = bool(re.search(r"\b(ouvre|montre|affiche)\b", t))

        def lire_ou_ouvrir(chemin):
            if code == "mwb" and not ouvrir:  # le programme de la semaine, lu à voix haute
                r = publications.programme_semaine(chemin, date)
                if r:
                    return f"Programme de la semaine du {r[0]}. " + ". ".join(r[1]) + "."
            self.actions.ouvrir_lien(chemin.as_uri())
            return "Je t'ouvre " + ("le cahier Vie et ministère." if code == "mwb" else "La Tour de Garde d'étude.")
        nom = f"{code}_F_{numero}.epub"
        for dossier in self._dossiers_publications():  # déjà téléchargé : rien à demander au site
            if (dossier / nom).exists():
                return lire_ou_ouvrir(dossier / nom), None
        pub = publications.chercher(code, numero)
        if not pub:
            self.actions.ouvrir_lien(lien)
            return "Je ne trouve pas encore la publication de cette semaine : je t'affiche la page.", None
        return self._proposer_publications([pub], ouvrir=False, puis=lambda: lire_ou_ouvrir(
            next(d / pub["nom"] for d in self._dossiers_publications() if (d / pub["nom"]).exists())))

    def _dossiers_publications(self):
        return [Path(os.path.expanduser(c)) for c in dossiers.liste(self.cfg).values()]

    def _texte_du_jour(self, date, lien):
        """Lit le texte du jour dans « Examinons les Écritures » téléchargé ; s'il manque, propose de le
        télécharger ; la page web n'est ouverte qu'en dernier recours."""
        code = f"es{date.year % 100:02d}"
        epub = publications.fichier_local(code, self._dossiers_publications())
        self.derniere_origine = "bible"
        if epub:
            r = publications.texte_du_jour(epub, date)
            if r:
                titre, verset, commentaire = r
                commentaire = re.sub(r"\s*\b[a-z]{1,3}\d{2}\.\d{2}\b.*$", "", commentaire)  # référence finale
                texte = f"Texte du {titre[0].lower() + titre[1:]}. {verset} {commentaire}"
                return re.sub(r"\s*\[…\]\s*", " ", texte).replace("[", "").replace("]", ""), None
        pub = publications.chercher(code)

        def ouvrir():
            self.actions.ouvrir_lien(lien)
            return "Je n'ai pas le texte dans mes publications : je te l'affiche à l'écran."
        if not pub:
            return None, ouvrir

        def telecharger_puis_lire():
            try:
                publications.telecharger(pub, dossiers.chemin(self.cfg))
            except OSError:
                return ouvrir()
            return self._texte_du_jour(date, lien)[0] or ouvrir()
        self.en_attente = telecharger_puis_lire
        return (f"Je n'ai pas encore « {pub['titre']} » dans tes documents. Je le télécharge "
                f"({espace.mo(pub['octets'])}) pour te le lire ?"), None

    def _ordinateur(self, t):
        """Questions sur l'ordinateur local, sans rien modifier ; None si la phrase n'en est pas une."""
        if self.derniers_fichiers and (m := re.search(r"\bouvre (?:le |la )?(premier|1|deuxieme|second|2|"
                                                     r"troisieme|3)\b", t)):
            rang = {"premier": 0, "1": 0, "deuxieme": 1, "second": 1, "2": 1, "troisieme": 2, "3": 2}[m.group(1)]
            if rang < len(self.derniers_fichiers):
                chemin = self.derniers_fichiers[rang]
                self.actions.ouvrir_lien((chemin if chemin.is_dir() else chemin.parent).as_uri())
                return f"Je t'ouvre le dossier où se trouve {chemin.name}." if not chemin.is_dir() \
                    else f"Je t'ouvre le dossier {chemin.name}.", None
        m = re.search(r"\b(?:cherche|trouve|ou est|ou sont|ou se trouve)\b.*?\b(fichiers?|documents?|dossiers?|"
                      r"repertoires?)\b\s+(?:qui s appelle |nomme |appele |de |du |des |sur )?(.+)$", t)
        if m:
            dossier = m.group(1).startswith(("dossier", "repertoire"))
            self.derniers_fichiers = systeme.chercher(m.group(2), dossiers=dossier)
            return systeme.decrire(self.derniers_fichiers, dossier), None
        if re.search(r"\b(espace|place)\b.*\b(libre|disque|disponible|reste|restante)\b|"
                     r"\b(reste|libre|disponible)\b.*\b(place|espace)\b", t):
            return systeme.espace_libre(), None
        if re.search(r"\b(quels?|combien de|liste)\b.*\b(disques?|lecteurs?|partitions?|volumes?)\b", t):
            return systeme.liste_disques(), None
        if re.search(r"\b(ta version|quelle version|version (?:de|du|d) )", t):
            return systeme.versions(), None
        if re.search(r"\b(infos?|informations?|caracteristiques)\b.*\b(systeme|ordinateur|ordi|pc|mac|poste|"
                     r"machine)\b|\bquel (?:systeme|processeur)\b|\bcombien de (?:memoire|ram)\b", t):
            return systeme.infos(), None
        return None

    def _geants(self, sujet):
        """Propose la recherche (internet, avec accord), puis dit la synthèse et ouvre la fiche PDF."""
        from . import document, geants

        def chercher():
            r = geants.rechercher(sujet, self.conversation, self.signaler)
            self.derniere_origine = "geants"
            if r["lignee"] or r["wikipedia"]:
                try:
                    with self._redaction("la fiche de recherche") as mesure:
                        chemin = document.generer(geants.fiche(r), True, dossiers.chemin(self.cfg))
                    return geants.a_dire(r).replace(" Je t'ai préparé une fiche avec la lignée complète et les "
                                                    "sources.", "") + " " + self._document_pret(
                        chemin, "la fiche avec la lignée et les sources", mesure["duree"])
                except OSError:
                    pass
            self.signaler("")
            return geants.a_dire(r)
        if self._libre("geants"):
            return None, chercher
        self.en_attente = chercher
        return (f"Je vais chercher comment d'autres ont déjà résolu « {sujet} », dans des sources ouvertes en "
                "ligne : Wikipédia et le catalogue scientifique OpenAlex. J'y vais ?"), None

    @contextlib.contextmanager
    def _redaction(self, libelle, format_="PDF"):
        """Pendant qu'Orion rédige : il l'annonce, et une feuille s'écrit sur l'hologramme (1,5 s au moins,
        même si le fichier est prêt plus vite, pour qu'on voie ce qu'il fait)."""
        debut, mesure = time.monotonic(), {}
        self.symboliser(format_)
        self.signaler(f"Je rédige {libelle}…")
        try:
            yield mesure
        finally:
            mesure["duree"] = time.monotonic() - debut  # temps réel de rédaction, avant l'attente d'affichage
            time.sleep(max(0.0, 1.5 - mesure["duree"]))
            self.symboliser(None)
            self.signaler("")

    def _document_pret(self, chemin, libelle, duree):
        """Annonce le document et propose de l'ouvrir ; de temps en temps, Orion se vante de sa rapidité."""
        dossier = "ton dossier personnel" if chemin.parent == Path.home() else f"le dossier {chemin.parent.name}"
        ms = round(duree * 1000)
        temps = ("moins d'une milliseconde" if ms < 1 else f"{ms} milliseconde{'s' if ms > 1 else ''}" if duree < 1
                 else f"{duree:.1f} secondes".replace(".", ","))
        f = libelle.startswith("la ")  # « la fiche », « la page web » : accords au féminin
        e, il, Libelle = ("e" if f else ""), ("Elle" if f else "Il"), libelle[:1].upper() + libelle[1:]
        if random.random() < 0.35:
            texte = random.choice([
                f"Et voilà : {libelle} rédigé{e} en {temps}, pas mal, non ? {il} s'appelle {chemin.name}, dans {dossier}.",
                f"{temps[:1].upper() + temps[1:]} chrono pour {libelle} ! C'est {chemin.name}, rangé{e} dans {dossier}.",
                f"Je n'ai pas traîné : {temps}. {Libelle} s'appelle {chemin.name}, dans {dossier}."])
        else:
            texte = f"{Libelle} est prêt{e} : {chemin.name}, dans {dossier}."
        self.en_attente = lambda: (self.actions.ouvrir_lien(chemin.as_uri()), "Je te l'ouvre.")[1]
        return texte + " Je l'ouvre ?"

    def _exporter(self, format_, cle=None):
        """Enregistre la dernière réponse dans le format demandé, puis l'ouvre."""
        r = self.derniere_reponse
        if not r:
            return "Pose-moi d'abord une question : j'en ferai ensuite un document.", None
        noms = {"docx": "le document Word", "md": "le fichier Markdown", "html": "la page web", "pdf": "le PDF",
                "pdf_pro": "le rapport PDF"}

        def creer():
            titre = re.sub(r"[?!.]+$", "", r["question"]).strip()
            doc = {"titre": titre[:1].upper() + titre[1:], **r}
            try:
                with self._redaction(noms[format_], "PDF PRO" if format_ == "pdf_pro" else format_.upper()) as mesure:
                    chemin = export.generer(doc, format_, dossiers.chemin(self.cfg, cle))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
                return f"Je n'arrive pas à enregistrer le document : {e}."
            self.export_en_cours = True
            return self._document_pret(chemin, noms[format_], mesure["duree"])
        return None, creer

    def _blague(self):
        from . import blagues
        question, chute = blagues.blague(self.cfg.get("blagues_internet", False))  # réserve relue par défaut
        self.derniere_origine = "blague"
        return f"{question} … {chute}" if chute else question

    def _capacites(self, t, generique=True):
        """Fiche de capacité la plus proche de la question (2 ou 3 phrases), ou un résumé très court."""
        mots = [m for m in t.split() if len(m) > 3]

        def proche(m, cles):  # « interromps » ~ « interrompre », « fichiers » ~ « fichier »
            return any(m[:5] == k[:5] for k in cles if len(k) > 3)
        notes = [(sum(proche(m, (c["motscles"] + " " + normaliser(c["titre"])).split()) for m in mots), c)
                 for c in CAPACITES]
        score, meilleure = max(notes, key=lambda n: n[0])
        if score and not re.search(r"\b(que|quoi|qu est ce que) (tu sais|sais tu|tu peux|peux tu)\b.*\bfaire\b"
                                   r"|\btes (fonctions|capacites)\b|\btu sais faire quoi\b", t):
            return meilleure["contenu"]
        if not generique:
            return None
        return ("Je t'écoute et je te réponds, je reconnais la famille, je gère la musique, la météo, les comptes "
                "à rebours, les fiches PDF, la Bible et tes publications, et je renseigne sur ton ordinateur. "
                "Demande-moi par exemple : « comment lancer un compte à rebours ? ».")

    def _lancer_minuteur(self, secondes, locuteur):
        remplace = " Il remplace le précédent." if self.minuteur else ""
        self.minuteur = {"fin": time.monotonic() + secondes, "total": secondes, "pour": locuteur}
        return f"C'est parti : {minuteur.en_mots(secondes)}.{remplace}", None

    def _libre(self, site):
        """Sites consultés sans demander l'accord (réglage « sites_libres ») ; rien n'en est stocké."""
        return site in self.cfg.get("sites_libres", [])

    SOURCE_BIBLIQUE = ("Pour les questions bibliques, ma base de connaissance externe est le site officiel "
                       "des Témoins de Jéhovah, JW.org, sa Bibliothèque en ligne wol.jw.org, "
                       "et l'application JW Library.")

    def _annoncer_source(self):
        o = self.derniere_origine
        if o == "bible":
            return self.SOURCE_BIBLIQUE
        if o == "conversation_locale":
            return "Je te réponds avec mon modèle de conversation local, sans source : ce n'est qu'un avis."
        if o == "meteo":
            return "La météo vient d'Open-Meteo, un service de données météo ouvertes."
        if o == "wikipedia":
            return f"Cette réponse vient de Wikipédia, article {self.derniere_fiche['titre']}."
        if o == "locale" and self.derniere_fiche:
            sources = [s for s in self.derniere_fiche["sources"] if s["consulte"]]
            if sources:
                return "Elle vient de ma base locale, appuyée sur : " + " ; ".join(
                    s["titre"].split("(")[0].strip() for s in sources[:3]) + "."
            return "Elle vient de ma base locale, sans référence vérifiée pour cette fiche."
        return ("Je réponds d'abord avec ma base locale. Sinon je consulte Wikipédia, Open-Meteo, "
                "et pour les questions bibliques JW.org, wol.jw.org et JW Library, sans rien en garder.")

    @staticmethod
    def en_francais(phrase, langue, traducteur):
        """Phrase entendue dans `langue` → français. Oui / non via le lexique fait à la main."""
        if langue == "fr":
            return phrase
        from .langues import LEXIQUE
        t = sans_accents(phrase)  # pas normaliser() : il effacerait le cyrillique, l'arabe, le chinois
        lex = LEXIQUE.get(langue, {})
        if lex and re.search(rf"^({lex['oui']})(\W|$)", t):
            return "oui"
        if lex and re.search(rf"^({lex['non']})(\W|$)", t):
            return "non"
        return traducteur.traduire(phrase, langue, "fr")

    def repondre_dans(self, phrase, locuteur, langue, traducteur):
        """Comme repondre(), pour une autre langue de discussion : Orion pense en français.
        Les oui / non passent par le lexique fait à la main (plus fiable que la traduction automatique)."""
        if langue == "fr":
            return self.repondre(phrase, locuteur)
        reponse, tache = self.repondre(self.en_francais(phrase, langue, traducteur), locuteur)
        if tache:
            return None, lambda: traducteur.traduire(tache(), "fr", langue)
        return traducteur.traduire(reponse, "fr", langue), None

    @staticmethod
    def _reponse_sourcee(fiche, decision):
        """Cite la meilleure source réellement consultée ; met toujours en doute le web non vérifié."""
        verifiees = [s for s in fiche["sources"] if s["consulte"] and s["portee"] == "fiche"]
        web = [s for s in verifiees if s["niveau"] == 0]
        solides = [s for s in verifiees if s["niveau"] >= 1]
        texte = fiche["contenu"]
        if web and not solides:
            texte = (f"D'après une page internet que je n'ai pas pu vérifier : {texte} "
                     "Méfie-toi, une information en ligne peut être fausse : recoupe-la avec une source sûre.")
        elif solides:
            s = solides[0]
            texte += f" Source : {s['titre'].split('(')[0].strip()}, {knowledge.NIVEAUX[s['niveau']]}."
        if decision:
            prudence = (" Pour la sécurité ou la structure, fais valider par un professionnel."
                        if fiche["domaine"] in ("batiment", "electronique") else "")
            texte = ("Je ne décide pas à ta place, mais voici ce qui est établi. " + texte +
                     " Vérifie que ta situation correspond bien à ces conditions." + prudence)
        return texte

