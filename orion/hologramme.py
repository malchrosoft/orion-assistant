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
import re
import subprocess
import sys
import time
import tkinter as tk

COULEURS = {  # (points, halo) — les transitions sont fondues
    "veille": ("#d6dbe1", "#2c3036"),     # au repos : gris perle
    "ecoute": ("#4ff4ff", "#0c3f9a"),     # écoute : cyan sur halo bleu
    "reflexion": ("#9fc2ff", "#1d2f73"),  # réfléchit : bleu pâle, entre écoute et action
    "parole": ("#ffc93c", "#9e1414"),     # parle : doré, qui ondule vers le rouge (voir ROUGE_PAROLE)
    "execution": ("#b77bff", "#40148c"),  # agit (téléchargement, installation…) : violet
}
ROUGE_PAROLE = "#ff5a3c"
POLICE_LECTURE = ("Helvetica", 11)
LIGNES_LECTURE = 4
CARACTERES_PAR_SECONDE = 14.5  # débit moyen des voix françaises (Piper et système), pour suivre la lecture
DELAI_VOIX = 0.6               # temps de synthèse avant que la voix ne démarre
LARGEUR_CAR = {11: 8.2, 9: 6.8}  # largeur approchée d'un caractère Consolas (pixels), par taille de police
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
        self.root = tk.Tk()
        # la fenêtre (hologramme + textes en dessous) doit tenir entière à l'écran, même petit
        s = self.taille = min(s, self.root.winfo_screenheight() - 170, self.root.winfo_screenwidth() - 40)
        self.etat, self.legende, self.t = "veille", cfg["nom"], 0.0
        self.coeur, self.halo = COULEURS["veille"]
        self.rassemble, self.eclat, self.flou = RASSEMBLEMENT["veille"], ECLAT["veille"], 0.0
        self._legende_cible, self._lettres, self._t_legende = "", 0, 0.0
        self.root.title(cfg["nom"])
        self.root.configure(bg=FOND)
        self.root.attributes("-topmost", h["toujours_devant"])
        if h["transparent"]:
            try:  # Windows : le fond devient invisible, seul l'hologramme flotte
                self.root.attributes("-transparentcolor", FOND)
                self.root.overrideredirect(True)
            except tk.TclError:
                pass
        self.toile = c = tk.Canvas(self.root, width=s, height=s + 70, bg=FOND, highlightthickness=0)
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
        # Compte à rebours : arc lumineux autour du visage et grands chiffres (cachés hors décompte)
        self.decompte = None   # (fin monotonic, total) ; la sonnerie fait clignoter « 00:00 »
        self.sonnerie, self.acquitte = False, False
        self.arcs_decompte = [c.create_arc(0, 0, 0, 0, start=90, extent=0, style="arc", outline=FOND, width=w,
                                           state="hidden") for w in (16, 7, 2)]
        # Rédaction d'un document : feuille lumineuse dont les lignes s'écrivent, étiquette du format
        self.redaction_format, self._t_redaction = None, 0.0
        self.feuille = c.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline=FOND, width=2, state="hidden")
        self.coin = c.create_line(0, 0, 0, 0, fill=FOND, width=2, state="hidden")
        self.lignes_feuille = [c.create_line(0, 0, 0, 0, fill=FOND, width=2, state="hidden") for _ in range(7)]
        self.plume = c.create_oval(0, 0, 0, 0, fill=FOND, outline="", state="hidden")
        self.etiquette_feuille = c.create_text(0, 0, text="", fill=FOND, font=("Helvetica", 10, "bold"), state="hidden")
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
        # Dernière action menée : une ligne discrète en haut (défile si elle est trop longue)
        self.action_texte, self._t_action = "", 0.0
        # Personne reconnue pendant la conversation : en haut à gauche
        self.personne_texte, self.couleur_personne = "", None
        self.personne = c.create_text(8, 10, text="", anchor="w", fill="#ffffff", font=("Consolas", 9))
        self.action = c.create_text(s / 2, 26, text="", fill="#ffffff", font=("Consolas", 9))
        self.chiffres_decompte = [c.create_text(s / 2, s * 0.86, text="", fill=FOND, state="hidden",
                                                font=("Helvetica", 44, "bold")) for _ in range(2)]
        self.texte = c.create_text(s / 2, s + 18, text="", fill="#ffffff", font=("Consolas", 11))
        # Tâche en cours : texte en petit et barre de progression (masqués quand rien n'est en cours)
        self.statut_texte, self.statut_fraction = "", None
        self.statut = c.create_text(s / 2, s + 40, text="", fill="#ffffff", font=("Consolas", 9))
        # Lecture en cours : texte sur 4 lignes en petit, qui remonte au fil de la voix (5 lignes pour le fondu)
        self.lecture, self._t_lecture, self._lignes = "", 0.0, []
        self.lignes_lecture = [c.create_text(s / 2, 0, text="", fill=FOND, font=POLICE_LECTURE, state="hidden")
                               for _ in range(LIGNES_LECTURE + 1)]
        self.barre_fond = c.create_rectangle(s * 0.2, s + 54, s * 0.8, s + 58, outline="", fill=FOND, state="hidden")
        self.barre = c.create_rectangle(s * 0.2, s + 54, s * 0.2, s + 58, outline="", fill=FOND, state="hidden")

        c.bind("<ButtonPress-1>", self._debut_glisser)
        c.bind("<B1-Motion>", self._glisser)
        c.bind("<ButtonRelease-1>", self._relache)
        self.sur_clic = lambda: None  # un clic simple : Orion écoute (branché par la boucle vocale)
        self.sur_deplacement = lambda: None  # fenêtre déplacée : Orion peut faire une remarque
        self._clic_prevu = None
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
        c.bind("<Double-Button-1>", self._double_clic)
        self.root.after(50, self._garder_visible)  # au chargement, une fois la taille réelle connue
        self._animer()

    def _garder_visible(self):
        """Ramène la fenêtre entièrement dans l'écran (au chargement, et après l'avoir déplacée)."""
        r = self.root
        r.update_idletasks()
        l, h = r.winfo_width(), r.winfo_height()
        sl, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        x = min(max(0, r.winfo_x()), max(0, sl - l))
        y = min(max(25, r.winfo_y()), max(0, sh - h - 60))  # barre de menus en haut, Dock / barre des tâches en bas
        if (x, y) != (r.winfo_x(), r.winfo_y()):
            r.geometry(f"+{x}+{y}")

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

    def progression(self, texte, fraction=None):
        """Tâche en cours (appelable depuis n'importe quel thread) : texte en petit, barre si la fraction (0 à 1)
        est connue. progression("") efface tout."""
        self.statut_texte, self.statut_fraction = texte, fraction

    def redaction(self, format_):
        """Format en cours de rédaction (« PDF », « DOCX »…) ou None. Appelable depuis n'importe quel thread."""
        self.redaction_format, self._t_redaction = format_, self.t

    def interlocuteur(self, nom, couleur=None):
        """Personne reconnue (vide : personne) et sa couleur (#rrggbb) : elle teinte le halo et son nom.
        Appelable depuis n'importe quel thread."""
        self.personne_texte = f"● {nom}" if nom else ""
        self.couleur_personne = couleur if nom and couleur and re.fullmatch(r"#[0-9a-fA-F]{6}", couleur) else None

    def derniere_action(self, texte):
        """Appelable depuis n'importe quel thread."""
        self.action_texte, self._t_action = texte, self.t

    def changer(self, etat, legende=None):
        """Appelable depuis n'importe quel thread."""
        if etat != self.etat:
            self.flou = 1.0  # brouillage de transition
        self.etat = etat
        if legende is not None:
            self.legende = legende
        if etat == "parole" and legende:  # nouvelle lecture : le texte défile au rythme estimé de la voix
            self.lecture, self._t_lecture, self._lignes = legende, time.monotonic(), []
        elif etat != "parole":
            self.lecture = ""

    def _afficher_feuille(self):
        """Feuille qui flotte à droite du visage : ses lignes s'écrivent l'une après l'autre, une plume brille
        au bout de la ligne en cours, puis tout recommence tant que la rédaction dure."""
        c, s = self.toile, self.taille
        items = [self.feuille, self.coin, self.plume, self.etiquette_feuille] + self.lignes_feuille
        if not self.redaction_format:
            for item in items:
                c.itemconfigure(item, state="hidden")
            return
        age = self.t - self._t_redaction
        apparition = min(1.0, age / 0.4)
        l, h = s * 0.2, s * 0.26
        x0, y0 = s * 0.76 - l / 2, s * 0.36 - h / 2 + 4 * math.sin(self.t * 2)  # flotte doucement
        pli = l * 0.22
        teinte = melange(FOND, melange(self.coeur, "#ffffff", 0.35), 0.9 * apparition)
        c.coords(self.feuille, x0, y0, x0 + l - pli, y0, x0 + l, y0 + pli, x0 + l, y0 + h, x0, y0 + h)
        c.itemconfigure(self.feuille, outline=teinte, fill=melange(FOND, self.coeur, 0.12 * apparition), state="normal")
        c.coords(self.coin, x0 + l - pli, y0, x0 + l - pli, y0 + pli, x0 + l, y0 + pli)
        c.itemconfigure(self.coin, fill=teinte, state="normal")
        progres = (age * 2.2) % (len(self.lignes_feuille) + 1.5)  # lignes écrites, en boucle
        plume = None
        for i, item in enumerate(self.lignes_feuille):
            y = y0 + h * (0.24 + 0.1 * i)
            longueur = (l - 18) * (0.55 if i == len(self.lignes_feuille) - 1 else 0.9 - 0.1 * (i % 3 == 1))
            fait = max(0.0, min(1.0, progres - i))
            if fait <= 0:
                c.itemconfigure(item, state="hidden")
                continue
            xf = x0 + 9 + longueur * fait
            c.coords(item, x0 + 9, y, xf, y)
            c.itemconfigure(item, fill=melange(FOND, self.coeur, 0.75 * apparition), state="normal")
            if fait < 1:
                plume = (xf, y)
        if plume:
            r = 3 + 1.5 * math.sin(self.t * 12)
            c.coords(self.plume, plume[0] - r, plume[1] - r, plume[0] + r, plume[1] + r)
            c.itemconfigure(self.plume, fill=melange(self.coeur, "#ffffff", 0.7), state="normal")
        else:
            c.itemconfigure(self.plume, state="hidden")
        c.coords(self.etiquette_feuille, x0 + l / 2, y0 + h + 12)
        c.itemconfigure(self.etiquette_feuille, text=self.redaction_format, fill=teinte, state="normal")

    def _afficher_decompte(self, cx, cy, echelle):
        """Arc qui se vide autour du visage, chiffres géants lumineux ; dernières secondes en rouge
        qui palpitent, puis « 00:00 » qui clignote pendant la sonnerie."""
        from .minuteur import affichage
        c, t = self.toile, self.t
        if not self.decompte and not self.sonnerie:
            for item in self.arcs_decompte + self.chiffres_decompte:
                c.itemconfigure(item, state="hidden")
            return
        restant, total = ((self.decompte[0] - time.monotonic(), self.decompte[1]) if self.decompte else (0, 1))
        part = max(0.0, min(1.0, restant / total))
        fin = restant <= 10
        teinte = melange("#4ff4ff", "#ffb13c", 1 - part) if not fin else melange("#ff8a3c", "#ff2d2d", 1 - restant / 10)
        palpite = 0.5 + 0.5 * math.sin(t * (9 if fin else 3))
        if self.sonnerie:
            teinte, palpite = "#ff3b3b", 1.0 if int(t * 3) % 2 else 0.15
        r = echelle * 1.18
        for k, item in enumerate(self.arcs_decompte):  # halo large et flou, trait, filet clair
            force = (0.25, 0.75, 1.0)[k] * (0.55 + 0.45 * palpite)
            c.coords(item, cx - r, cy - r, cx + r, cy + r)
            c.itemconfigure(item, extent=-359.9 * (part if not self.sonnerie else 1), state="normal",
                            outline=melange(FOND, melange(teinte, "#ffffff", 0.4 * k / 2), force))
        taille = int(44 * (1 + (0.12 * palpite if fin or self.sonnerie else 0)))
        texte = affichage(restant)
        for k, item in enumerate(self.chiffres_decompte):  # lueur décalée derrière, chiffres nets devant
            c.coords(item, self.taille / 2 + (2 if not k else 0), self.taille * 0.86 + (2 if not k else 0))
            c.itemconfigure(item, text=texte, state="normal", font=("Helvetica", taille, "bold"),
                            fill=melange(FOND, teinte, 0.45 if not k else 0.6 + 0.4 * palpite))

    def _couper(self, texte):
        """Lignes qui tiennent dans la largeur de la fenêtre (mesurées avec la vraie police si possible)."""
        largeur = self.taille * 0.86
        try:
            import tkinter.font as tkfont
            mesure = tkfont.Font(font=POLICE_LECTURE).measure
        except Exception:
            mesure = lambda m: len(m) * 6.5  # noqa: E731 — sans fenêtre (tests)
        lignes, ligne = [], ""
        for mot in texte.split():
            essai = f"{ligne} {mot}".strip()
            if ligne and mesure(essai) > largeur:
                lignes.append(ligne)
                ligne = mot
            else:
                ligne = essai
        return lignes + ([ligne] if ligne else [])

    def _afficher_lecture(self):
        """4 lignes centrées en bas : la ligne lue en clair, les suivantes plus douces ; le bloc remonte en
        continu au rythme estimé de la voix (caractères par seconde), la ligne lue restant en 2e position."""
        c, s, items = self.toile, self.taille, self.lignes_lecture
        if not self.lecture:
            for item in items:
                c.itemconfigure(item, state="hidden")
            c.itemconfigure(self.statut, state="normal")
            return
        c.itemconfigure(self.statut, state="hidden")
        if not self._lignes:
            self._lignes = self._couper(self.lecture)
        lignes = self._lignes
        lus = max(0.0, (time.monotonic() - self._t_lecture - DELAI_VOIX) * CARACTERES_PAR_SECONDE)
        position, reste = 0.0, lus  # ligne en cours de lecture (avec la fraction déjà lue)
        for i, ligne in enumerate(lignes):
            if reste <= len(ligne) + 1:
                position = i + reste / (len(ligne) + 1)
                break
            reste -= len(ligne) + 1
        else:
            position = len(lignes) - 1
        haut = max(0.0, min(position - 1, len(lignes) - LIGNES_LECTURE)) if len(lignes) > LIGNES_LECTURE else 0.0
        premier, decalage = int(haut), haut - int(haut)
        y0, pas = s + 6, 15
        for k, item in enumerate(items):
            i = premier + k
            y = y0 + (k - decalage) * pas
            if i >= len(lignes) or y < y0 - 4 or y > y0 + (LIGNES_LECTURE - 0.6) * pas:
                c.itemconfigure(item, state="hidden")
                continue
            bord = min(1.0, (y - (y0 - 4)) / 10, (y0 + (LIGNES_LECTURE - 0.6) * pas - y) / 10)  # fondu haut/bas
            proche = max(0.0, 1 - abs(i + 0.5 - position) / 1.5)  # la ligne lue ressort
            teinte = melange(FOND, melange(self.coeur, "#ffffff", 0.3), (0.35 + 0.65 * proche) * max(0.0, bord))
            c.coords(item, s / 2, y)
            c.itemconfigure(item, text=lignes[i], fill=teinte, state="normal")

    def _defiler(self, texte, taille_police, depart=0.0):
        """Texte trop long pour la fenêtre : il défile en boucle, comme un bandeau (pause au début)."""
        place = int(self.taille * 0.92 / LARGEUR_CAR[taille_police])
        if len(texte) <= place:
            return texte
        boucle = texte + "   •   "
        pas = max(0, int((self.t - depart - 1.5) * 6)) % len(boucle)
        return (boucle * 2)[pas:pas + place]

    @staticmethod
    def ouvrir_panneau():
        cmd = [sys.executable, "panneau"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "orion", "panneau"]
        subprocess.Popen(cmd)

    # Souris : glisser déplace la fenêtre, un clic fait écouter Orion, un double-clic ouvre le panneau
    def _debut_glisser(self, e):
        self._dx, self._dy, self._deplace = e.x, e.y, False

    def _glisser(self, e):
        if abs(e.x - self._dx) + abs(e.y - self._dy) > 4:
            self._deplace = True
            self.flou = max(self.flou, 0.45)  # la nuée s'agite, comme secouée
            self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _relache(self, e):
        if not getattr(self, "_deplace", False):  # clic simple, confirmé s'il n'est pas suivi d'un second clic
            self._clic_prevu = self.root.after(260, self._clic_simple)
        else:
            self._garder_visible()
            self.sur_deplacement()

    def _clic_simple(self):
        self._clic_prevu = None
        if self.sonnerie:  # un clic pendant la sonnerie l'arrête (Orion n'a pas besoin de l'annoncer)
            self.sonnerie, self.acquitte = False, True
            return
        self.sur_clic()

    def _double_clic(self, e):
        if self._clic_prevu:
            self.root.after_cancel(self._clic_prevu)
            self._clic_prevu = None
        self.ouvrir_panneau()

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
        if self.couleur_personne:  # la couleur de la personne reconnue baigne le halo ; l'état reste lisible
            cible_halo = melange(cible_halo, melange(FOND, self.couleur_personne, 0.55), 0.7)
        if etat == "parole":  # dégradé doré ↔ rouge qui respire pendant qu'Orion parle
            cible_point = melange(cible_point, ROUGE_PAROLE, 0.5 + 0.5 * math.sin(t * 2.2))
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

        self._afficher_decompte(cx, cy, echelle)
        self._afficher_feuille()

        # Balayage horizontal façon projection holographique
        y = (t * 60) % s
        c.coords(self.balayage, cx - s * 0.42, y, cx + s * 0.42, y)
        c.itemconfigure(self.balayage, fill=melange(FOND, self.halo, 0.8))

        # Légende qui s'écrit lettre par lettre
        if self.legende != self._legende_cible:
            self._legende_cible, self._lettres, self._t_legende = self.legende, 0, t
        self._lettres = min(len(self.legende), self._lettres + 2)
        curseur = "▌" if self._lettres < len(self.legende) or int(t * 2) % 2 else " "
        texte = self.legende[:self._lettres].upper() + curseur
        if self._lettres >= len(self.legende):  # écrit en entier : défile s'il dépasse la fenêtre
            texte = self._defiler(self.legende.upper(), 11, self._t_legende + len(self.legende) * 0.02)
        c.itemconfigure(self.texte, text="" if self.lecture else texte, fill=melange(self.coeur, "#ffffff", 0.2))
        self._afficher_lecture()

        c.itemconfigure(self.personne, text=self.personne_texte,
                        fill=self.couleur_personne or melange(FOND, self.coeur, 0.8))
        c.itemconfigure(self.action, text=self._defiler(self.action_texte, 9, self._t_action),
                        fill=melange(FOND, COULEURS["veille"][0], 0.55))

        # Tâche en cours
        c.itemconfigure(self.statut, text=self._defiler(self.statut_texte, 9),
                        fill=melange(FOND, self.coeur, 0.85))
        if self.statut_fraction is None:
            c.itemconfigure(self.barre_fond, state="hidden")
            c.itemconfigure(self.barre, state="hidden")
        else:
            x0, x1 = s * 0.2, s * 0.2 + s * 0.6 * max(0.0, min(1.0, self.statut_fraction))
            c.coords(self.barre, x0, s + 54, x1, s + 58)
            c.itemconfigure(self.barre_fond, state="normal", fill=melange(FOND, self.halo, 0.9))
            c.itemconfigure(self.barre, state="normal", fill=melange(self.coeur, "#ffffff", 0.2))

        self.t += 0.04
        self.root.after(40, self._animer)

    def lancer(self):
        self.root.mainloop()
