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
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import bible, bibliotheque, dossiers, espace, export, knowledge, meteo, minuteur, personnes, publications, systeme, web
from .cerveau_documents import Documents
from .cerveau_publications import Publications
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
# Questions qu'Orion peut laisser en attente, avec leur valeur « rien en attente »
ATTENTES = {"en_attente": None, "ville_demandee": None, "duree_demandee": False, "question_tutoiement": None,
            "oubli_a_confirmer": None, "retrait_voix": None}
STOP_ATTENTE = r"\b(tais toi|taisez vous|chut|silence|stop|laisse tomber)\b"
COMMANDES = r"^(?:mets|joue|lance|ouvre|monte|baisse|coupe|pause|reprends|suivant|precedent|arrete)\b"
VIDEOS_MENSUELLES = "https://www.jw.org/fr/biblioth%C3%A8que/videos/#fr/categories/StudioMonthlyPrograms"
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


PREMIERS_MAX = 10_000


def bornes_premiers(t):
    """« nombres premiers de 1 a 100 », « entre 20 40 », « jusqu a mille », « de 100 » → (debut, fin), sinon None.
    `t` : phrase normalisée, nombres en chiffres."""
    if not re.search(r"\bnombres? premiers?\b", t):
        return None
    t = re.sub(r"\bmille\b", "1000", t)
    m = (re.search(r"\b(?:de|entre|depuis) (\d+) (?:a |et |jusqu a )?(\d+)\b", t)
         or re.search(r"\b(?:jusqu a|inferieurs? a|en dessous de|avant|sous|de) (\d+)\b", t))
    if not m:
        return None
    debut, fin = (int(m[1]), int(m[2])) if m.lastindex == 2 else (1, int(m[1]))
    return min(debut, fin), max(debut, fin)


def nombres_premiers(debut, fin):
    """Liste mise en forme (dix nombres par ligne), calculée : un petit modèle se trompe sur ce genre de liste."""
    crible = bytearray([1]) * (fin + 1)
    crible[:2] = b"\0\0"
    for n in range(2, int(fin ** 0.5) + 1):
        if crible[n]:
            crible[n * n::n] = bytes(len(range(n * n, fin + 1, n)))
    premiers = [n for n in range(debut, fin + 1) if crible[n]]
    if not premiers:
        return f"Il n'y a aucun nombre premier entre {debut} et {fin}."
    lignes = [", ".join(map(str, premiers[i:i + 10])) for i in range(0, len(premiers), 10)]
    return (f"# Nombres premiers de {debut} à {fin}\n\nIl y en a {len(premiers)} :\n\n" + "\n".join(lignes))


