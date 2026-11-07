"""Point d'entrée.

  python -m orion              assistant vocal + hologramme
  python -m orion texte        conversation au clavier (sans micro ni modèle)
  python -m orion enroler Nom  enregistre la voix d'un membre de la famille
  python -m orion savoir       reconstruit la base de savoir après modification de savoir.json
  python -m orion holo         démo de l'hologramme (fait défiler les états)
  python -m orion panneau      interface graphique (discussion, savoir, famille, réglages)
  python -m orion apprendre URL [sujet]   retient une page web (toujours marquée non vérifiée)
  python -m orion verifier     vérifie en ligne les références livrées
"""
import sys
import threading
import time

from . import knowledge
from .actions import Actions
from .brain import Cerveau
from .config import charger
from .texte import normaliser


def mode_texte(cfg):
    cerveau = Cerveau(cfg, Actions(cfg))
    print(f"{cfg['nom']} (mode texte) — Ctrl+C pour quitter")
    while True:
        try:
            phrase = input("toi > ")
        except (EOFError, KeyboardInterrupt):
            return
        reponse, tache = cerveau.repondre(phrase, "invité")
        print(f"{cfg['nom']} > {tache() if tache else reponse}")
        for src in (cerveau.derniere_fiche or {}).get("sources", []) if not tache else []:
            print(f"     [{src['niveau']}] {'source' if src['portee'] == 'fiche' else 'pour aller plus loin'} : "
                  f"{src['titre']} — {src['url']}"
                  f"{'' if src['consulte'] else '  (non vérifiée)'}")


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


def _langue_demandee(t):
    """« anglais » → "en" ; None si aucune langue reconnue."""
    from .bouche import LANGUES
    return next((c for c, nom in LANGUES.items() if normaliser(nom) in t.split()), None)


def boucle_vocale(cfg, holo):
    import re
    from . import modeles
    from .bouche import LANGUES, Bouche, voix_pour
    from .config import RACINE, sauver
    from .voix import Oreille, Profils
    if modeles.manquants(RACINE / "models"):
        holo.changer("execution", "Premier lancement : téléchargement des modèles…")
        modeles.installer(RACINE / "models")
    holo.changer("reflexion", "Chargement…")
    oreille, bouche = Oreille(cfg), Bouche(cfg)
    profils, cerveau = Profils(cfg["seuil_locuteur"]), Cerveau(cfg, Actions(cfg))
    holo.sur_silence = bouche.interrompre  # clic droit → « Se taire »
    eveil_jusqua = 0.0

    def parler(texte):
        """Parle en continuant d'écouter : « stop », « tais-toi » ou le nom d'Orion l'interrompent.
        Pour ne pas s'interrompre sur son propre écho, on ignore les mots qu'Orion est en train de dire."""
        holo.changer("parole", texte)
        dits = set(normaliser(texte).split())
        fini = threading.Event()
        threading.Thread(target=lambda: (bouche.dire(texte), fini.set()), daemon=True).start()
        oreille.vider()
        while not fini.is_set():
            entendu, final, _ = oreille.lire()
            nouveaux = " ".join(m for m in normaliser(entendu).split() if m not in dits)
            if nouveaux and (re.search(STOP, nouveaux) or any(m in nouveaux for m in cfg["mots_eveil"])):
                bouche.interrompre()
                holo.changer("ecoute", "Je t'écoute…")
                return False  # on garde ce que l'utilisateur est en train de dire
        oreille.vider()
        return True

    def ecouter(eveille):
        """Attend une phrase complète, en affichant les mots au fur et à mesure."""
        while True:
            texte, final, empreinte = oreille.lire(0.5)
            if texte and not final and (eveille or any(m in normaliser(texte) for m in cfg["mots_eveil"])):
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
        cfg.update(langue=code, voix_id=voix[0][0], langue_confirmee=True)
        sauver(cfg)
        bouche.voix = voix[0][0]
        return f"D'accord, je parle maintenant en {nom}. Attention, je ne comprends toujours que le français."

    if not cfg["langue_confirmee"]:
        confirmer_langue()
    elif not profils.data:
        parler(f"Bonjour, je suis {cfg['nom']}. Pour que je reconnaisse chacun à sa voix, "
               "double-clique sur moi et va dans l'onglet Famille.")
    else:
        parler(f"Bonjour, je suis {cfg['nom']}.")
    while True:
        eveille = time.time() < eveil_jusqua
        holo.changer("ecoute" if eveille else "veille", "Je t'écoute…" if eveille else cfg["nom"])
        texte, empreinte = ecouter(eveille)
        t = normaliser(texte)
        if not eveille and not any(m in t[:30] for m in cfg["mots_eveil"]):
            continue
        reste = re.sub(STOP, "", t)
        for m in cfg["mots_eveil"]:
            reste = reste.replace(m, "")
        if not reste.strip():  # juste « stop » ou « Orion, tais-toi » : on se tait et on écoute
            eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]
            continue
        locuteur = profils.identifier(empreinte)
        holo.changer("reflexion", f"{locuteur} : {texte}")
        m = re.search(r"\bparle (?:en )?(\w+)", t)
        if m and _langue_demandee(m.group(1)):
            reponse, tache = changer_langue(_langue_demandee(m.group(1))), None
        else:
            reponse, tache = cerveau.repondre(texte, locuteur)
        if tache:
            holo.changer("execution", "J'exécute…")
            reponse = tache()
        parler(reponse)
        eveil_jusqua = time.time() + cfg["fenetre_conversation_s"]


def demo_holo(holo):
    for etat in ["veille", "ecoute", "reflexion", "parole", "execution"] * 50:
        holo.changer(etat, etat)
        time.sleep(3)


def main():
    cfg = charger()
    args = sys.argv[1:]
    commande = args[0] if args else "vocal"
    if commande == "texte":
        return mode_texte(cfg)
    if commande == "savoir":
        return print(f"{knowledge.construire()} fiches indexées.")
    if commande == "worker-voix":
        from .bouche import worker
        return worker()
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
    if commande == "enroler":
        return enroler(cfg, args[1] if len(args) > 1 else input("Prénom : "))
    from .hologramme import Hologramme
    holo = Hologramme(cfg)
    cible = demo_holo if commande == "holo" else lambda h: boucle_vocale(cfg, h)
    threading.Thread(target=cible, args=(holo,), daemon=True).start()
    holo.lancer()


if __name__ == "__main__":
    main()
