# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Limite de l'espace disque occupé par Orion, pour ne jamais remplir un disque.

Seules les données internes d'Orion comptent : modèles vocaux, langues et mémoire. Les documents qu'il génère
(fiches, crédits PDF) appartiennent à l'utilisateur et sont rangés dans ses dossiers (voir dossiers.py) : ils
ne comptent pas. Quand la limite approche, Orion prévient ; quand elle est atteinte, il s'allège (historiques
raccourcis), et sinon il refuse poliment. La limite se règle dans le panneau ou en ligne de commande, jamais à la voix.
"""
import shutil

from .config import DONNEES, UTILISATEUR

LIMITE_DEFAUT_MO = 1024
SEUIL_ALERTE = 0.8
MO = 1_000_000


def mo(octets):
    """Taille lisible : une décimale sous 10 Mo."""
    if octets >= 1000 * MO:
        return f"{octets / (1000 * MO):.1f}".replace(".", ",") + " Go"
    texte = f"{octets / MO:.1f}" if octets < 10 * MO else f"{octets / MO:.0f}"
    return texte.replace(".", ",") + " Mo"


def _taille(chemin):
    if chemin.is_file():
        return chemin.stat().st_size
    if chemin.is_dir():
        return sum(f.stat().st_size for f in chemin.rglob("*") if f.is_file())
    return 0


def categories():
    """{libellé: octets} — uniquement ce qu'Orion a écrit."""
    memoire = sum(_taille(DONNEES / n) for n in ("savoir.db", "appris.json", "personnes.json", "profils_voix.json",
                                                 "references.json"))
    return {
        "Modèles vocaux (français)": _taille(UTILISATEUR / "models"),
        "Langues supplémentaires": _taille(UTILISATEUR / "langues"),
        "Voix naturelles (Piper)": _taille(UTILISATEUR / "voix_neuronales"),
        "Conversation (moteur et modèle locaux)": _taille(UTILISATEUR / "conversation"),
        "Mémoire (savoir appris, personnes, voix)": memoire,
    }


def occupe():
    return sum(categories().values())


def limite(cfg):
    return int(cfg.get("limite_disque_mo", LIMITE_DEFAUT_MO)) * MO


def libre():
    UTILISATEUR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(UTILISATEUR).free


def etat(cfg):
    """(occupé, limite, ratio)."""
    o, l = occupe(), limite(cfg)
    return o, l, o / l if l else 1.0


def alerte(cfg):
    """Message à dire si le seuil d'alerte est dépassé, sinon None."""
    o, l, r = etat(cfg)
    if r < SEUIL_ALERTE:
        return None
    return (f"Attention : j'occupe {mo(o)} sur les {mo(l)} autorisés. Pour augmenter cette "
            "limite, passe par le panneau, onglet Réglages.")


def alleger(cible_octets=0):
    """Libère de la place sans rien perdre d'important : historiques réduits aux 5 derniers échanges.
    Les souvenirs demandés, les voix et les langues ne sont jamais supprimés automatiquement.
    Renvoie le nombre d'octets libérés."""
    from . import personnes
    avant = occupe()
    personnes.raccourcir_historiques(5)
    return avant - occupe()


def place_pour(cfg, octets):
    """Vrai si `octets` supplémentaires tiennent dans la limite, après allègement si nécessaire."""
    depassement = occupe() + octets - limite(cfg)
    if depassement <= 0:
        return True
    alleger(depassement)
    return occupe() + octets <= limite(cfg)


def refus(cfg):
    return (f"Je n'ai plus de place pour retenir ou créer quoi que ce soit : mon espace est limité à "
            f"{mo(limite(cfg))} par la configuration, et il est plein. On peut augmenter cette limite dans le "
            "panneau, onglet Réglages.")


def verifier_nouvelle_limite(mo):
    """Avertissements à montrer avant de confirmer une nouvelle limite (liste vide si tout est cohérent)."""
    avertissements = []
    o, disponible = occupe(), libre()
    if mo * MO < o:
        avertissements.append(f"Orion occupe déjà {o / MO:.0f} Mo : avec {mo} Mo, il devra s'alléger et ne "
                              "pourra plus rien mémoriser de nouveau.")
    if mo * MO - o > disponible:
        avertissements.append(f"Il ne reste que {disponible / MO:.0f} Mo libres sur le disque : une limite de "
                              f"{mo} Mo ne pourrait pas être atteinte, et risquerait de remplir le disque.")
    elif mo * MO - o > disponible * 0.5:
        avertissements.append(f"Cette limite permettrait à Orion d'utiliser plus de la moitié de l'espace libre "
                              f"restant ({disponible / MO:.0f} Mo).")
    if mo < 100:
        avertissements.append("En dessous de 100 Mo, les modèles vocaux français eux-mêmes ne tiennent pas.")
    return avertissements