class Cerveau(Publications, Documents):
    def __init__(self, cfg, actions):
        self.cfg, self.actions = cfg, actions
        self.derniere_fiche = None
        self.en_attente = None        # action proposée, exécutée si l'utilisateur répond « oui »
        self.derniere_origine = None  # pour répondre à « quelle est ta source ? »
        self.ville_demandee = None        # phrase météo en attente de « pour quelle ville ? »
        self.symboliser = lambda libelle: None  # feuille qui s'écrit sur l'hologramme (branchée par la boucle vocale)
        self.tour, self.dernier_note = 0, None  # dernier échange mémorisé : (personne, n° d'échange, souvenir)
        self.sources_reponse = []         # publications citées par la réponse en cours (pour les documents)
        self.derniere_reponse = None      # dernière réponse donnée : « fais-en un document Word »
        self.export_en_cours = False
        self.derniers_fichiers = []       # résultats de la dernière recherche de fichiers (« ouvre le premier »)
        self.notes_a_jouer = []           # bips de départ des minuteurs, joués après la réponse orale
        self.minuteurs = []               # comptes à rebours en cours (3 au plus) : {fin, total, pour, nom, couleur}
        self.duree_demandee = False       # Orion vient de demander « pour combien de temps ? »
        self.question_tutoiement = None   # nom de la personne à qui l'on vient de demander « on se tutoie ? »
        self.oubli_a_confirmer = None     # (nom, mots ou None pour « tout ») en attente d'un « oui »
        self.demande_enrolement = None    # prénom dont la boucle vocale doit enregistrer la voix
        self.completer_voix = False       # compléter cette voix (sans effacer) plutôt que la remplacer
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
        Une question d'Orion (« on se tutoie ? », « pour quelle ville ? »…) n'attend qu'une réponse : un ordre
        d'arrêt l'annule, et elle expire si la phrase suivante n'y répond pas."""
        attentes = {a: getattr(self, a) for a in ATTENTES}
        en_cours = [a for a, v in attentes.items() if v is not ATTENTES[a]]  # « » compte : ville à demander
        if en_cours and re.search(STOP_ATTENTE, normaliser(phrase)):
            for a, vide in ATTENTES.items():
                setattr(self, a, vide)
            return "D'accord.", None
        resultat = self._repondre_avec_relation(phrase, locuteur)
        for a in en_cours:
            if getattr(self, a) is attentes[a]:  # restée sans réponse : on n'en parle plus
                setattr(self, a, ATTENTES[a])
        return resultat

    def _repondre_avec_relation(self, phrase: str, locuteur: str):
        """Ajoute à la réponse brute la relation avec la personne : tutoiement, mémoire locale, voix inconnue."""
        connu = locuteur != "invité"
        t = normaliser(phrase)
        self.tour += 1  # numéro de l'échange (pour « oublie ça » : seulement l'échange juste avant)

        # Confirmation du retrait d'une voix
        if self.retrait_voix:
            nom, self.retrait_voix = self.retrait_voix, None
            if re.search(OUI, t):
                from .voix import Profils
                Profils(self.cfg["seuil_locuteur"]).retirer(nom)
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
        m = re.search(r"\b(?:complete|ameliore|perfectionne|mets a jour|actualise) (?:ma|mon) (?:voix|empreinte)\b"
                      r"(?:.*?\b(?:je suis|je m appelle|c est) (\w+))?", t)
        if m:
            prenom = self._avec_accents(m.group(1) or "", phrase).capitalize() or (locuteur if connu else None)
            if not prenom:
                return "D'accord ! Dis-moi d'abord ton prénom : « complète ma voix, je suis… ».", None
            self.demande_enrolement, self.completer_voix = prenom, True
            return (f"D'accord {prenom}. Lis-moi cinq phrases de plus : j'ajoute ta voix d'aujourd'hui à ce que "
                    "je connais déjà, sans rien effacer."), None
        m = re.search(r"\b(?:memorise|enregistre|retiens|apprends) (?:ma|mon) voix\b(?:.*?\b(?:je suis|je m appelle|c est) (\w+))?", t)
        if m:
            prenom = self._avec_accents(m.group(1) or "", phrase).capitalize() or (locuteur if connu else None)
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
        if re.search(r"\b(que sais tu de moi|tu me connais)\b|\b(sais|connais|retenu)\b.*\b(sur|de) moi$", t):
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
            self.dernier_note = (locuteur, self.tour, souvenir)
            return self._adapter("C'est retenu, sans limite de temps : " + personnes.a_la_deuxieme(souvenir) + ".",
                                 locuteur), None
        m = re.search(r"^oublie (?:que |qu )(.+)$", t)
        if m and connu:
            self.oubli_a_confirmer = (locuteur, m.group(1))
            texte = re.sub(r"^\s*oublie\s+(?:que |qu')", "", phrase.strip(), flags=re.IGNORECASE).rstrip(" .?!")
            return self._adapter(f"Tu veux vraiment que j'oublie que {personnes.a_la_deuxieme(texte)} ? "
                                 "Dis oui pour confirmer.", locuteur), None
        # « cherche dans ta mémoire sur moi … » : recherche textuelle, puis suppression sur confirmation
        m = re.search(r"(?:\b(?:cherche|retrouve)\b.*?\b(?:memoire|souvenirs?)\b|\bqu est ce que tu as retenu\b|"
                      r"\btu te souviens\b).*?\b(?:sur|de|a propos d[eu]?|concernant|avec)\s+"
                      r"(?:moi\s+)?(?:sur |de |a propos d[eu]? |concernant )?(?:le |la |les |l |un |une )?(.+)$", t)
        if m and connu and m.group(1) not in ("moi", "toi"):
            trouvees = personnes.chercher_memoire(locuteur, m.group(1))
            if not trouvees:
                return self._adapter(f"Je n'ai rien en mémoire sur « {m.group(1)} ».", locuteur), None
            extraits = " ; ".join(f"« {texte[:70]} »" for _, _, texte in trouvees[:3])
            self.en_attente = lambda: self._adapter(
                f"C'est fait : {personnes.supprimer_entrees(locuteur, trouvees)} entrée"
                f"{'s' if len(trouvees) > 1 else ''} oubliée{'s' if len(trouvees) > 1 else ''}.", locuteur)
            return self._adapter(f"J'ai {len(trouvees)} entrée{'s' if len(trouvees) > 1 else ''} sur « {m.group(1)} » : "
                                 f"{extraits}{' …' if len(trouvees) > 3 else ''}. Je {'les' if len(trouvees) > 1 else "l'"}"
                                 f"{' ' if len(trouvees) > 1 else ''}oublie ?", locuteur), None

        # « oublie ça », « oublie cette histoire », « oublie ce que tu viens de dire » : seulement le dernier
        # échange, sans proposer de tout effacer
        if re.search(r"^(?:oublie|efface|laisse tomber|n en tiens pas compte)\b.*\b(cette histoire|cela|ca|"
                     r"ce que (?:tu viens|je viens|je t ai|tu m as) (?:de )?(?:dire|dit|raconter|raconte)|"
                     r"la derniere chose|ce dernier echange|cette (?:definition|reponse)|ta (?:definition|reponse))$", t) \
                or t in ("oublie", "oublie ca", "oublie tout ca"):
            oublie = None
            if connu and self.dernier_note and self.dernier_note[:2] == (locuteur, self.tour - 1):
                souvenir = self.dernier_note[2]
                if souvenir:  # l'échange précédent était « retiens que… » : on retire ce souvenir-là
                    personnes.oublier_souvenir(locuteur, souvenir)
                    oublie = souvenir
                else:
                    oublie = personnes.oublier_dernier(locuteur)
            self.dernier_note = None
            historique = self.conversation.historiques.get(locuteur, [])
            del historique[-2:]  # la discussion en cours ne s'appuiera plus dessus
            self.derniere_reponse = None
            if oublie:
                return self._adapter(f"C'est oublié : « {oublie} ». Le reste de ce que je sais sur toi ne bouge pas.",
                                     locuteur), None
            return "C'est oublié, on n'en parle plus.", None

        if re.search(r"\b(oublie (tout )?ce que tu sais (de|sur) moi|oublie moi|oublie tout(?! ca\b)|"
                     r"efface (mes donnees|ma memoire))\b", t):
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
                and len(phrase.split()) > 2 and not re.search(OUI + "|" + NON, normaliser(phrase))
                and not re.search(COMMANDES, normaliser(phrase))):
            sources = self.sources_reponse or ([s for s in (self.derniere_fiche or {}).get("sources", [])
                                                 if s.get("consulte")]
                                                if self.derniere_origine in ("locale", "wikipedia") else [])
            self.derniere_reponse = {"question": phrase, "contenu": texte, "sources": sources}
        self.export_en_cours = False
        if locuteur == "invité":
            return texte
        texte = self._adapter(texte, locuteur)
        if espace.place_pour(self.cfg, 2_000):  # l'historique n'est pas essentiel : sans place, on ne l'écrit pas
            personnes.noter_echange(locuteur, phrase, texte)
            self.dernier_note = (locuteur, self.tour, None)
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
        self.sources_reponse = []
        t = normaliser(phrase)
        for mot in self.cfg["mots_eveil"]:
            t = re.sub(rf"^(ok |dis |hey |salut )?{mot}\b[ ,]*", "", t)
        # « nombres premiers » souvent compris « (noms) mon premier » quand une plage suit
        t = re.sub(r"\b(?:(?:des |les )?noms? )?mon premiers?\b(?= (?:de|d|entre|jusqu|inferieur))", "nombres premiers", t)
        prenom = "" if locuteur == "invité" else f" {locuteur}"
        a = self.actions

        # --- Réponse à une proposition (« Puis-je consulter… ? ») -------------
        if self.duree_demandee:  # réponse à « pour combien de temps ? »
            self.duree_demandee = False
            d = minuteur.duree(chiffres(t))
            if d:
                return self._lancer_minuteur(d, locuteur, self._avec_accents(minuteur.nom(t), phrase))

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

        # --- Mode silencieux : réponses écrites (sans voix), ou retour à la voix ---
        if re.search(r"\b(mode silencieux|en silencieux|reponds? (?:moi )?par ecrit|ecris (?:moi )?au lieu de parler|"
                     r"sans parler|ne parle plus)\b", t):
            from .config import sauver
            self.cfg["mode_silencieux"] = True
            sauver(self.cfg)
            return "Mode silencieux : je te réponds par écrit. Dis « mode vocal » pour que je reparle.", None
        if re.search(r"\b(mode vocal|reparle|parle a nouveau|reponds? (?:moi )?a voix haute|tu peux parler)\b", t):
            from .config import sauver
            self.cfg["mode_silencieux"] = False
            sauver(self.cfg)
            return "D'accord, je te réponds de nouveau à voix haute.", None

        # --- Ce qu'Orion sait faire : réponse courte, ciblée selon la question ---
        if re.search(CAPACITES_TOT, t):
            reponse = self._capacites(t, generique=not t.startswith("comment"))
            if reponse:
                return reponse, None

        # --- Compte à rebours (interne à Orion, affiché sur l'hologramme) ---
        # « compte à rebours » est souvent mal transcrit (« mémento à rebours », « conte à rebours ») : « à rebours » suffit
        # tournures acceptées : « minuteur de 5 minutes », « compte 5 minutes », « décompte 30 s »,
        # « préviens-moi dans 10 minutes », « mets 3 minutes », « lance 20 secondes »…
        duree_dite = minuteur.duree(chiffres(t))
        if self.minuteurs and not duree_dite and re.search(r"\b(reste|restant)\b", t) and re.search(
                r"\b(combien|temps|encore)\b", t):
            return "Il reste " + " ; ".join(
                f"{minuteur.en_mots(m['fin'] - time.monotonic())}" + (f" pour {m['nom']}" if m["nom"] else "")
                for m in self.minuteurs) + ".", None
        if re.search(r"\b(a rebours|minuteurs?|minuteries?|chronos?|chronometres?|timers?|decomptes?|decompter|"
                     r"compteurs?)\b", t) \
                or (duree_dite and re.search(r"^\d+\s*(?:heures?|h|minutes?|min|mn|secondes?|sec|s)\b.*\bpour\b|"
                                             r"^(?:compte|mets|lance|demarre|programme|regle)\b|\bcompter?\b|"
                                             r"\b(?:previens|previens moi|rappelle moi|alerte moi|sonne|bipe)\b.*\bdans\b", t)):
            if re.search(r"\b(annule|arrete|stop|supprime|enleve)", t):
                if not self.minuteurs:
                    return "Il n'y a pas de compte à rebours en cours.", None
                vises = (list(self.minuteurs) if re.search(r"\b(tous|toutes|les minuteurs)\b", t) else
                         [m for m in self.minuteurs if m["nom"] and normaliser(m["nom"]) in t]
                         or (list(self.minuteurs) if len(self.minuteurs) == 1 else []))
                if not vises:
                    return ("Lequel ? " + ", ".join(minuteur.libelle(m) for m in self.minuteurs)
                            + ", ou tous ?"), None
                for m in vises:
                    self.minuteurs.remove(m)
                return ("Tous les minuteurs sont annulés." if len(vises) > 1 else
                        minuteur.libelle(vises[0])[:1].upper() + minuteur.libelle(vises[0])[1:] + " est annulé."), None
            if duree_dite:
                return self._lancer_minuteur(duree_dite, locuteur, self._avec_accents(minuteur.nom(t), phrase))
            if not self.minuteurs and re.search(r"\b(reste|combien|ou en)", t):
                return "Aucun minuteur n'est en cours.", None
            if self.minuteurs and re.search(r"\b(reste|combien|ou en)", t):
                return "Il reste " + " ; ".join(
                    f"{minuteur.en_mots(m['fin'] - time.monotonic())}"
                    + (f" pour {m['nom']}" if m["nom"] else "") for m in self.minuteurs) + ".", None
            self.duree_demandee = True
            return "Pour combien de temps ?", None

        # --- Compétence « commande » : une question sur l'ordinateur résolue par une commande de consultation ---
        if re.search(r"\b(en bash|en shell|en zsh|une commande|ligne de commande|dans le terminal|par le terminal)\b|"
                     r"\b(adresse ip|niveau de (?:la )?batterie|batterie|processus|programmes?\b.*\b(?:tournent|consomment|ouverts?)|"
                     r"combien de fichiers|depuis quand .*allume|mac est allume|uptime)\b", t):
            return self._commande(phrase)

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
        if bornes := bornes_premiers(chiffres(t)):
            if bornes[1] > PREMIERS_MAX:
                return f"Je m'arrête à {PREMIERS_MAX} : au-delà, la liste serait trop longue à lire.", None
            texte = nombres_premiers(*bornes)
            if re.search(r"\b(document|fichier|word|docx|markdown|html|page web|pdf)\b", t):
                self.derniere_reponse = {"question": f"Nombres premiers de {bornes[0]} à {bornes[1]}",
                                         "contenu": texte, "sources": []}
                return self._exporter(export.format_demande(t), cle)
            return texte, None
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
        if not re.search(r"\b(ta|ma) bibliotheque\b|\bdocuments?\b", t) and re.search(
                r"\b(credits?|bibliotheques?|librairies?|composants?|logiciels? libres?|"
                     r"qui t a (fait|programme|developpe)|avec quoi (tu es|es tu) fait)\b", t):
            from .credits import enoncer
            return enoncer(t), None

        # --- Politesse ------------------------------------------------------
        if not t:
            return f"Oui{prenom} ?", None
        if re.search(r"^(bonjour|salut|coucou|hello|bonsoir)\b", t):
            return random.choice([f"Bonjour{prenom} !", f"Salut{prenom}, que puis-je faire ?"]), None
        if re.search(r"\b(qui suis je|qui je suis|tu me reconnais|tu (?:me )?reconnais (?:ma voix|qui)|^tu reconnais$|"
                     r"qui parle|tu sais qui (je suis|c est))\b", t):
            return (f"Tu es{prenom}." if prenom else "Je ne reconnais pas ta voix. "
                    "Dis « mémorise ma voix, je suis… », ou « complète ma voix » si je te connais déjà."), None
        if re.search(r"\b(je vais (me coucher|dormir)|bonne nuit|a demain|je vais au lit)\b", t):
            return random.choice([f"Bonne nuit{prenom}, dors bien !", f"Bonne nuit{prenom}. À demain !"]), None
        if re.search(r"\b(qui es tu|comment tu t appelles|ton nom|presente toi|presentez vous|tu es qui)\b", t):
            return presentation(self.cfg), None
        if re.search(r"\b(merci)\b", t):
            return random.choice(["Avec plaisir.", "De rien !", "À ton service."]), None
        if re.search(r"\b(au revoir|a plus)\b", t):
            return f"À bientôt{prenom}.", None

        # --- Musique --------------------------------------------------------
        if re.search(r"\b(musique|morceau|chanson|spotify|aimp|vlc|playlist|joue|mets)\b", t):
            lecteur = next((c for c, motif in (("spotify", r"\bspotify\b"), ("aimp", r"\baimp\b"), ("vlc", r"\bvlc\b"),
                                                ("musique", r"\b(apple music|itunes|l app musique|application musique)\b"))
                            if re.search(motif, t)), None)
            if re.search(r"\b(suivant|suivante|passe|next)\b", t):
                cmd = "suivant"
            elif re.search(r"\b(precedent|precedente|reviens)\b", t):
                cmd = "precedent"
            elif re.search(r"\b(pause)\b|^(?:pas|pose|po) la musique$", t):  # « pause » souvent mal transcrit
                cmd = "pause"
            elif re.search(r"\b(arrete|stop|coupe)\b", t):
                cmd = "stop"
            else:
                cmd = "jouer"
            m = re.search(r"\b(?:joue|mets|lance|ecouter)\s+(?!la musique|de la musique|spotify|aimp|vlc|musique)"
                          r"(?:moi |du |de la |des |le |la |les )?(.+?)(?:\s+sur\s+(?:spotify|vlc|musique|apple music))?$", t)
            recherche = m.group(1) if m and cmd == "jouer" else None
            return None, lambda: a.musique(cmd, lecteur, recherche)
        if re.search(r"\b(suivant|morceau d apres)\b", t):
            return None, lambda: a.musique("suivant")
        if re.search(r"\bpause\b", t):
            return None, lambda: a.musique("pause")
        if re.search(r"\b(reprends|relance) (?:la )?(?:musique|lecture)\b|^reprends$", t):
            return None, lambda: a.musique("jouer")

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
        if re.search(r"\b(telecharge|recupere|apprends|ajoute|lis|indexe)\b.*\b(lien|adresse|url|fichier) copie", t) \
                or re.search(r"\b(telecharge|recupere)\b.*\blien\b", t):
            return self._telecharger_lien(publications.presse_papiers())
        if re.search(r"\b(quels?|liste)\b.*\bdocuments?\b.*\b(bibliotheque|appris|indexe|as tu)\b|\bta bibliotheque\b", t):
            docs = bibliotheque.liste()
            if not docs:
                return ("Ma bibliothèque est vide. Copie l'adresse d'un document (PDF, EPUB, Word, Markdown, texte, "
                        "page web), puis dis « ajoute le lien copié »."), None
            return (f"J'ai {len(docs)} document{'s' if len(docs) > 1 else ''} : "
                    + " ; ".join(t for t, _, _ in docs[:6]) + ("…" if len(docs) > 6 else "") + "."), None
        m = re.search(r"\b(?:retire|supprime|enleve)\b.*\bdocument\b\s+(.+)$", t)
        if m and bibliotheque.retirer(m.group(1)):
            return f"J'ai retiré « {m.group(1)} » de ma bibliothèque. Le fichier, lui, reste sur l'ordinateur.", None

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

        # --- Émission vidéo du mois (vidéothèque du site de l'éditeur), ouverte à l'écran ---
        # seulement dans le contexte JW : « broadcasting », « télédiffusion », ou « JW » (souvent transcrit
        # « j w », « ji double vé ») avec « émission » / « programme mensuel » — pas une émission de télé quelconque
        jw = r"\b(?:jw|j w|ji? double ve?|jay double you|broadcasting|broad casting|teled\w+)\b"
        if re.search(jw, t) and re.search(r"\b(broadcasting|broad casting|teled\w+|emissions?|programmes? mensuels?|"
                                          r"mois|video)\b", t):
            return self._emission(t)

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
                self._citer_passages(trouves[:2])
                return " ".join(f"{lieu} : {texte}" for lieu, texte, _ in trouves[:2]), None
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

        # --- Bibliothèque : documents ajoutés depuis une URL ou un fichier (tous les mots de la question) ---
        trouves = publications.rechercher(phrase, bibliotheque.PREFIXE, limite=2, tous_les_mots=True)
        if trouves:
            self.derniere_origine = "bibliotheque"
            morceaux = []
            for lieu, texte, cle in trouves[:2]:
                doc = bibliotheque.document(cle)
                nom = doc[0] if doc else "un document"
                morceaux.append(f"D'après « {nom} »{'' if lieu in ('début', nom) else f', {lieu}'} : {texte}")
                self.sources_reponse.append({"titre": f"{nom}, {lieu} (document ajouté, non vérifié)",
                                             "url": doc[1] if doc and "://" in doc[1] else None, "niveau": 0,
                                             "consulte": knowledge.aujourdhui(), "portee": "fiche"})
            return " ".join(morceaux), None

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

    def _blague(self):
        from . import blagues
        question, chute = blagues.blague(self.cfg.get("blagues_internet", False))  # réserve relue par défaut
        self.derniere_origine = "blague"
        return f"{question} … {chute}" if chute else question

    def _commande(self, question):
        """Le modèle local écrit une commande de consultation ; Orion la vérifie, la montre, attend l'accord,
        la lance en lecture seule (bac à sable), puis résume le résultat."""
        from . import commandes
        if not commandes.systeme():
            return "Je ne sais pas encore écrire de commande pour ce système.", None
        if not self.conversation.local_disponible():
            return "Il me faut mon modèle de conversation pour écrire une commande : installe-le depuis le panneau.", None
        self.signaler("J'écris la commande…")
        commande = commandes.proposer(question, self.conversation)
        self.signaler("")
        if not commande:
            return "Je ne trouve pas de commande qui réponde sans rien modifier.", None
        sure, raison = commandes.verifier(commande)
        if not sure:
            return f"J'ai pensé à « {commande} », mais je ne la lance pas : {raison}.", None

        def lancer():
            with self._redaction("la commande", "BASH"):
                sortie = commandes.executer(commande)
            print(f"[commande] {commande}\n{sortie}", flush=True)
            self.derniere_origine = "commande"
            return commandes.resumer(question, sortie, self.conversation)
        self.en_attente = lancer
        return f"Je vais lancer la commande « {commande} », en lecture seule. Je la lance ?", None

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

    @staticmethod
    def _avec_accents(nom, phrase):
        """« pates » (phrase normalisée) → « pâtes », tel que la personne l'a dit."""
        originaux = {normaliser(m): m.lower() for m in re.findall(r"[\w'’-]+", phrase)}
        return " ".join(originaux.get(m, m) for m in nom.split())

    def _lancer_minuteur(self, secondes, locuteur, nom=""):
        """Ajoute un minuteur (3 au plus en même temps), avec un nom facultatif et sa propre couleur."""
        if len(self.minuteurs) >= minuteur.MAXIMUM:
            return (f"J'ai déjà {minuteur.MAXIMUM} minuteurs en cours, c'est mon maximum. Annule-en un d'abord : "
                    + ", ".join(minuteur.libelle(m) for m in self.minuteurs) + "."), None
        prises = {m["couleur"] for m in self.minuteurs}
        rang = next(i for i, c in enumerate(minuteur.COULEURS) if c not in prises)  # première place libre
        self.minuteurs.append({"fin": time.monotonic() + secondes, "total": secondes, "pour": locuteur,
                               "nom": nom, "couleur": minuteur.COULEURS[rang], "note": minuteur.NOTES[rang]})
        self.notes_a_jouer.append(minuteur.NOTES[rang])  # bip de départ, à la hauteur de ce minuteur
        autres = len(self.minuteurs) - 1
        return (f"C'est parti : {minuteur.en_mots(secondes)}{f' pour {nom}' if nom else ''}."
                + (f" Ça fait {autres + 1} minuteurs en cours." if autres else "")), None

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

