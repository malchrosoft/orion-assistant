# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Point d'entrée.

  python -m orion              assistant vocal + hologramme
  python -m orion texte        conversation au clavier (sans micro ni modèle)
  python -m orion enroler Nom  enregistre la voix d'un membre de la famille
  python -m orion savoir       reconstruit la base de savoir après modification de savoir.json
  python -m orion holo         démo de l'hologramme (fait défiler les états)
  python -m orion panneau      interface graphique (discussion, savoir, famille, réglages)
  python -m orion apprendre URL [sujet]   retient une page web (toujours marquée non vérifiée)
  python -m orion verifier     vérifie en ligne les références livrées
  python -m orion limite [Mo]  affiche l'espace occupé, ou change la limite (avec confirmation)
  python -m orion dossiers [ajouter MOT CHEMIN | retirer MOT | defaut MOT]   dossiers d'enregistrement des PDF
"""
import math
import os
import sys
import threading
import time
from pathlib import Path

from . import knowledge
from .actions import Actions
from .brain import Cerveau
from .config import charger
from .texte import est_echo, normaliser, sans_accents, trouver_eveil, trouver_nom


def mode_texte(cfg):
    from . import langues
    cerveau = Cerveau(cfg, Actions(cfg))
    langue = cfg["langue_discussion"] if langues.installee(cfg["langue_discussion"]) else "fr"
    traducteur = langues.Traducteur()
    print(f"{cfg['nom']} (mode texte, {langues.nom(langue)}) — Ctrl+C pour quitter")
    while True:
        try:
            phrase = input("toi > ")
        except (EOFError, KeyboardInterrupt):
            return
        reponse, tache = cerveau.repondre_dans(phrase, "invité", langue, traducteur)
        print(f"{cfg['nom']} > {tache() if tache else reponse}")
        for src in (cerveau.derniere_fiche or {}).get("sources", []) if not tache else []:
            print(f"     [{src['niveau']}] {'source' if src['portee'] == 'fiche' else 'pour aller plus loin'} : "
                  f"{src['titre']} — {src['url']}"
                  f"{'' if src['consulte'] else '  (non vérifiée)'}")


def commande_limite(cfg, valeur=None):
    """Affiche l'occupation ; avec une valeur, change la limite après avertissements et confirmation."""
    from . import espace
    from .config import sauver
    o, l, r = espace.etat(cfg)
    for libelle, octets in espace.categories().items():
        print(f"  {libelle:45} {octets / espace.MO:8.1f} Mo")
    print(f"  {'Total':45} {o / espace.MO:8.1f} Mo sur {l / espace.MO:.0f} Mo autorisés ({r:.0%})")
    print(f"  Espace libre sur le disque : {espace.libre() / espace.MO:.0f} Mo")
    if valeur is None:
        return
    try:
        mo = int(valeur)
    except ValueError:
        return print("Indiquez une taille en Mo, par exemple : python -m orion limite 2048")
    for avertissement in espace.verifier_nouvelle_limite(mo):
        print(f"  ⚠ {avertissement}")
    if input(f"Fixer la limite d'Orion à {mo} Mo ? (oui/non) ").strip().lower() not in ("oui", "o", "yes", "y"):
        return print("Limite inchangée.")
    cfg["limite_disque_mo"] = mo
    sauver(cfg)
    if espace.occupe() > mo * espace.MO:
        print(f"Allègement : {espace.alleger(espace.occupe() - mo * espace.MO) / espace.MO:.1f} Mo libérés.")
    print(f"Limite fixée à {mo} Mo.")


def commande_dossiers(cfg, args):
    """Liste ou modifie les dossiers où Orion enregistre les documents (mot-clé → chemin)."""
    from . import dossiers
    from .config import sauver
    try:
        if args[:1] == ["ajouter"] and len(args) >= 3:
            dossiers.ajouter(cfg, args[1], " ".join(args[2:]))
        elif args[:1] == ["retirer"] and len(args) == 2:
            dossiers.retirer(cfg, args[1])
        elif args[:1] == ["defaut"] and len(args) == 2 and args[1] in dossiers.liste(cfg):
            cfg["dossier_defaut"] = args[1]
        elif args:
            return print("Usage : python -m orion dossiers [ajouter MOT CHEMIN | retirer MOT | defaut MOT]")
    except ValueError as e:
        return print(e)
    if args:
        sauver(cfg)
    for cle, chemin in dossiers.liste(cfg).items():
        print(f"  {'*' if cle == dossiers.cle_par_defaut(cfg) else ' '} {cle:15} {chemin}")
    print("  (* = dossier par défaut ; à la voix : « … dans <mot-clé> »)")


