# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Hologramme en Tkinter pur : une tête de trois quarts faite d'une nuée de points lumineux.

La tête est un nuage de points en 3D (front, arcades, nez, pommettes, lèvres, menton, cou, chevelure) projeté
avec une légère rotation : les points proches brillent, ceux de l'arrière s'estompent. Autour : bulles de
lumière floues (bokeh), anneaux et traînées d'énergie, quelques étincelles chaudes. En veille, la nuée se
disperse et s'assombrit ; à l'écoute, elle se rassemble et s'illumine en cyan. Chaque changement d'état
brouille brièvement l'image (points dispersés, traînées), puis la tête se recompose.

Léger : toutes les formes sont créées une fois puis déplacées (coords/itemconfig). Densité réglable
(cfg["hologramme"]["densite"]) pour les machines modestes.
États : veille, ecoute, reflexion, parole, execution.
"""
import json
import math
import random
import subprocess
import sys
import tkinter as tk

COULEURS = {  # (points, halo) — les transitions sont fondues
    "veille": ("#4a7f99", "#08202b"),
    "ecoute": ("#62f6ff", "#0e5c70"),
    "reflexion": ("#c7a8ff", "#35226e"),
    "parole": ("#bdfcff", "#11798c"),
    "execution": ("#ffc46b", "#6e4000"),
}
CHAUD = "#ffd8a0"
SEUIL_NOIR = 28  # sur 255 : en dessous, un pixel du visage est considéré comme du fond (transparent)
FOND = "#01030a"
RASSEMBLEMENT = {"veille": 0.35, "ecoute": 1.0, "reflexion": 0.92, "parole": 1.0, "execution": 0.8}
ECLAT = {"veille": 0.55, "ecoute": 1.0, "reflexion": 0.9, "parole": 1.0, "execution": 0.95}
AGITATION = {"veille": 0.5, "ecoute": 0.18, "reflexion": 0.45, "parole": 0.22, "execution": 0.8}


def _rvb(c):
    return [int(c[i:i + 2], 16) for i in (1, 3, 5)]


def melange(a, b, k):
    """Couleur entre a et b (k=0 → a, k=1 → b). Tk n'a pas de transparence : on simule halos et fondus."""
    k = max(0.0, min(1.0, k))
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * k) for x, y in zip(_rvb(a), _rvb(b)))


def _bosse(x, y, cx, cy, sx, sy):
    return math.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))


def _carte_lumiere():
    """Carte de luminosité du visage (outils/extraire_visage.py) : (largeur, hauteur, octets, réglages) ou None."""
    import base64
    import zlib
    from .config import DATA
    fichier = DATA / "visage_lumiere.json"
    if not fichier.exists():
        return None
    d = json.loads(fichier.read_text(encoding="utf-8"))
    return d["largeur"], d["hauteur"], zlib.decompress(base64.b64decode(d["lumiere"])), d


def image_dispo():
    from .config import DATA
    return (DATA / "visage_lumiere.json").exists()


