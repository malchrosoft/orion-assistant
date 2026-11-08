# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Blagues pour toute la famille : JokeAPI (v2.jokeapi.dev, libre, sans clé, blagues en français) avec un
double filtre, sinon une petite réserve locale (hors ligne, ou si rien ne passe le filtre).

Le « mode sûr » de JokeAPI ne suffit pas en français : des blagues racistes ou grivoises y sont mal
étiquetées, et une liste de mots interdits n'en vient pas à bout. La réserve locale, relue, est donc la
source par défaut ; internet n'est utilisé que si le réglage « blagues_internet » est activé.
"""
import json
import random
import re
import urllib.request

from .texte import normaliser

API = ("https://v2.jokeapi.dev/joke/Pun,Misc,Programming?lang=fr&safe-mode&amount=10"
       "&blacklistFlags=nsfw,religious,political,racist,sexist,explicit")
UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
INTERDITS = re.compile(
    r"\b(noirs?|blancs?|arabes?|juifs?|chinois|asiatiques?|race|blondes?|femmes?|belle mere|viagra|sexe|sexy|nue?s?|"
    r"seins?|fesses?|gay|homos?|enfer|satan|diable|dieu|jesus|religion|alcool|biere|vin|bourre|drogues?|mort|morts|"
    r"tuer|tue|sang|armes?|fusil|pitbull|bras|accident|suicide|cancer|handicape|gros|grosse|moche|idiot|con|conne|"
    r"merde|putain|cul|mamadou|zoophiles?|bar|bars)\b")
RESERVE = [
    ("Que font deux brosses à dents le 14 juillet ?", "Un feu dentifrice !"),
    ("Qu'est-ce qui a trois bosses ?", "Un chameau qui s'est cogné."),
    ("Pourquoi les poissons vivent-ils dans l'eau salée ?", "Parce que dans l'eau poivrée, ils éternuent !"),
    ("Quel est le comble pour un électricien ?", "De ne pas être au courant."),
    ("Que dit une imprimante dans l'eau ?", "J'ai papier !"),
    ("Pourquoi les plongeurs plongent-ils toujours en arrière ?", "Parce que sinon, ils tombent dans le bateau."),
    ("Quel est le sport le plus silencieux ?", "Le para-chuuut."),
    ("Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ?", "Un chat-mallow."),
    ("Quel est le comble pour un jardinier ?", "De raconter des salades."),
    ("Que dit un zéro à un huit ?", "Jolie ceinture !"),
    ("Pourquoi les canards sont-ils toujours à l'heure ?", "Parce qu'ils sont dans l'étang."),
    ("Qu'est-ce qu'un crocodile qui surveille la pharmacie ?", "Un Lacoste garde."),
    ("Quel est le fruit préféré des profs d'histoire ?", "Les dattes."),
    ("Comment appelle-t-on un boomerang qui ne revient pas ?", "Un bâton."),
    ("Pourquoi le livre de maths est-il triste ?", "Parce qu'il a trop de problèmes."),
    ("Que dit une maman tomate à son petit qui traîne ?", "Ketchup !"),
    ("Quel est le comble pour un cordonnier ?", "D'avoir les pieds dans le plat."),
    ("Que fait un crocodile quand il rencontre une superbe crocodile ?", "Il Lacoste."),
    ("Pourquoi les éléphants n'utilisent-ils pas d'ordinateur ?", "Parce qu'ils ont peur de la souris."),
    ("Comment appelle-t-on un chien qui fait de la magie ?", "Un labracadabrador."),
    ("Qu'est-ce qui est jaune et qui attend ?", "Jonathan."),
    ("Quel est le comble pour un professeur de musique ?", "De perdre la note."),
    ("Que dit un oignon quand il se cogne ?", "Aïe ! Ça fait pleurer."),
    ("Pourquoi les vaches ferment-elles les yeux quand on les trait ?", "Pour faire du lait concentré."),
    ("Quel animal a le plus de dents ?", "La petite souris."),
    ("Quelle est la ville la plus calme de France ?", "Chut-tgart… ah non, ça, c'est en Allemagne !"),
    ("Pourquoi le football, c'est rigolo ?", "Parce que Thierry en rit."),
    ("Que dit un escargot sur le dos d'une tortue ?", "Youhouuu, ça va vite !"),
    ("Quel est le comble pour un boulanger ?", "D'être dans le pétrin."),
    ("Que dit une puce à une autre puce ?", "On prend le chien ou on y va à pied ?"),
]


def convenable(texte):
    return not INTERDITS.search(normaliser(texte))


def en_ligne():
    """(question, chute) d'une blague récupérée et filtrée, ou None."""
    with urllib.request.urlopen(urllib.request.Request(API, headers=UA), timeout=8) as r:
        donnees = json.load(r)
    blagues = donnees.get("jokes") or ([donnees] if donnees.get("type") else [])
    random.shuffle(blagues)
    for b in blagues:
        partie = (b["setup"], b["delivery"]) if b.get("type") == "twopart" else (b.get("joke", ""), "")
        if partie[0] and convenable(" ".join(partie)):
            return partie
    return None


def blague(internet=False):
    """(question, chute) : en ligne si permis et disponible, sinon dans la réserve locale."""
    if internet:
        try:
            trouvee = en_ligne()
            if trouvee:
                return trouvee
        except Exception:
            pass
    if not _paquet:  # toutes racontées une fois avant de recommencer, dans un nouvel ordre
        _paquet.extend(random.sample(RESERVE, len(RESERVE)))
    return _paquet.pop()


_paquet = []
