"""Représentation holographique animée en Tkinter pur (aucune dépendance, ~1 % CPU).

États : veille, ecoute, reflexion, parole, execution.
"""
import math
import subprocess
import sys
import tkinter as tk

COULEURS = {  # (cœur, anneaux) — les transitions entre états sont fondues
    "veille": ("#1aa7c4", "#0b5566"),
    "ecoute": ("#3ff0ff", "#18b4d4"),
    "reflexion": ("#c3a6ff", "#7c4dff"),
    "parole": ("#9ffcff", "#2fe4ff"),
    "execution": ("#ffc46b", "#ff8f00"),
}
FOND = "#010409"
VITESSE = {"veille": 0.3, "ecoute": 1, "reflexion": 2.5, "parole": 1.2, "execution": 4}

# Constellation d'Orion (Bételgeuse, Bellatrix, ceinture, Saïph, Rigel, Meïssa) en coordonnées normalisées
ETOILES = [(-0.55, -0.75), (0.45, -0.65), (-0.18, 0.0), (0.0, 0.05), (0.18, 0.1), (-0.45, 0.8), (0.55, 0.7),
           (0.0, -0.95)]
LIENS = [(0, 1), (0, 2), (1, 4), (2, 3), (3, 4), (2, 5), (4, 6), (0, 7), (1, 7)]


def _rvb(c):
    return [int(c[i:i + 2], 16) for i in (1, 3, 5)]


def melange(a, b, k):
    """Couleur entre a et b (k=0 → a, k=1 → b). Tk n'a pas de transparence : on simule halos et fondus."""
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * k) for x, y in zip(_rvb(a), _rvb(b)))