def enroler(cfg, nom):
    from .voix import Oreille, Profils
    oreille, profils, vecteurs = Oreille(cfg), Profils(cfg["seuil_locuteur"]), []
    print(f"Enregistrement de {nom} : lis 5 phrases à voix haute, une par une (3 secondes chacune).")
    while len(vecteurs) < 5:
        texte, vecteur = oreille.phrase()
        if vecteur:
            vecteurs.append(vecteur)
            print(f"  {len(vecteurs)}/5 ✓  « {texte} »")
    profils.enregistrer(nom, vecteurs)
    print(f"Voix de {nom} enregistrée.")


STOP = r"\b(stop|tais toi|taisez vous|chut|silence|arrete|ca suffit|attends|stoppe)\b"


CHAHUTE = [
    "Oh là, où est-ce qu'on m'emmène ?",
    "Doucement, j'ai le mal de mer !",
    "Wouah, ça tangue ! Préviens la prochaine fois.",
    "Hop là ! Bon, d'accord, je m'installe ici.",
    "Attention, je vais finir par avoir le tournis.",
    "Tu déménages souvent les gens comme ça ?",
    "Pas trop vite, mes points s'éparpillent !",
]

TROP_DE_CLICS = [
    "Hé, doucement ! Je ne suis pas un bouton d'ascenseur : un seul clic suffit, je t'écoute.",
    "Du calme, du calme ! À force de me tapoter, je vais finir par compter les points.",
    "Je suis à l'écoute, promis. Pas besoin de me secouer comme une vieille télécommande !",
    "Respire un grand coup… Voilà. Maintenant, dis-moi ce que tu veux, je suis à ton écoute.",
    "Si tu cliques encore, je demande une augmentation ! Bon, je t'écoute.",
]


def _date_config():
    from .config import UTILISATEUR
    fichier = UTILISATEUR / "config.json"
    return fichier.stat().st_mtime if fichier.exists() else 0.0


def _lire_avancement(message):
    """« Voix Siwis : 40 % » → (« Voix Siwis… », 0.4) ; sans pourcentage, la fraction est inconnue (None)."""
    import re
    m = re.search(r"(\d+)\s*%", message)
    if not m:
        return message, None
    return re.sub(r"\s*:?\s*\d+\s*%.*$", "", message) + "…", int(m.group(1)) / 100


def _langue_demandee(t):
    """« anglais » → "en" ; None si aucune langue reconnue."""
    from .bouche import LANGUES
    return next((c for c, nom in LANGUES.items() if normaliser(nom) in t.split()), None)


