# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Météo dite à voix haute, depuis Open-Meteo (open-meteo.com, données CC BY 4.0, sans clé ni compte).

Une requête par question, rien n'est stocké. La Chaîne Météo refuse la lecture automatisée : elle n'est
qu'ouverte à l'écran, à la demande (« montre-moi la météo »).
"""
import datetime
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Orion-assistant/1.0 (assistant familial)"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
QUAND = r"\b(aujourd hui|demain|apres demain|ce soir|ce matin|cet apres midi|" + "|".join(JOURS) + r")\b"

# Codes météo de l'Organisation météorologique mondiale (WMO), utilisés par Open-Meteo
CIEL = [((0,), "ciel dégagé"), ((1,), "plutôt ensoleillé"), ((2,), "partiellement nuageux"), ((3,), "couvert"),
        ((45, 48), "brouillard"), ((51, 53, 55, 56, 57), "bruine"), ((61, 63, 80, 81), "pluie"),
        ((65, 82), "forte pluie"), ((66, 67), "pluie verglaçante"), ((71, 73, 77, 85), "neige"),
        ((75, 86), "forte neige"), ((95,), "orages"), ((96, 99), "orages avec grêle")]


def _ciel(code):
    return next((mot for codes, mot in CIEL if code in codes), "temps variable")


def _degres(x):
    x = round(x)
    return f"moins {-x}" if x < 0 else str(x)  # « -2 » serait mal lu par la synthèse vocale


def _lire(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
        return json.load(r)


def jour_vise(t):
    """Nombre de jours à partir d'aujourd'hui (0 à 6) d'après la phrase normalisée."""
    if re.search(r"\bapres demain\b", t):
        return 2
    if re.search(r"\bdemain\b", t):
        return 1
    for i, j in enumerate(JOURS):
        if re.search(rf"\b{j}\b", t):
            return (i - datetime.date.today().weekday()) % 7
    return 0


def ville_dans(t):
    """« météo à Lyon demain » → « lyon » ; chaîne vide si aucune ville n'est citée."""
    m = re.search(r"\b(?:a|sur|pour|de) ([a-z][a-z -]*)$", re.sub(QUAND, " ", t).strip())
    ville = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return "" if ville in ("la", "le", "les", "") else ville


def bulletin(ville, t=""):
    """Phrase à dire : « À Lyon demain : pluie, entre 6 et 12 degrés… », ou None si la ville est inconnue."""
    lieux = _lire("https://geocoding-api.open-meteo.com/v1/search?count=1&language=fr&name="
                  + urllib.parse.quote(ville)).get("results")
    if not lieux:
        return None
    lieu = lieux[0]
    p = _lire(f"https://api.open-meteo.com/v1/forecast?latitude={lieu['latitude']}&longitude={lieu['longitude']}"
              "&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto&forecast_days=7"
              "&daily=weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max,"
              "wind_speed_10m_max")
    n, d = jour_vise(t), p["daily"]
    quand = ["aujourd'hui", "demain", "après-demain"][n] if n < 3 else \
        JOURS[(datetime.date.today().weekday() + n) % 7]
    texte = (f"À {lieu['name']} {quand} : {_ciel(d['weather_code'][n])}, entre "
             f"{_degres(d['temperature_2m_min'][n])} et {_degres(d['temperature_2m_max'][n])} degrés")
    pluie = d["precipitation_probability_max"][n]
    if pluie is not None and pluie >= 30:
        texte += f", {pluie} % de risque de pluie"
    vent = d["wind_speed_10m_max"][n]
    if vent >= 40:
        texte += f", vent fort jusqu'à {round(vent)} kilomètres heure"
    if n == 0:
        texte += (f". En ce moment, il fait {_degres(p['current']['temperature_2m'])} degrés, "
                  f"{_ciel(p['current']['weather_code'])}")
    return texte + "."