def _tete_image(densite):
    """Points extraits d'une image de visage (outils/extraire_visage.py), s'ils existent : (x, y, z, rôle, lum).
    Un relief arrondi donne de la profondeur au balancement de la tête."""
    from .config import DATA
    fichier = DATA / "visage_points.json"
    if not fichier.exists():
        return None
    points = json.loads(fichier.read_text(encoding="utf-8"))["points"]
    pas = max(1, len(points) // max(densite, 1))
    tete = []
    for x, y, lum, role in points[::pas]:
        x, y = x * 0.8, y * 0.8 - 0.02  # même échelle que la tête calculée
        z = 0.55 * math.sqrt(max(0.0, 1 - (x / 0.62) ** 2)) + 0.25 * (lum - 0.5)
        tete.append((x, y, z, role, lum))
    return tete


def _tete(densite, rnd):
    """Points 3D (x, y, z, rôle) d'une tête stylisée ; y vers le bas, z vers l'observateur."""
    pts = []

    def visage(x, y):
        """Profondeur du visage en (x, y), avec ses reliefs ; None hors du visage."""
        a = 0.56 * (1 - 0.28 * max(0.0, y) ** 2)          # mâchoire qui s'affine vers le menton
        b = 0.80
        r2 = (x / a) ** 2 + (y / b) ** 2
        if r2 >= 1:
            return None
        z = 0.6 * math.sqrt(1 - r2)
        z += 0.20 * _bosse(x, y, 0, 0.10, 0.05, 0.17)       # nez
        z += 0.05 * _bosse(x, y, 0, 0.24, 0.08, 0.04)       # bout du nez
        z -= 0.07 * (_bosse(x, y, -0.21, -0.11, 0.09, 0.05) + _bosse(x, y, 0.21, -0.11, 0.09, 0.05))  # orbites
        z += 0.05 * (_bosse(x, y, -0.2, -0.22, 0.14, 0.04) + _bosse(x, y, 0.2, -0.22, 0.14, 0.04))    # arcades
        z += 0.05 * (_bosse(x, y, -0.3, 0.12, 0.12, 0.12) + _bosse(x, y, 0.3, 0.12, 0.12, 0.12))      # pommettes
        z += 0.05 * _bosse(x, y, 0, 0.42, 0.14, 0.05)       # lèvres
        z += 0.06 * _bosse(x, y, 0, 0.66, 0.12, 0.08)       # menton
        return z

    n_visage, n_cheveux, n_cou = int(densite * 0.55), int(densite * 0.27), int(densite * 0.08)
    while len(pts) < n_visage:
        x, y = rnd.uniform(-0.56, 0.56), rnd.uniform(-0.8, 0.8)
        z = visage(x, y)
        if z is not None:
            pts.append((x, y, z, "visage"))
    while len(pts) < n_visage + n_cheveux:                 # chevelure : volume au-dessus et à l'arrière
        u, v = rnd.uniform(0, 2 * math.pi), rnd.uniform(-1, 0.35)
        rayon = 1.08 + rnd.uniform(0, 0.12)
        x, y, z = 0.6 * rayon * math.cos(u) * math.sqrt(1 - v * v), 0.82 * rayon * v, 0.62 * rayon * math.sin(u) * math.sqrt(1 - v * v)
        if z < 0.25 or y < -0.45:                          # pas sur le visage : arrière et sommet
            pts.append((x, y - 0.05, z - 0.08, "cheveux"))
    while len(pts) < n_visage + n_cheveux + n_cou:
        a, y = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.7, 1.2)
        pts.append((0.22 * math.cos(a), y, 0.22 * math.sin(a) - 0.1, "cou"))
    for cote in (-1, 1):                                    # traits lumineux : yeux, sourcils
        for i in range(16):
            a = 2 * math.pi * i / 16
            x, y = cote * 0.21 + math.cos(a) * 0.1, -0.11 + math.sin(a) * 0.04
            pts.append((x, y, (visage(x, y) or 0.5) + 0.01, "oeil"))
        pts.append((cote * 0.21, -0.11, (visage(cote * 0.21, -0.11) or 0.5) + 0.02, "pupille"))
        for i in range(9):
            x, y = cote * (0.11 + 0.025 * i), -0.24 - 0.025 * math.sin(math.pi * i / 8)
            pts.append((x, y, (visage(x, y) or 0.5) + 0.01, "sourcil"))
    for i in range(18):                                     # lèvres (haut et bas), animées en parole
        x = -0.14 + 0.28 * i / 17
        pts.append((x, 0.40 - 0.025 * math.sin(math.pi * i / 17), (visage(x, 0.40) or 0.5) + 0.02, "levre_haut"))
        pts.append((x, 0.43 + 0.025 * math.sin(math.pi * i / 17), (visage(x, 0.43) or 0.5) + 0.02, "levre_bas"))
    return pts