def boucle_vocale(cfg, holo):
    import random
    import re
    from . import modeles, personnes
    from .bouche import LANGUES, Bouche, bip, voix_pour
    from .config import UTILISATEUR, sauver
    from .persona import salutation
    from .voix import Oreille, Profils
    if modeles.manquants(UTILISATEUR / "models"):
        holo.changer("execution", "Premier lancement")
        modeles.installer(UTILISATEUR / "models", lambda m: holo.progression(*_lire_avancement(m)))
        holo.progression("")
    from . import langues
    holo.changer("reflexion", "Chargement…")
    discussion = cfg["langue_discussion"] if langues.installee(cfg["langue_discussion"]) else "fr"
    if discussion != "fr":
        cfg["chemin_vosk"] = str(langues.chemin_modele_vosk(discussion))
    traducteur = langues.Traducteur()
    oreille, bouche = Oreille(cfg), Bouche(cfg)
    profils, cerveau = Profils(cfg["seuil_locuteur"]), Cerveau(cfg, Actions(cfg))
    holo.sur_silence = bouche.interrompre  # clic droit → « Se taire »
    holo.source_niveau = lambda: oreille.niveau  # l'anneau ondule avec le son du micro
    clics = {"en_attente": False, "recents": [], "deplace": False, "derniere_remarque": 0.0}
    holo.sur_clic = lambda: clics.update(en_attente=True)  # un clic sur l'hologramme vaut « dis Orion »
    holo.sur_deplacement = lambda: clics.update(deplace=True)
    annonces = {"etape": None, "palier": -1, "quand": 0.0}
    dernier_dit = {"texte": "", "quand": 0.0}  # pour écarter l'écho de sa dernière phrase

    def signaler_tache(message):
        """Avancement d'une tâche longue : texte et barre sur l'hologramme ; à voix haute au début de chaque
        étape puis à chaque quart, au plus toutes les 15 secondes, pour ne pas parler sans arrêt."""
        if not message:
            holo.progression("")
            return
        texte, fraction = _lire_avancement(message)
        holo.progression(texte, fraction)
        etape = re.sub(r"\s*:?\s*\d+\s*%.*$", "", message)
        palier = int(fraction * 4) if fraction is not None else -1
        maintenant = time.time()
        if etape != annonces["etape"] or (palier > annonces["palier"] and maintenant - annonces["quand"] > 15):
            annonces.update(etape=etape, palier=palier, quand=maintenant)
            bouche.dire(etape if fraction is None else f"{etape} : {int(fraction * 100)} pour cent.")  # sans écoute de l'interruption : phrase courte, la tâche continue après
    cerveau.signaler = signaler_tache
    config_vue = {"date": _date_config()}

    def recharger():
        """Relit config.json et applique voix, présentation, modèle… sans redémarrer Orion."""
        nouveau = charger()
        nouveau.pop("chemin_vosk", None)
        cfg.update({k: v for k, v in nouveau.items() if k != "chemin_vosk"})
        bouche.recharger(cfg)
        config_vue["date"] = _date_config()
        print("[réglages rechargés]", flush=True)
    cerveau.conversation.signaler = signaler_tache
    cerveau.signaler_inconnu = bool(profils.data)  # « je n'ai pas reconnu ta voix » seulement si la famille est enregistrée
    eveil_jusqua = 0.0

    def parler(texte):
        """Parle micro coupé : Orion ne s'entend jamais lui-même. Un clic sur l'hologramme (ou « Se taire »
        au clic droit) l'interrompt ; il se met alors à écouter. Renvoie False s'il a été interrompu."""
        holo.changer("parole", texte)
        fini = threading.Event()
        clics["en_attente"] = False
        oreille.muet = True
        threading.Thread(target=lambda: (bouche.dire(texte), fini.set()), daemon=True).start()
        interrompu = False
        while not fini.wait(0.05):
            if clics["en_attente"]:  # clic pendant qu'il parle : il se tait et écoute
                clics["en_attente"] = False
                bouche.interrompre()
                interrompu = True
                break
        reprendre_micro()
        dernier_dit.update(texte=texte, quand=time.time())
        return not interrompu

    def reprendre_micro():
        time.sleep(0.5)  # laisse s'éteindre la résonance des haut-parleurs
        oreille.vider()
        oreille.muet = False

    def stop_lexique(entendu):
        """« Stop » dans la langue de discussion (lexique fait à la main, sans normalisation latine)."""
        mots = langues.LEXIQUE.get(discussion, {}).get("stop")
        return bool(mots and re.search(rf"(^|\W)({mots})(\W|$)", sans_accents(entendu)))

    def dire(texte_fr):
        """Traduit la réponse dans la langue de discussion, puis la prononce."""
        return parler(traducteur.traduire(texte_fr, "fr", discussion) if discussion != "fr" else texte_fr)

    def changer_discussion(code):
        """Change la langue dans laquelle on parle à Orion (et sa voix)."""
        nonlocal discussion
        if code not in langues.CATALOGUE:  # voix disponible, mais pas de modèle pour discuter
            return changer_langue(code) or f"Je ne sais pas encore discuter en {code}."
        if not langues.installee(code):
            return (f"Le {langues.nom(code)} n'est pas encore installé pour discuter. Ouvre le panneau, "
                    "onglet Langues : je t'indiquerai l'espace nécessaire avant de l'installer.")
        discussion = code
        oreille.charger(langues.chemin_modele_vosk(code))
        cfg["langue_discussion"] = code
        sauver(cfg)
        message = changer_langue(code) if code != cfg["langue"] else ""
        return f"D'accord, on parle maintenant en {langues.nom(code)}. {message}".strip()

    def enregistrer_voix(prenom):
        """Enregistrement de la voix pendant la conversation : 5 phrases, puis confirmation orale."""
        vecteurs = []
        while len(vecteurs) < 5:
            holo.changer("ecoute", f"Voix de {prenom} : phrase {len(vecteurs) + 1}/5")
            texte, empreinte = ecouter(True)
            if empreinte:
                vecteurs.append(empreinte)
                print(f"[voix de {prenom} {len(vecteurs)}/5] {texte}", flush=True)
        profils.enregistrer(prenom, vecteurs)
        parler(f"C'est fait, {prenom} : je reconnaîtrai ta voix.")

    def ecouter(eveille):
        """Attend une phrase complète, en affichant les mots au fur et à mesure."""
        while True:
            if annonces:  # fin de compte à rebours : Orion prend la parole, puis se remet à l'écoute
                parler(annonces.pop(0))
                holo.changer("ecoute" if eveille else "veille", "Je t'écoute…" if eveille else
                             f"« dis-moi {cfg['nom']} »")
            if clics["en_attente"]:
                return None, None
            if clics["deplace"]:
                clics["deplace"] = False
                # remarque de temps en temps seulement (au plus toutes les 20 s), pour que ça reste drôle
                if time.time() - clics["derniere_remarque"] > 20 and random.random() < 0.6:
                    clics["derniere_remarque"] = time.time()
                    etat_avant = "ecoute" if eveille else "veille"
                    parler(random.choice(CHAHUTE))
                    holo.changer(etat_avant, "Je t'écoute…" if eveille else f"« dis-moi {cfg['nom']} »")
            texte, final, empreinte = oreille.lire(0.5)
            if texte and not final and (eveille or trouver_eveil(texte, cfg["mots_eveil"],
                                                                   cfg["formules_eveil"])[0]):
                holo.changer("ecoute", texte)
            if final and texte:
                return texte, empreinte

    def confirmer_langue():
        """Premier lancement : Orion annonce sa langue et demande confirmation à voix haute."""
        nom = LANGUES.get(cfg["langue"], cfg["langue"])
        parler(f"Je parlerai en {nom}. C'est bien ce que tu souhaites ? Réponds oui, ou dis la langue de ton choix.")
        holo.changer("ecoute", "oui / anglais / espagnol…")
        texte, _ = ecouter(True)
        t = normaliser(texte)
        code = _langue_demandee(t)
        if code and code != cfg["langue"]:
            parler(changer_langue(code))
        elif re.search(r"\b(oui|ok|d accord|parfait|c est bien|exactement)\b", t) or code:
            cfg["langue_confirmee"] = True
            sauver(cfg)
            parler("Parfait.")
        else:
            parler("Je n'ai pas compris, je garde le " + nom + ". Tu pourras changer dans le panneau, onglet Voix.")

    def changer_langue(code):
        voix = voix_pour(code)
        nom = LANGUES[code]
        if not voix:
            return (f"Je n'ai pas de voix en {nom} sur cet ordinateur. Ouvre le panneau, onglet Voix : "
                    "je t'indiquerai comment en installer une.")
        cfg.update(langue=code, voix_id=voix[0][0], langue_confirmee=True, genre=voix[0][3] or cfg["genre"])
        sauver(cfg)
        bouche.voix = voix[0][0]
        if code != discussion:
            return f"D'accord, ma voix est maintenant en {nom}."
        return ""

    print(f"{cfg['nom']} est prêt. Dites « dis-moi {cfg['nom']} » (ou « dis {cfg['nom']} », « hey {cfg['nom']} »), puis votre demande. "
          "Ce terminal affiche ce qu'il entend.",
          flush=True)
    if not cfg["langue_confirmee"]:
        confirmer_langue()
    elif not profils.data:
        parler(f"{salutation(cfg)} Pour que je reconnaisse chacun à sa voix, "
               "double-clique sur moi et va dans l'onglet Famille.")
    else:
        parler(salutation(cfg))
    from . import composants
    manque = composants.manquants(cfg)
    if manque:
        parler("Au fait, je peux m'installer " + " et ".join(composants.LIBELLES[g] for g, _ in manque)
               + ". Dis-moi « installe ce qui te manque » quand tu veux.")
    # Pas d'écoute constante : Orion ne réagit qu'à « hey Orion » / « dis Orion », ou juste après avoir posé
    # une question (pour qu'on puisse répondre « oui » sans répéter la formule).
    def verifier_publications():
        """Au démarrage, en arrière-plan : publications présentes, lisibles et indexées."""
        from . import dossiers, publications
        try:
            chemins = [Path(os.path.expanduser(c)) for c in dossiers.liste(cfg).values()]
            bilan = publications.verifier(chemins)
        except Exception as e:  # la vérification ne doit jamais empêcher Orion de démarrer
            print(f"[publications] vérification impossible : {e}", flush=True)
            return
        texte = f"{bilan['valides']} publication(s) prête(s)"
        if bilan["corrompus"]:
            texte += f", {len(bilan['corrompus'])} abîmée(s) à retélécharger : " + ", ".join(bilan["corrompus"])
        if bilan["disparus"]:
            texte += f", {len(bilan['disparus'])} retirée(s) de l'index (fichier absent)"
        print(f"[publications] {texte}", flush=True)
        if bilan["corrompus"] or bilan["disparus"]:
            holo.derniere_action(f"{time.strftime('%H:%M')} · {texte}")
    threading.Thread(target=verifier_publications, daemon=True).start()

    annonces = []  # phrases qu'Orion doit dire de lui-même (fin de compte à rebours), lues par ecouter()

    def surveiller_minuteur():
        """Fil de fond : affiche le décompte ; à la fin, 5 bips lents ; sans clic, Orion l'annonce."""
        from . import minuteur
        while True:
            m = cerveau.minuteur
            holo.decompte = (m["fin"], m["total"]) if m else None
            if m and time.monotonic() >= m["fin"]:
                cerveau.minuteur, holo.decompte = None, None
                holo.sonnerie, holo.acquitte = True, False
                for _ in range(5):  # la fin du décompte sonne toujours, même si le bip d'écoute est coupé
                    if holo.acquitte:
                        break
                    bip(0.18)
                    time.sleep(1.6)
                holo.sonnerie = False
                duree = minuteur.en_mots(m["total"])
                if not holo.acquitte:
                    pour = m["pour"]
                    annonces.append(f"Le compte à rebours de {duree} est terminé." if pour == "invité" else
                                    cerveau._adapter(f"{pour}, ton compte à rebours de {duree} est terminé.", pour))
                holo.derniere_action(f"{time.strftime('%H:%M')} · compte à rebours de {duree} terminé")
            time.sleep(0.2)
    threading.Thread(target=surveiller_minuteur, daemon=True).start()

    eveil_jusqua = 0.0
    dernier_locuteur = None
    dernier_reconnu = None  # dernière personne reconnue à sa voix pendant cette session
    formule = f"dis-moi {cfg['nom']}"
    etait_eveille = False
    while True:
        if _date_config() != config_vue["date"]:  # réglages modifiés dans le panneau : appliqués tout de suite
            recharger()
        eveille = time.time() < eveil_jusqua
        if eveille and not etait_eveille and cfg.get("bip_ecoute", True):
            oreille.muet = True  # le bip ne doit pas être transcrit
            bip()  # prêt à écouter (après avoir fini de parler) : signal sonore, sans regarder l'écran
            time.sleep(0.1)
            reprendre_micro()
        if not eveille:
            holo.interlocuteur("")  # conversation terminée
        etait_eveille = eveille
        holo.changer("ecoute" if eveille else "veille", "Je t'écoute…" if eveille else f"« {formule} »")
        texte, empreinte = ecouter(eveille)
        if texte is None:  # clic sur l'hologramme : comme « dis Orion »… sauf si l'on s'acharne
            clics["en_attente"] = False
            maintenant = time.time()
            clics["recents"] = [c for c in clics["recents"] if maintenant - c < 15] + [maintenant]
            if len(clics["recents"]) >= 5:
                clics["recents"] = []
                holo.changer("parole", "Du calme…")
                parler(random.choice(TROP_DE_CLICS))
            else:
                holo.changer("ecoute", "Je t'écoute…")
                parler(random.choice(["Oui ?", "Je t'écoute.", "Oui, dis-moi."]))
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        # le micro est coupé pendant qu'Orion parle : seul un long écho résiduel peut encore arriver ;
        # une réponse courte (« oui », « non ») n'est jamais prise pour de l'écho
        if len(texte.split()) >= 3 and time.time() - dernier_dit["quand"] < 6 and est_echo(texte, dernier_dit["texte"]) \
                and not trouver_eveil(texte, cfg["mots_eveil"], cfg["formules_eveil"])[0]:
            print(f"[écho ignoré] {texte}", flush=True)
            continue
        t = normaliser(texte)
        nomme, sans_nom = trouver_eveil(texte, cfg["mots_eveil"], cfg["formules_eveil"])
        print(f"[entendu{' (éveillé)' if eveille else ''}{' · formule reconnue' if nomme else ''} · confiance "
              f"{oreille.confiance:.2f}] {texte}", flush=True)
        if not eveille and not nomme:
            continue
        profils.data = Profils(cfg["seuil_locuteur"]).data  # voix ajoutées ou retirées depuis le panneau
        # l'empreinte d'une phrase très courte (« dis-moi Orion », « oui ») est peu fiable : on garde alors
        # la personne reconnue juste avant plutôt que de la déclarer inconnue
        courte = len(texte.split()) < 4
        locuteur = profils.identifier(empreinte)
        if locuteur == "invité" and courte and dernier_reconnu:
            locuteur = dernier_reconnu
        print(f"[voix : {locuteur} · ressemblance {profils.score:.2f} / seuil {cfg['seuil_locuteur']}"
              f"{' · phrase courte' if courte else ''}]", flush=True)
        if locuteur != "invité" and profils.score >= cfg["seuil_locuteur"] + 0.05 and not courte:
            profils.apprendre(locuteur, empreinte)  # reconnu avec assurance : Orion affine sa mémoire de la voix
        # continuité : une phrase courte ou peu claire en pleine discussion vient du même interlocuteur
        if locuteur == "invité" and eveille and dernier_locuteur not in (None, "invité"):
            locuteur = dernier_locuteur
        dernier_locuteur = locuteur
        # première fois qu'on l'entend, ou quelqu'un d'autre prend la parole : Orion montre qu'il l'a reconnu
        nouveau = locuteur != "invité" and locuteur != dernier_reconnu
        if locuteur != "invité":
            dernier_reconnu = locuteur
        holo.interlocuteur("" if locuteur == "invité" else locuteur, personnes.couleur(locuteur))
        if nomme and not sans_nom.strip():  # « dis Orion » seul : couleur d'écoute, puis on attend la demande
            holo.changer("ecoute", "Je t'écoute…")
            if nouveau:
                parler(cerveau._adapter(random.choice([
                    f"Je t'écoute, {locuteur}.", f"Ah, c'est toi {locuteur} ! Je t'écoute.",
                    f"Bonjour {locuteur}, que puis-je faire pour toi ?"]), locuteur))
            else:
                parler(random.choice(["Oui ?", "Je t'écoute.", "Oui, dis-moi."]))
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        if oreille.confiance < cfg["confiance_min"]:
            parler(random.choice(["Pardon, je n'ai pas bien compris.", "Tu peux répéter ?",
                                  "Je n'ai pas bien entendu, tu peux répéter ?"]))
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        if stop_lexique(texte) and len(texte.split()) <= 3:
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        reste = re.sub(STOP, "", sans_nom)
        if not reste.strip():  # juste « stop » ou « Orion, tais-toi » : on se tait et on écoute
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        holo.changer("reflexion", f"{locuteur} : {texte}")
        phrase_fr = cerveau.en_francais(sans_nom if nomme else texte, discussion, traducteur)
        t_fr = normaliser(phrase_fr)
        m = re.search(r"\b(?:parle|parlons|discutons|discute|on parle)(?: avec moi)? en (\w+)", t_fr)
        code = _langue_demandee(m.group(1)) if m else None
        if code:
            reponse, tache = changer_discussion(code), None
        else:
            reponse, tache = cerveau.repondre(phrase_fr, locuteur)
        if tache:
            holo.changer("execution", "J'exécute…")
            oreille.muet = True  # pendant la tâche, ses annonces de progression ne doivent pas être entendues
            reponse = tache()
            reprendre_micro()
            holo.derniere_action(f"{time.strftime('%H:%M')} · {reponse}")
            holo.progression("")
        if cerveau.a_recharger:  # après une installation ou « recharge-toi » : on applique avant de répondre
            cerveau.a_recharger = False
            recharger()
        if nouveau and reponse and not normaliser(reponse).startswith(normaliser(locuteur)):
            reponse = f"{random.choice(['Ah', 'Bonjour', 'Tiens'])} {locuteur}. {reponse}"
        print(f"[{cfg['nom']}] {reponse}", flush=True)
        if locuteur != "invité":  # couleur éventuellement choisie à l'instant
            holo.interlocuteur(locuteur, personnes.couleur(locuteur))
        coupe = dire(reponse) is False
        if cerveau.demande_enrolement:
            enregistrer_voix(cerveau.demande_enrolement)
            cerveau.demande_enrolement = None
        # reste à l'écoute seulement si Orion attend une réponse (question posée), sinon se rendort
        attend = (reponse or "").rstrip().endswith("?") or cerveau.en_attente or cerveau.ville_demandee is not None or cerveau.question_tutoiement \
            or cerveau.oubli_a_confirmer or cerveau.retrait_voix
        # interrompu en pleine phrase : on reste à l'écoute de ce qui suit
        eveil_jusqua = time.time() + cfg["fenetre_conversation_s"] if attend or coupe else 0.0


