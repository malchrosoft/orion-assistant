# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Extrait d'une image de visage holographique les points lumineux qui servent de base à l'hologramme.

  .venv/bin/python outils/extraire_visage.py IMAGE.png [nombre_de_points]
Écrit orion/data/visage_points.json (coordonnées normalisées, luminosité, rôle : œil, bouche…) et un aperçu
sources_privees/apercu_points.png. Tkinter lit le PNG : aucune dépendance.
"""
import json
import random
import sys
import tkinter as tk
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent


def luminosite(pixel):
    r, g, b = pixel[:3]
    return (0.3 * r + 0.55 * g + 0.15 * b) / 255


def main():
    image, voulu = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 900
    racine = tk.Tk()
    racine.withdraw()
    img = tk.PhotoImage(file=image)
    l, h = img.width(), img.height()
    # Zone de la tête et du cou : ellipse centrée (évite le bokeh et l'anneau du fond)
    cx, cy, rx, ry = l * 0.5, h * 0.47, l * 0.17, h * 0.47
    grille = {}
    for y in range(0, h, 2):
        for x in range(0, l, 2):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            if dx * dx + dy * dy < 1.15 or (abs(x - cx) < rx * 0.6 and y > cy + ry * 0.7):
                grille[(x, y)] = luminosite(img.get(x, y))
    candidats = []
    for (x, y), lum in grille.items():
        dx, dy = (x - cx) / rx, (y - cy) / ry
        if not (dx * dx + dy * dy < 1 or (abs(x - cx) < rx * 0.55 and y > cy + ry * 0.75)):
            continue
        voisins = [grille.get((x + i, y + j), lum) for i in (-6, -4, 4, 6) for j in (-6, -4, 4, 6)]
        contraste = lum - sum(voisins) / len(voisins)  # point plus brillant que son voisinage : un « pixel » du visage
        if lum > 0.25 and contraste > 0.02:
            candidats.append((x, y, lum, contraste))
    rnd = random.Random(5)
    # tirage pondéré par contraste et luminosité : les traits (yeux, nez, lèvres) ressortent, pas la lueur des bords
    choisis = rnd.choices(candidats, weights=[(c[3] ** 1.2) * (c[2] ** 2) for c in candidats],
                          k=min(voulu, len(candidats)))
    choisis = [(x, y, lum) for x, y, lum, _ in choisis]
    choisis = list({(x, y): (x, y, lum) for x, y, lum in choisis}.values())
    echelle = ry
    points = []
    for x, y, lum in choisis:
        nx, ny = (x - cx) / echelle, (y - cy) / echelle
        role = "visage"
        if abs(ny + 0.12) < 0.08 and 0.08 < abs(nx) < 0.38:
            role = "oeil"
        elif abs(nx) < 0.22 and 0.36 < ny < 0.50:
            role = "levre_haut" if ny < 0.43 else "levre_bas"
        elif ny > 0.82:
            role = "cou"
        points.append([round(nx, 4), round(ny, 4), round(lum, 3), role])
    sortie = ICI / "orion" / "data" / "visage_points.json"
    sortie.write_text(json.dumps({"source": Path(image).name, "points": points}), encoding="utf-8")
    # aperçu
    apercu = tk.PhotoImage(width=500, height=500)
    apercu.put("#01030a", to=(0, 0, 500, 500))
    for nx, ny, lum, role in points:
        px, py = int(250 + nx * 220), int(240 + ny * 220)
        couleur = "#ffd080" if role.startswith("levre") else "#ff6060" if role == "oeil" else \
            "#%02x%02x%02x" % (int(60 * lum), int(220 * lum), 255)
        if 0 <= px < 499 and 0 <= py < 499:
            apercu.put(couleur, to=(px, py, px + 2, py + 2))
    (ICI / "sources_privees").mkdir(exist_ok=True)
    apercu.write(str(ICI / "sources_privees" / "apercu_points.png"), format="png")
    print(f"{len(points)} points extraits ({len(candidats)} candidats) → {sortie}")
    carte_lumiere(img, cx, cy, ry)


def carte_lumiere(img, cx, cy, ry, px_par_unite=128, x_min=-0.8, x_max=0.8, y_min=-1.0, y_max=1.12):
    """Carte de luminosité du visage (niveaux de gris, fond masqué) que l'hologramme colore selon l'état.
    Stockée compressée (zlib + base64) : quelques dizaines de Ko, décodée instantanément."""
    import base64
    import zlib
    largeur, hauteur = int((x_max - x_min) * px_par_unite), int((y_max - y_min) * px_par_unite)
    octets = bytearray()
    for j in range(hauteur):
        ny = y_min + j / px_par_unite
        for i in range(largeur):
            nx = x_min + i / px_par_unite
            # masque doux : tête (ellipse) et cou ; le fond (bokeh, anneau) disparaît
            d = (nx / 0.62) ** 2 + ((ny + 0.02) / 0.98) ** 2
            tete = max(0.0, min(1.0, (1.08 - d) / 0.12))
            largeur_cou = 0.30 + 0.06 * max(0.0, ny - 0.75)          # cou qui s'évase légèrement
            cou = max(0.0, min(1.0, (largeur_cou - abs(nx)) / 0.08)) * max(0.0, min(1.0, (y_max - ny) / 0.25)) \
                if ny > 0.62 else 0.0
            masque = max(tete, cou)
            if masque <= 0:
                octets.append(0)
                continue
            x, y = int(cx + nx * ry), int(cy + ny * ry)
            total = 0.0
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                total += luminosite(img.get(min(img.width() - 1, x + dx), min(img.height() - 1, y + dy)))
            lum = max(0.0, min(1.0, (total / 4 - 0.12) / 0.88)) ** 1.25 * masque
            octets.append(int(lum * 255))
    donnees = {"largeur": largeur, "hauteur": hauteur, "px_par_unite": px_par_unite, "x_min": x_min,
               "y_min": y_min, "source": "Carte extraite d'une image générée avec Gemini (Google) ; l'image n'est "
                                         "pas diffusée.",
               "lumiere": base64.b64encode(zlib.compress(bytes(octets), 9)).decode()}
    sortie = ICI / "orion" / "data" / "visage_lumiere.json"
    sortie.write_text(json.dumps(donnees), encoding="utf-8")
    print(f"Carte de luminosité {largeur}×{hauteur} → {sortie} ({sortie.stat().st_size // 1000} Ko)")


if __name__ == "__main__":
    main()
