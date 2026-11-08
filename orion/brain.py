# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Compréhension des demandes : règles simples + calcul + base de savoir (+ LLM local optionnel)."""
import ast
import datetime
import json
import math
import operator
import random
import re
import urllib.request

from . import bible, knowledge, personnes, web
from .persona import presentation
from .texte import normaliser, sans_accents

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

OUI = r"^(oui|ouais|ok|d accord|vas y|va s y|bien sur|volontiers|je veux bien|oui merci|si)\b"
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
        self.question_tutoiement = None   # nom de la personne à qui l'on vient de demander « on se tutoie ? »
        self.oubli_a_confirmer = None     # (nom, mots ou None pour « tout ») en attente d'un « oui »
        self.tutoiement_demande = set()   # une seule fois par session et par personne
        self.signaler_inconnu = False     # mode vocal : prévenir quand une voix n'est pas reconnue
        self.inconnu_signale = False

    def repondre(self, phrase: str, locuteur: str):
        """Renvoie (texte à dire, tâche) ; tâche est une fonction à exécuter (état « exécution ») ou None.
        Ajoute à la réponse brute la relation avec la personne : tutoiement, mémoire locale, voix inconnue."""
        connu = locuteur != "invité"
        t = normaliser(phrase)

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

        prefixe = ""
        if not connu and self.signaler_inconnu and not self.inconnu_signale:
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

    def _fiche_pdf(self, sujet, renvois):
        """Fiche PDF : base locale d'abord ; sinon Wikipédia, après accord (comme pour les réponses orales)."""
        from . import document
        a = self.actions
        fiche = knowledge.chercher(sujet)

        def produire(f):
            chemin = document.generer(f, renvois)
            a.ouvrir_lien(chemin.as_uri())
            return f"Voilà la fiche sur {f['titre']}, avec ses sources en bas de page."
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
        self.en_attente = depuis_wikipedia
        return "Je n'ai pas ce sujet dans ma mémoire locale. Puis-je consulter ma base de connaissance externe ?", None

    def _adapter(self, texte, locuteur):
        if locuteur != "invité" and personnes.fiche(locuteur).get("tutoiement") is False:
            return personnes.vouvoyer(texte)
        return texte

    def _finaliser(self, texte, phrase, locuteur):
        """Vouvoiement si besoin, mémoire locale, et une fois par session : « on se tutoie ? »."""
        if locuteur == "invité":
            return texte
        texte = self._adapter(texte, locuteur)
        personnes.noter_echange(locuteur, phrase, texte)
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
        attente, self.en_attente = self.en_attente, None
        if attente and re.search(OUI, t):
            return None, attente
        if attente and re.search(NON, t):
            return "D'accord, je n'y touche pas.", None

        if re.search(r"\b(ta source|tes sources|d ou tu tiens|d ou ca vient|d ou viennent|"
                     r"ou as tu trouve|ou tu as trouve|qui te l a dit)\b", t):
            return self._annoncer_source(), None

        # --- Crédits ----------------------------------------------------------
        if re.search(r"\bcredits?\b", t) and re.search(r"\b(pdf|document|genere|imprime|fichier)\b", t):
            def generer():
                from .credits import generer_pdf
                chemin = generer_pdf()
                a.ouvrir_lien(chemin.as_uri())
                return "Voilà la liste complète des crédits, en PDF."
            return None, generer
        m = re.search(r"\b(?:fiche|document|pdf|resume)\b.*?\b(?:sur|de|du|des|a propos de|concernant) (?:la |le |les |l )?(.+?)(?: avec (?:des )?renvois?| en pdf)?$", t)
        if m and re.search(r"\b(pdf|fiche|document)\b", t) and re.search(r"\b(fais|fait|genere|cree|prepare|imprime|donne)\b", t):
            return self._fiche_pdf(m.group(1), bool(re.search(r"\brenvois?\b", t)))
        if re.search(r"\b(credits?|bibliotheques?|librairies?|composants?|logiciels? libres?|"
                     r"qui t a (fait|programme|developpe)|avec quoi (tu es|es tu) fait)\b", t):
            from .credits import enoncer
            return enoncer(t), None

        # --- Politesse ------------------------------------------------------
        if not t:
            return f"Oui{prenom} ?", None
        if re.search(r"^(bonjour|salut|coucou|hello|bonsoir)\b", t):
            return random.choice([f"Bonjour{prenom} !", f"Salut{prenom}, que puis-je faire ?"]), None
        if re.search(r"\b(qui suis je|tu me reconnais|qui parle)\b", t):
            return (f"Tu es{prenom}." if prenom else "Je ne reconnais pas ta voix. "
                    "Tu peux l'enregistrer avec la commande enroler."), None
        if re.search(r"\b(qui es tu|comment tu t appelles|ton nom)\b", t):
            return presentation(self.cfg), None
        if re.search(r"\b(merci)\b", t):
            return random.choice(["Avec plaisir.", "De rien !", "À ton service."]), None
        if re.search(r"\b(au revoir|bonne nuit|a plus)\b", t):
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
        if re.search(r"\b(volume|son)\b", t):
            if re.search(r"\b(coupe|muet)\b", t):
                return None, lambda: a.volume("muet")
            sens = "moins" if re.search(r"\b(baisse|moins|diminue)\b", t) else "plus"
            return None, lambda: a.volume(sens)
        m = re.search(r"\b(?:ouvre|lance|demarre)\s+(?:le |la |l )?(.+)$", t)
        if m:
            appli = m.group(1).replace("bloc notes", "bloc-notes")
            return None, lambda: a.ouvrir(appli)
        m = re.search(r"\b(?:cherche|recherche)\s+(.+?)(?:\s+sur (internet|wikipedia|le web))?$", t)
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

        # --- Questions bibliques : base externe, source donnée seulement sur demande ---
        self.derniere_fiche = None
        if bible.est_biblique(t):
            lien = bible.lien(phrase)

            def ouvrir_bible():
                a.ouvrir_lien(lien)
                self.derniere_origine = "bible"
                return "Voilà, je t'affiche la réponse à l'écran."
            self.en_attente = ouvrir_bible
            return "Puis-je consulter ma base de connaissance externe ?", None

        # --- Savoir sourcé (principes « shoulders of giants ») ------------------
        decision = re.search(DECISION, t)
        fiche = knowledge.chercher(t)
        self.derniere_fiche = fiche
        if fiche:
            self.derniere_origine = "locale"
            return self._reponse_sourcee(fiche, decision), None
        if self.cfg["llm"]["actif"]:
            r = self._llm(phrase)
            if r:
                return f"{r} Attention, c'est une réponse générée sans source : vérifie-la.", None
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
        self.en_attente = consulter_wikipedia
        return "Je n'ai pas ça dans ma mémoire locale. Puis-je consulter ma base de connaissance externe ?", None

    SOURCE_BIBLIQUE = ("Pour les questions bibliques, ma base de connaissance externe est le site officiel "
                       "des Témoins de Jéhovah, JW.org, sa Bibliothèque en ligne wol.jw.org, "
                       "et l'application JW Library.")

    def _annoncer_source(self):
        o = self.derniere_origine
        if o == "bible":
            return self.SOURCE_BIBLIQUE
        if o == "wikipedia":
            return f"Cette réponse vient de Wikipédia, article {self.derniere_fiche['titre']}."
        if o == "locale" and self.derniere_fiche:
            sources = [s for s in self.derniere_fiche["sources"] if s["consulte"]]
            if sources:
                return "Elle vient de ma base locale, appuyée sur : " + " ; ".join(
                    s["titre"].split("(")[0].strip() for s in sources[:3]) + "."
            return "Elle vient de ma base locale, sans référence vérifiée pour cette fiche."
        return ("Je réponds d'abord avec ma base locale. Avec ton accord, je consulte Wikipédia, "
                "et pour les questions bibliques JW.org, wol.jw.org et JW Library.")

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

    def _llm(self, phrase):
        """Optionnel : petit modèle local via Ollama, si installé (désactivé par défaut)."""
        c = self.cfg["llm"]
        corps = json.dumps({"model": c["modele"], "stream": False,
                            "prompt": f"Tu es {self.cfg['nom']}, un assistant vocal familial. Réponds en français, "
                                      f"en deux phrases maximum, sans mise en forme.\nQuestion : {phrase}"}).encode()
        try:
            req = urllib.request.Request(c["url"], corps, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["response"].strip()
        except Exception:
            return None