def demo_holo(holo):
    holo.source_niveau = lambda: abs(math.sin(time.time() * 3.1) * math.sin(time.time() * 1.7))
    for etat in ["veille", "ecoute", "reflexion", "parole", "execution"] * 50:
        holo.changer(etat, etat)
        if etat == "execution":  # tâche simulée : texte en petit et barre de progression
            for i in range(31):
                holo.progression("Démonstration : téléchargement…", i / 30)
                time.sleep(0.1)
            holo.progression("")
        else:
            time.sleep(3)


def main():
    cfg = charger()
    args = sys.argv[1:]
    commande = args[0] if args else "vocal"
    if commande == "texte":
        return mode_texte(cfg)
    if commande == "savoir":
        return print(f"{knowledge.construire()} fiches indexées.")
    if commande == "panneau":
        from .panneau import Panneau
        return Panneau().lancer()
    if commande == "apprendre":
        from . import web
        print(web.AVERTISSEMENT)
        _, message = web.apprendre(args[1], " ".join(args[2:]) or None)
        return print(message)
    if commande == "verifier":
        from . import web
        for statut, titre, url in web.verifier_references():
            print(f"{statut:5} {titre}\n      {url}")
        return None
    if commande == "dossiers":
        return commande_dossiers(cfg, args[1:])
    if commande == "limite":
        return commande_limite(cfg, args[1] if len(args) > 1 else None)
    if commande == "enroler":
        return enroler(cfg, args[1] if len(args) > 1 else input("Prénom : "))
    from .hologramme import Hologramme
    holo = Hologramme(cfg)
    cible = demo_holo if commande == "holo" else lambda h: boucle_vocale(cfg, h)
    threading.Thread(target=cible, args=(holo,), daemon=True).start()
    holo.lancer()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