class Hologramme:
    def __init__(self, cfg):
        h = cfg["hologramme"]
        self.taille = s = h["taille"]
        self.etat, self.legende, self.t = "veille", cfg["nom"], 0.0
        self.coeur, self.halo = COULEURS["veille"]
        self.rassemble, self.eclat, self.flou = RASSEMBLEMENT["veille"], ECLAT["veille"], 0.0
        self._legende_cible, self._lettres = "", 0
        self.root = tk.Tk()
        self.root.title(cfg["nom"])
        self.root.configure(bg=FOND)
        self.root.attributes("-topmost", h["toujours_devant"])
        if h["transparent"]:
            try:  # Windows : le fond devient invisible, seul l'hologramme flotte
                self.root.attributes("-transparentcolor", FOND)
                self.root.overrideredirect(True)
            except tk.TclError:
                pass
        self.toile = c = tk.Canvas(self.root, width=s, height=s + 40, bg=FOND, highlightthickness=0)
        c.pack()
        rnd = random.Random(11)

        # Formes créées une fois pour toutes, de l'arrière-plan vers l'avant
        self.halos = [c.create_oval(0, 0, 0, 0, outline="", fill=FOND) for _ in range(5)]
        self.bokeh = [{"x": rnd.uniform(0, s), "y": rnd.uniform(0, s), "r": rnd.uniform(3, 15),
                       "v": rnd.uniform(-6, 6), "anneau": rnd.random() < 0.3, "chaud": rnd.random() < 0.25,
                       "phase": rnd.uniform(0, 6.3), "item": None} for _ in range(24)]
        for b in self.bokeh:
            b["item"] = c.create_oval(0, 0, 0, 0, outline="", fill=FOND, width=1)
        self.trainees_energie = [c.create_line(0, 0, 0, 0, fill=FOND, smooth=True, width=1) for _ in range(7)]
        # Anneau lumineux : polygones lissés pour pouvoir onduler avec la voix (écoute et parole)
        self.anneaux = [c.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline=FOND, width=w, smooth=True)
                        for w in (9, 4, 1)]
        self.source_niveau = lambda: 0.0  # volume du micro (0 à 1), branché par la boucle vocale
        self.niveau = 0.0
        # Visage précis : carte de luminosité colorée selon l'état (une image par état, préparée au démarrage)
        self.carte = _carte_lumiere() if image_dispo() else None
        self.images_etat = {}
        self.image_visage = c.create_image(0, 0, anchor="nw", state="hidden")
        if self.carte:
            for etat in COULEURS:
                self.images_etat[etat] = self._colorer(etat, s * 0.38 * 0.8)
        image = _tete_image(h.get("densite", 900))
        self.face = image is not None  # visage de face (image de référence) ou tête calculée de trois quarts
        self.tete = image or [(x, y, z, r, None) for x, y, z, r in _tete(h.get("densite", 520), rnd)]
        self.nuage = [(rnd.gauss(0, 0.75), rnd.gauss(0, 0.6), rnd.uniform(0, 6.3)) for _ in self.tete]
        self.chauds = {i for i in range(len(self.tete)) if rnd.random() < 0.04}
        self.positions = [(s / 2 + x * s * 0.4, s / 2 + y * s * 0.4) for x, y, _ in self.nuage]
        self.trainees = {i: c.create_line(0, 0, 0, 0, fill=FOND) for i in range(0, len(self.tete), 3)}
        self.points = [c.create_oval(0, 0, 0, 0, outline="", fill=FOND) for _ in self.tete]
        self.balayage = c.create_line(0, 0, 0, 0, fill=FOND, dash=(2, 6))
        self.texte = c.create_text(s / 2, s + 18, text="", fill="#ffffff", font=("Consolas", 11))

        c.bind("<ButtonPress-1>", self._debut_glisser)
        c.bind("<B1-Motion>", self._glisser)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        # Utilisateur lambda : tout est à la souris (clic droit = menu, double-clic = panneau)
        self.sur_silence = lambda: None
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Se taire", command=lambda: self.sur_silence())
        menu.add_command(label="Panneau (voix, famille, savoir, réglages)", command=self.ouvrir_panneau)
        menu.add_separator()
        menu.add_command(label=f"Quitter {cfg['nom']}", command=self.root.destroy)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        c.bind("<Button-2>", lambda e: menu.tk_popup(e.x_root, e.y_root))  # macOS
        c.bind("<Double-Button-1>", lambda e: self.ouvrir_panneau())
        self._animer()

    def _colorer(self, etat, px_par_unite_cible):
        """Image du visage teintée de la couleur de l'état (plus terne en veille), à l'échelle de l'hologramme."""
        largeur, hauteur, lum, reglages = self.carte
        f = px_par_unite_cible / reglages["px_par_unite"]
        l2, h2 = max(1, int(largeur * f)), max(1, int(hauteur * f))
        couleur, eclat = _rvb(COULEURS[etat][0]), ECLAT[etat]
        fond = _rvb(FOND)
        palette = []
        for k in range(256):  # 256 teintes précalculées : du fond à la couleur, blanchie sur les points brillants
            v = k / 255
            blanc = 0.35 * v * v
            teinte = [c + (255 - c) * blanc for c in couleur]
            palette.append("#%02x%02x%02x" % tuple(int(a + (b - a) * v * eclat) for a, b in zip(fond, teinte)))
        lignes = []
        for j in range(h2):
            src = int(j / f) * largeur
            lignes.append("{" + " ".join(palette[lum[src + int(i / f)]] for i in range(l2)) + "}")
        img = tk.PhotoImage(width=l2, height=h2)
        img.put(" ".join(lignes))
        # Le noir de l'image d'origine devient transparent : halos, anneau et bokeh restent visibles derrière
        for j in range(h2):
            src = int(j / f) * largeur
            for i in range(l2):
                if lum[src + int(i / f)] < SEUIL_NOIR:
                    img.transparency_set(i, j, True)
        return img

    def changer(self, etat, legende=None):
        """Appelable depuis n'importe quel thread."""
        if etat != self.etat:
            self.flou = 1.0  # brouillage de transition
        self.etat = etat
        if legende is not None:
            self.legende = legende[:60]

    @staticmethod
    def ouvrir_panneau():
        cmd = [sys.executable, "panneau"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "orion", "panneau"]
        subprocess.Popen(cmd)

    # Déplacement de la fenêtre sans bordure
    def _debut_glisser(self, e):
        self._dx, self._dy = e.x, e.y

    def _glisser(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _animer(self):
        c, s, t, etat = self.toile, self.taille, self.t, self.etat
        echelle = s * 0.38
        if self.carte:  # visage de face : centré exactement sur son emprise réelle (tête et cou)
            _, h_img, _, reglages = self.carte
            y_haut = 0.8 * reglages["y_min"] - 0.02
            y_bas = y_haut + 0.8 * h_img / reglages["px_par_unite"]
            cx, cy = s / 2, s / 2 - echelle * (y_haut + y_bas) / 2
        else:
            cx, cy = s * 0.52, s * 0.47
        cible_point, cible_halo = COULEURS[etat]
        self.coeur = melange(self.coeur, cible_point, 0.12)
        self.halo = melange(self.halo, cible_halo, 0.12)
        self.rassemble += (RASSEMBLEMENT[etat] - self.rassemble) * 0.08
        self.eclat += (ECLAT[etat] - self.eclat) * 0.1
        self.flou *= 0.92
        agit = AGITATION[etat] + 2.4 * self.flou

        # Bokeh : bulles de lumière floues qui dérivent lentement, quelques anneaux
        for b in self.bokeh:
            b["x"] = (b["x"] + b["v"] * 0.04) % s
            k = (0.10 + 0.08 * math.sin(t * 0.8 + b["phase"])) * (0.6 + 0.4 * self.eclat)
            teinte = melange(FOND, CHAUD if b["chaud"] else self.coeur, k * (1.6 if b["anneau"] else 1))
            r = b["r"]
            c.coords(b["item"], b["x"] - r, b["y"] - r, b["x"] + r, b["y"] + r)
            if b["anneau"]:
                c.itemconfigure(b["item"], fill="", outline=teinte)
            else:
                c.itemconfigure(b["item"], fill=teinte, outline="")

        # Halos derrière la tête (créés du plus grand au plus petit)
        for i, item in enumerate(self.halos):
            k = len(self.halos) - 1 - i
            r = echelle * (0.9 + 0.16 * k) * (1 + 0.06 * self.flou)
            intensite = (0.42 - 0.08 * k) * self.eclat * (0.4 + 0.6 * self.rassemble) + 0.15 * self.flou
            c.coords(item, cx - r * 0.8, cy - r, cx + r * 0.8, cy + r * 1.05)
            c.itemconfigure(item, fill=melange(FOND, self.halo, intensite))

        # Anneau lumineux : il ondule avec le son pendant l'écoute et la parole, cercle calme sinon
        niveau = self.source_niveau()
        if etat == "parole":  # avec un casque, le micro n'entend pas Orion : ondulation de secours
            niveau = max(niveau, 0.35 + 0.35 * abs(math.sin(t * 7) * math.sin(t * 3.3)))
        elif etat != "ecoute":
            niveau = 0.0
        self.niveau += (niveau - self.niveau) * 0.35
        amplitude = 0.075 * self.niveau
        respir = 1 + 0.025 * math.sin(t * 1.4) + 0.05 * self.flou
        for k, item in enumerate(self.anneaux):
            r0 = echelle * 1.12 * respir
            pts = []
            for n in range(72):
                a = 2 * math.pi * n / 72
                onde = (math.sin(5 * a + t * 9 + k) * 0.6 + math.sin(9 * a - t * 13) * 0.3
                        + math.sin(3 * a + t * 5) * 0.4)
                r = r0 * (1 + amplitude * onde)
                pts += [cx + r * math.cos(a), cy + r * 1.02 * math.sin(a)]
            c.coords(item, *pts)
            intensite = (0.18, 0.35, 0.75)[k] * self.eclat * (0.5 + 0.5 * self.rassemble) * (1 + 0.6 * self.niveau)
            c.itemconfigure(item, outline=melange(FOND, melange(self.coeur, "#ffffff", 0.3 * k), intensite))

        # Visage précis : visible une fois la nuée rassemblée, masqué pendant le brouillage des transitions
        balance = 2.5 * math.sin(t * 0.8)  # léger mouvement vertical, partagé avec les points
        if self.carte:
            _, _, _, reglages = self.carte
            c.coords(self.image_visage, cx + echelle * 0.8 * reglages["x_min"],
                     cy + balance + echelle * (0.8 * reglages["y_min"] - 0.02))
            visible = self.flou < 0.3 and self.rassemble > 0.6
            c.itemconfigure(self.image_visage, image=self.images_etat[etat], state="normal" if visible else "hidden")

        # Traînées d'énergie qui ondulent autour de la tête (comme des mèches de lumière)
        for j, item in enumerate(self.trainees_energie):
            pts = []
            for k in range(9):
                u = k / 8
                x = cx + echelle * (-1.6 + 3.2 * u)
                y = cy + echelle * (-0.3 + 0.12 * j + 0.18 * math.sin(u * 4 + t * (0.6 + 0.1 * j) + j))
                pts += [x, y]
            c.coords(item, *pts)
            c.itemconfigure(item, fill=melange(FOND, self.coeur, (0.10 + 0.05 * math.sin(t + j)) * self.eclat))

        # Tête de trois quarts : rotation lente, bouche qui suit la voix, clignements
        lacet = 0.0 if self.carte else (0.0 if self.face else -0.55) + (0.1 if self.face else 0.14) * math.sin(t * 0.35)
        tangage = 0.05 * math.sin(t * 0.27)
        cl, sl, ct, st = math.cos(lacet), math.sin(lacet), math.cos(tangage), math.sin(tangage)
        bouche = abs(math.sin(t * 9) * math.sin(t * 4.1)) * 0.07 if etat == "parole" else 0.0
        cligne = 0.15 if (t % 4.6) < 0.12 else 1.0
        tourbillon = etat == "execution"
        g = self.rassemble

        for i, ((vx, vy, vz, role, lum_image), (nx, ny, phase)) in enumerate(zip(self.tete, self.nuage)):
            if role == "levre_haut":
                vy -= bouche
            elif role == "levre_bas":
                vy += bouche
            elif role in ("oeil", "pupille"):
                oeil_y = -0.12 * 0.8 if self.face else -0.11
                vy = oeil_y + (vy - oeil_y) * cligne
            x3 = vx * cl + vz * sl                       # rotation (lacet puis tangage)
            z3 = -vx * sl + vz * cl
            y3 = vy * ct - z3 * st
            z3 = vy * st + z3 * ct
            profondeur = max(0.0, min(1.0, (z3 + 0.75) / 1.5))
            a = phase + t * (0.9 if tourbillon else 0.2)
            if tourbillon and role in ("cheveux", "cou"):
                nxa, nya, gi = 1.15 * math.cos(a + i), 1.1 * math.sin(a + i), g * 0.3
            else:
                nxa, nya, gi = nx + 0.08 * math.cos(a), ny + 0.08 * math.sin(a * 1.3), g
            x = cx + echelle * (nxa + (x3 - nxa) * gi) + random.gauss(0, agit * 1.5)
            y = cy + echelle * (nya + (y3 - nya) * gi) + random.gauss(0, agit * 1.5) + (balance if self.carte else 0)
            px, py = self.positions[i]
            self.positions[i] = (x, y)

            trait = role in ("oeil", "pupille", "levre_haut", "levre_bas", "sourcil")
            base = 1.0 if trait else 0.42 if role == "cheveux" else 0.8
            if lum_image is not None:  # luminosité d'origine : les traits du visage ressortent
                base = 0.35 + 0.9 * lum_image
            scintille = 0.7 + 0.3 * math.sin(t * 6 + phase * 7)
            lum = base * scintille * (0.25 + 0.75 * profondeur) * self.eclat
            if i in self.chauds:
                couleur = melange(FOND, CHAUD, lum * (0.6 + 0.4 * math.sin(t * 3 + phase)))
            else:
                couleur = melange(FOND, melange(self.coeur, "#ffffff", 0.35 * profondeur * trait), lum)
            r = (2.3 if role == "pupille" else 1.5 if trait else 0.8 + 0.9 * profondeur) * (0.85 + 0.3 * self.eclat)
            if self.carte and self.flou < 0.3 and not role.startswith("levre"):
                r *= 0.6        # sur le visage précis, la nuée n'est plus qu'un scintillement léger
                couleur = melange(FOND, couleur, 0.75)
            c.coords(self.points[i], x - r, y - r, x + r, y + r)
            c.itemconfigure(self.points[i], fill=couleur)
            if i in self.trainees:                       # flou de mouvement pendant les transitions
                vitesse = math.hypot(x - px, y - py)
                if vitesse > 2.5:
                    c.coords(self.trainees[i], px, py, x, y)
                    c.itemconfigure(self.trainees[i], fill=melange(FOND, self.coeur, min(0.55, vitesse / 25)))
                else:
                    c.coords(self.trainees[i], 0, 0, 0, 0)

        # Balayage horizontal façon projection holographique
        y = (t * 60) % s
        c.coords(self.balayage, cx - s * 0.42, y, cx + s * 0.42, y)
        c.itemconfigure(self.balayage, fill=melange(FOND, self.halo, 0.8))

        # Légende qui s'écrit lettre par lettre
        if self.legende != self._legende_cible:
            self._legende_cible, self._lettres = self.legende, 0
        self._lettres = min(len(self.legende), self._lettres + 2)
        curseur = "▌" if self._lettres < len(self.legende) or int(t * 2) % 2 else " "
        c.itemconfigure(self.texte, text=self.legende[:self._lettres].upper() + curseur,
                        fill=melange(self.coeur, "#ffffff", 0.2))

        self.t += 0.04
        self.root.after(40, self._animer)

    def lancer(self):
        self.root.mainloop()