class Hologramme:
    def __init__(self, cfg):
        h = cfg["hologramme"]
        self.taille = h["taille"]
        self.etat, self.legende, self.t, self.phase = "veille", cfg["nom"], 0.0, 0.0
        self.coeur, self.anneau = COULEURS["veille"]
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
        self.toile = tk.Canvas(self.root, width=self.taille, height=self.taille + 40, bg=FOND,
                               highlightthickness=0)
        self.toile.pack()
        self.toile.bind("<ButtonPress-1>", self._debut_glisser)
        self.toile.bind("<B1-Motion>", self._glisser)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        # Utilisateur lambda : tout est à la souris (clic droit = menu, double-clic = panneau)
        self.sur_silence = lambda: None
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Se taire", command=lambda: self.sur_silence())
        menu.add_command(label="Panneau (voix, famille, savoir, réglages)", command=self.ouvrir_panneau)
        menu.add_separator()
        menu.add_command(label=f"Quitter {cfg['nom']}", command=self.root.destroy)
        self.toile.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        self.toile.bind("<Button-2>", lambda e: menu.tk_popup(e.x_root, e.y_root))  # macOS
        self.toile.bind("<Double-Button-1>", lambda e: self.ouvrir_panneau())
        self._animer()

    def changer(self, etat, legende=None):
        """Appelable depuis n'importe quel thread."""
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
        """~25 images/s, environ 200 formes simples par image : fluide même sur un vieux PC."""
        c, s, t, etat = self.toile, self.taille, self.t, self.etat
        cible_coeur, cible_anneau = COULEURS[etat]
        self.coeur = melange(self.coeur, cible_coeur, 0.15)
        self.anneau = melange(self.anneau, cible_anneau, 0.15)
        coeur, anneau = self.coeur, self.anneau
        cx = cy = s / 2
        v = VITESSE[etat]
        self.phase += 0.04 * v
        ph = self.phase
        scintille = 0.85 + 0.15 * math.sin(t * 13) * math.sin(t * 7.3)  # léger tremblement holographique
        c.delete("all")

        # Constellation d'Orion en perspective, qui tourne lentement en arrière-plan
        rot = t * 0.15
        pts = []
        for x, y in ETOILES:
            xr = x * math.cos(rot)
            pts.append((cx + xr * s * 0.36, cy + y * s * 0.36 + x * math.sin(rot) * s * 0.04))
        trait = melange(FOND, anneau, 0.35 * scintille)
        for i, j in LIENS:
            c.create_line(*pts[i], *pts[j], fill=trait, dash=(1, 4))
        for k, (x, y) in enumerate(pts):
            r = 1.5 + 1.2 * abs(math.sin(t * 2 + k))
            c.create_oval(x - r, y - r, x + r, y + r, fill=melange(FOND, coeur, 0.6), outline="")

        # Couronne de graduations avec un balayage lumineux
        R = s * 0.46
        balayage = (ph * 40) % 360
        for a in range(0, 360, 6):
            d = min(abs(a - balayage), 360 - abs(a - balayage))
            k = max(0.18, 1 - d / 70)
            ang = math.radians(a)
            l = 6 if a % 30 else 11
            c.create_line(cx + R * math.cos(ang), cy + R * math.sin(ang),
                          cx + (R - l) * math.cos(ang), cy + (R - l) * math.sin(ang),
                          fill=melange(FOND, anneau, k * scintille))

        # Anneaux en arcs contrarotatifs, doublés d'un halo
        for i, r in enumerate((0.40, 0.33, 0.26)):
            rayon = s * r
            depart = (ph * (40 + 25 * i) * (-1) ** i) % 360
            for k in range(3):
                for largeur, teinte in ((6, melange(FOND, anneau, 0.25)), (2, anneau)):
                    c.create_arc(cx - rayon, cy - rayon, cx + rayon, cy + rayon, start=depart + k * 120,
                                 extent=70 - 15 * i, style="arc", outline=teinte, width=largeur)

        # Particules en orbite avec traînée
        for k in range(14):
            for trace in range(3):
                a = ph * (0.9 + k % 3 * 0.25) + k * 0.45 - trace * 0.08
                r = s * (0.20 + 0.025 * (k % 4))
                x, y = cx + r * math.cos(a), cy + r * math.sin(a) * 0.92
                taille = 2.2 - trace * 0.6
                c.create_oval(x - taille, y - taille, x + taille, y + taille, outline="",
                              fill=melange(FOND, coeur, 0.9 - trace * 0.3))

        # Effet propre à chaque état
        if etat == "ecoute":  # ondes qui convergent vers le cœur
            for k in range(3):
                p = 1 - ((t * 0.7 + k / 3) % 1)
                r = s * (0.14 + 0.3 * p)
                c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=melange(FOND, coeur, 1 - p))
        elif etat == "parole":  # spectre radial qui suit la voix
            for k in range(48):
                ang = 2 * math.pi * k / 48
                amp = s * 0.07 * (0.25 + 0.75 * abs(math.sin(t * 9 + k * 0.7) * math.sin(t * 4.1 + k)))
                r0 = s * 0.15
                c.create_line(cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
                              cx + (r0 + amp) * math.cos(ang), cy + (r0 + amp) * math.sin(ang),
                              fill=melange(anneau, coeur, amp / (s * 0.07)), width=3)
        elif etat == "reflexion":  # réseau de neurones qui s'allume
            noeuds = [(cx + s * 0.17 * math.cos(ph * 0.8 + k * 1.26), cy + s * 0.17 * math.sin(ph * 1.1 + k * 1.26))
                      for k in range(5)]
            for i in range(5):
                for j in range(i + 1, 5):
                    c.create_line(*noeuds[i], *noeuds[j], fill=melange(FOND, coeur, 0.4))
        elif etat == "execution":  # hexagone d'engrenage
            for k in range(6):
                a1, a2 = math.radians(k * 60 + ph * 60), math.radians(k * 60 + 40 + ph * 60)
                r = s * 0.17
                c.create_line(cx + r * math.cos(a1), cy + r * math.sin(a1), cx + r * math.cos(a2),
                              cy + r * math.sin(a2), fill=coeur, width=4)

        # Cœur lumineux : halo en dégradé (cercles concentriques de plus en plus sombres)
        pouls = 1 + 0.07 * math.sin(t * (7 if etat == "parole" else 2))
        rc = s * 0.085 * pouls
        for k in range(5, 0, -1):
            r = rc * (1 + k * 0.22)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="", fill=melange(FOND, coeur, 0.12 * (6 - k)))
        c.create_oval(cx - rc, cy - rc, cx + rc, cy + rc, fill=coeur, outline=melange(coeur, "#ffffff", 0.6))
        c.create_oval(cx - rc * 0.45, cy - rc * 0.45, cx + rc * 0.45, cy + rc * 0.45,
                      fill=melange(coeur, "#ffffff", 0.7), outline="")

        # Balayage horizontal façon projection holographique
        y = (t * 70) % s
        c.create_line(cx - s * 0.42, y, cx + s * 0.42, y, fill=melange(FOND, anneau, 0.5), dash=(2, 6))

        # Légende qui s'écrit lettre par lettre
        if self.legende != self._legende_cible:
            self._legende_cible, self._lettres = self.legende, 0
        self._lettres = min(len(self.legende), self._lettres + 2)
        curseur = "▌" if self._lettres < len(self.legende) or int(t * 2) % 2 else " "
        c.create_text(cx, s + 18, text=self.legende[:self._lettres].upper() + curseur,
                      fill=melange(coeur, "#ffffff", 0.2), font=("Consolas", 11))

        self.t += 0.04
        self.root.after(40, self._animer)

    def lancer(self):
        self.root.mainloop()
