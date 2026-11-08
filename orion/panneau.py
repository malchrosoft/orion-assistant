# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Interface graphique optionnelle (Tkinter, incluse avec Python) : discuter, gérer le savoir,
les voix de la famille et les réglages, sans toucher aux fichiers JSON."""
import json
import locale
import os
import platform
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import espace, knowledge, langues, web
from .bouche import LANGUES, Bouche, lister_voix
from .persona import GENRES, salutation
from .actions import Actions
from .brain import Cerveau
from .config import charger, sauver
from .voix import PROFILS

# Thème futuriste épuré : noir bleuté, accents cyan, aucune image (léger)
FOND, SURFACE, TEXTE, ACCENT, DISCRET = "#05090d", "#0c141b", "#cfe9f2", "#29e0ff", "#5b7683"


def theme(root):
    root.configure(bg=FOND)
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=FOND, foreground=TEXTE, fieldbackground=SURFACE, bordercolor="#14313d",
                 lightcolor=FOND, darkcolor=FOND, font=("Segoe UI", 10))
    st.configure("TNotebook", background=FOND, borderwidth=0)
    st.configure("TNotebook.Tab", background=FOND, foreground=DISCRET, padding=(14, 6), borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", ACCENT)])
    st.configure("TButton", background=SURFACE, foreground=ACCENT, borderwidth=1, focusthickness=0,
                 padding=(10, 4))
    st.map("TButton", background=[("active", "#123040")])
    st.configure("TLabelframe", background=FOND, bordercolor="#14313d")
    st.configure("TLabelframe.Label", background=FOND, foreground=ACCENT)
    st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXTE, rowheight=24)
    st.configure("Treeview.Heading", background=FOND, foreground=ACCENT)
    st.map("Treeview", background=[("selected", "#123040")])
    st.configure("TCheckbutton", background=FOND, foreground=TEXTE)
    st.configure("TRadiobutton", background=FOND, foreground=TEXTE)
    st.configure("TEntry", foreground=TEXTE, insertcolor=ACCENT)
    root.option_add("*Listbox.background", SURFACE)
    root.option_add("*Listbox.foreground", TEXTE)
    root.option_add("*Listbox.selectBackground", "#123040")
    root.option_add("*Listbox.borderWidth", 0)


ETOILES = {3: "★★★", 2: "★★", 1: "★", 0: "⚠ non vérifiée"}
DOMAINES = ["maths", "mecanique", "electronique", "batiment", "web"]


class Panneau:
    def __init__(self):
        self.cfg = charger()
        self.cerveau = Cerveau(self.cfg, Actions(self.cfg))
        self.root = tk.Tk()
        self.root.title(f"{self.cfg['nom']} — panneau")
        # entièrement visible au chargement, même sur un petit écran : taille bornée et fenêtre centrée
        l, h = min(780, self.root.winfo_screenwidth() - 40), min(560, self.root.winfo_screenheight() - 100)
        self.root.geometry(f"{l}x{h}+{(self.root.winfo_screenwidth() - l) // 2}"
                           f"+{max(0, (self.root.winfo_screenheight() - h) // 2 - 20)}")
        theme(self.root)
        from .hologramme import icone
        icone(self.root)
        onglets = ttk.Notebook(self.root)
        onglets.pack(fill="both", expand=True)
        for titre, construire in (("Discussion", self._discussion), ("Savoir", self._savoir),
                                  ("Voix", self._voix), ("Langues", self._langues), ("Famille", self._famille), ("Réglages", self._reglages)):
            if titre == "Discussion":  # le journal de discussion a déjà sa propre zone défilante
                cadre = ttk.Frame(onglets, padding=8)
                onglets.add(cadre, text=titre)
            else:
                cadre = self._onglet_defilant(onglets, titre)
            construire(cadre)
        bas = ttk.Frame(self.root)
        bas.pack(pady=6)
        lancer = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "orion"]
        ttk.Button(bas, text=f"▶ Lancer {self.cfg['nom']} (voix + hologramme)",
                   command=lambda: subprocess.Popen(lancer)).pack(side="left", padx=4)
        ttk.Button(bas, text="Crédits (PDF)", command=self._credits_pdf).pack(side="left", padx=4)
        ttk.Button(bas, text="Installer ce qui manque…", command=lambda: self._installer_composants(
            self._manquants())).pack(side="left", padx=4)
        self.etat_installation = tk.StringVar()
        ttk.Label(self.root, textvariable=self.etat_installation, foreground=ACCENT).pack()

    def _onglet_defilant(self, onglets, titre):
        """Onglet avec barre de défilement verticale et molette (Windows, macOS, Linux)."""
        conteneur = ttk.Frame(onglets)
        onglets.add(conteneur, text=titre)
        toile = tk.Canvas(conteneur, bg=FOND, highlightthickness=0)
        barre = ttk.Scrollbar(conteneur, orient="vertical", command=toile.yview)
        interieur = ttk.Frame(toile, padding=8)
        fenetre = toile.create_window((0, 0), window=interieur, anchor="nw")
        interieur.bind("<Configure>", lambda e: toile.configure(scrollregion=toile.bbox("all")))
        toile.bind("<Configure>", lambda e: toile.itemconfigure(fenetre, width=e.width))
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")

        toile.configure(yscrollincrement=40)  # pas de défilement confortable (en pixels)

        def peut_defiler():
            return toile.winfo_ismapped() and interieur.winfo_height() > toile.winfo_height()

        def molette(e):
            if peut_defiler():
                if e.num in (4, 5):                      # Linux (X11) : boutons 4 et 5
                    pas = -1 if e.num == 4 else 1
                else:                                    # Windows (±120 par cran), macOS (petites valeurs)
                    pas = (-1 if e.delta > 0 else 1) * max(1, abs(e.delta) // 120)
                toile.yview_scroll(pas, "units")

        def pave_tactile(e):  # macOS, Tk 9 : défilement à deux doigts
            if peut_defiler():
                try:
                    _, dy = self.root.tk.splitlist(self.root.tk.call("tk::PreciseScrollDeltas", e.delta))
                    dy = float(dy)
                except tk.TclError:
                    return
                if abs(dy) >= 1:
                    toile.yview_scroll(int(-dy / 4) or (-1 if dy > 0 else 1), "units")
        # bind_all : la molette fonctionne même au-dessus des champs ; seul l'onglet visible défile
        for evt in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(evt, molette, add="+")
        try:
            self.root.bind_all("<TouchpadScroll>", pave_tactile, add="+")
        except tk.TclError:
            pass  # Tk 8.6 : pas d'événement dédié, le pavé tactile envoie <MouseWheel>
        return interieur

    # --- Discussion -------------------------------------------------------------
    def _discussion(self, f):
        self.journal = tk.Text(f, wrap="word", height=18, state="disabled", bg=SURFACE, fg=TEXTE,
                               insertbackground=ACCENT, relief="flat", padx=10, pady=8, font=("Segoe UI", 11))
        self.journal.pack(fill="both", expand=True)
        self.journal.tag_config("moi", foreground=ACCENT)
        self.journal.tag_config("lien", foreground="#7ffcff", underline=True)
        self.journal.tag_config("doute", foreground="#ffb74d")
        ligne = ttk.Frame(f)
        ligne.pack(fill="x", pady=4)
        self.saisie = ttk.Entry(ligne)
        self.saisie.pack(side="left", fill="x", expand=True)
        self.saisie.bind("<Return>", lambda e: self._envoyer())
        ttk.Button(ligne, text="Envoyer", command=self._envoyer).pack(side="left")

    def _ecrire(self, texte, *tags):
        self.journal.configure(state="normal")
        self.journal.insert("end", texte, tags)
        self.journal.configure(state="disabled")
        self.journal.see("end")

    def _envoyer(self):
        phrase = self.saisie.get().strip()
        if not phrase:
            return
        self.saisie.delete(0, "end")
        self._ecrire(f"\nToi : {phrase}\n", "moi")
        self.cerveau.derniere_fiche = None
        reponse, tache = self.cerveau.repondre(phrase, "invité")
        self._ecrire(f"{self.cfg['nom']} : {tache() if tache else reponse}\n")
        fiche = self.cerveau.derniere_fiche
        for s in (fiche or {}).get("sources", []):
            etat = f"consultée le {s['consulte']}" if s["consulte"] else "jamais vérifiée"
            role = "Source" if s["portee"] == "fiche" else "Pour aller plus loin"
            self._ecrire(f"   {role} {ETOILES[s['niveau']]} {s['titre']} ({etat}) ", "doute" if s["niveau"] == 0 else ())
            tag = f"url{id(s)}"
            self.journal.tag_config(tag)
            self.journal.tag_bind(tag, "<Button-1>", lambda e, u=s["url"]: webbrowser.open(u))
            self._ecrire("ouvrir\n", "lien", tag)

    # --- Savoir -------------------------------------------------------------------
    def _savoir(self, f):
        self.arbre = ttk.Treeview(f, columns=("domaine", "origine"), height=12)
        self.arbre.heading("#0", text="Fiche")
        self.arbre.heading("domaine", text="Domaine")
        self.arbre.heading("origine", text="Origine")
        self.arbre.column("#0", width=380)
        self.arbre.pack(fill="both", expand=True)
        self._rafraichir_savoir()

        cadre = ttk.LabelFrame(f, text="Apprendre depuis une URL (internet ou intranet) ou un fichier", padding=6)
        cadre.pack(fill="x", pady=6)
        self.url, self.sujet, self.domaine = tk.StringVar(), tk.StringVar(), tk.StringVar(value="web")
        for i, (lib, var) in enumerate((("Lien", self.url), ("Sujet (facultatif)", self.sujet))):
            ttk.Label(cadre, text=lib).grid(row=i, column=0, sticky="w")
            ttk.Entry(cadre, textvariable=var, width=60).grid(row=i, column=1, sticky="we")
        ttk.Combobox(cadre, textvariable=self.domaine, values=DOMAINES, width=12).grid(row=0, column=2)
        ttk.Button(cadre, text="Lire et retenir", command=self._apprendre).grid(row=1, column=2)
        ttk.Button(cadre, text="Fichier…", command=lambda: self.url.set(filedialog.askopenfilename(filetypes=[
            ("Documents", "*.epub *.pdf *.md *.markdown *.txt *.docx *.html *.htm"), ("Tous", "*")]) or self.url.get())
                   ).grid(row=0, column=3)
        ttk.Label(cadre, foreground=DISCRET, wraplength=620, justify="left", text=(
            "Document (EPUB, PDF, Word, Markdown, texte, HTML) : ajouté à la bibliothèque et découpé en passages "
            "indexés, cités avec leur page ou leur section. Page web : résumée en une fiche. Dans les deux cas, "
            "le contenu reste « non vérifié ».")).grid(row=2, column=0, columnspan=4, sticky="w")

        pub = ttk.LabelFrame(f, text="Publication de jw.org (EPUB)", padding=6)
        pub.pack(fill="x", pady=6)
        self.lien_pub = tk.StringVar()
        ttk.Label(pub, text="Lien de téléchargement").grid(row=0, column=0, sticky="w")
        ttk.Entry(pub, textvariable=self.lien_pub, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(pub, text="Télécharger", command=self._telecharger_publication).grid(row=0, column=2)
        ttk.Button(pub, text="Chercher sur jw.org…", command=lambda: webbrowser.open(
            "https://www.jw.org/fr/bibliotheque/")).grid(row=1, column=2)
        ttk.Label(pub, text="Sur la page de la publication, ouvrez la fenêtre de téléchargement et copiez le lien "
                            "de l'EPUB. Orion la retiendra : vous pourrez ensuite la demander par son titre.",
                  foreground=DISCRET, wraplength=520).grid(row=1, column=0, columnspan=2, sticky="w")

        boutons = ttk.Frame(f)
        boutons.pack(fill="x")
        ttk.Button(boutons, text="Oublier la fiche apprise", command=self._oublier).pack(side="left")
        ttk.Button(boutons, text="Vérifier les références en ligne", command=self._verifier).pack(side="left")

    def _telecharger_publication(self):
        from . import dossiers, publications
        d = publications.depuis_lien(self.lien_pub.get())
        pub = publications.chercher(*d) if d else None
        if not pub:
            messagebox.showwarning("Publication", "Ce lien ne correspond à aucune publication EPUB en français.")
            return
        if not messagebox.askyesno("Publication", f"Télécharger « {pub['titre']} » ({pub['octets'] / 1e6:.1f} Mo) ?"):
            return
        try:
            chemin = publications.telecharger(pub, dossiers.chemin(self.cfg))
        except OSError as e:
            messagebox.showerror("Publication", f"Le téléchargement n'a pas abouti : {e}")
            return
        publications.retenir(pub, *d)
        messagebox.showinfo("Publication", f"« {pub['titre']} » est enregistrée :\n{chemin}")

    def _rafraichir_savoir(self):
        self.arbre.delete(*self.arbre.get_children())
        appris = {f["titre"] for f in knowledge._lire(knowledge.APPRIS)}
        for fi in knowledge.toutes_les_fiches():
            self.arbre.insert("", "end", text=fi["titre"], values=(
                fi["domaine"], "⚠ internet, non vérifiée" if fi["titre"] in appris else "livrée"))
        from . import bibliotheque
        for nom, url, n in bibliotheque.liste():
            self.arbre.insert("", "end", text=nom, values=("bibliothèque", f"⚠ document ajouté ({n} passages)"))

    def _apprendre(self):
        from . import bibliotheque, dossiers
        url = self.url.get().strip().strip('"')
        if not url or not messagebox.askokcancel("Prudence", web.AVERTISSEMENT + "\n\nContinuer ?"):
            return
        document = bibliotheque.est_document(url) or ("://" not in url and Path(url).expanduser().is_file())

        def tache():
            try:
                if document:  # document entier : bibliothèque indexée (internet, intranet ou fichier local)
                    nom, n = bibliotheque.ajouter(url, dossiers.chemin(self.cfg) / "Bibliothèque")
                    message = (f"« {nom} » ajouté à la bibliothèque : {n} passage(s) indexé(s). "
                               "Orion le citera comme source non vérifiée.")
                else:
                    _, message = web.apprendre(url, self.sujet.get().strip() or None, self.domaine.get())
            except Exception as e:
                message = f"Impossible de lire ce document ou cette page : {e}"
            self.root.after(0, lambda: (messagebox.showinfo("Résultat", message), self._rafraichir_savoir()))
        threading.Thread(target=tache, daemon=True).start()

    def _oublier(self):
        for item in self.arbre.selection():
            knowledge.oublier(self.arbre.item(item, "text"))
        self._rafraichir_savoir()

    def _verifier(self):
        def tache():
            res = web.verifier_references()
            texte = "\n".join(f"{s} — {t}" for s, t, _ in res)
            self.root.after(0, lambda: messagebox.showinfo("Références", texte))
        threading.Thread(target=tache, daemon=True).start()

    # --- Voix d'Orion ---------------------------------------------------------------
    AIDE_VOIX = {
        "Windows": ("Paramètres › Heure et langue › Voix › Ajouter des voix, puis choisissez la langue.\n"
                    "Si la voix n'apparaît pas ici, ajoutez la langue dans « Langue et région » avec "
                    "l'option « Synthèse vocale », puis redémarrez Orion.",
                    [("Ouvrir les réglages Voix", "ms-settings:speech"),
                     ("Ouvrir Langue et région", "ms-settings:regionlanguage")]),
        "Darwin": ("Réglages Système › Accessibilité › Contenu énoncé › Voix du système › Gérer les voix…, "
                   "cochez une voix de la langue voulue (les voix « améliorées » sont plus naturelles).",
                   [("Ouvrir Accessibilité", "x-apple.systempreferences:com.apple.preference.universalaccess")]),
        "Linux": ("Installez eSpeak NG (sudo apt install espeak-ng) et, pour une voix plus douce, "
                  "les voix MBROLA de la langue (paquets mbrola-fr1, mbrola-en1…).", []),
    }

    def _voix(self, f):
        systeme = platform.system()
        langue_sys = (locale.getlocale()[0] or "fr")[:2].lower()
        ttk.Label(f, text=f"Système : {systeme} — langue de l'ordinateur : "
                          f"{LANGUES.get(langue_sys, langue_sys)}").pack(anchor="w")
        ligne = ttk.Frame(f)
        ligne.pack(fill="x", pady=4)
        ttk.Label(ligne, text="Langue de la voix d'Orion :").pack(side="left")
        self.langue = tk.StringVar(value=LANGUES.get(self.cfg["langue"], "français"))
        choix = ttk.Combobox(ligne, textvariable=self.langue, values=list(LANGUES.values()), width=14,
                             state="readonly")
        choix.pack(side="left")
        choix.bind("<<ComboboxSelected>>", lambda e: self._rafraichir_voix_systeme())
        self.toutes = tk.BooleanVar()
        ttk.Checkbutton(ligne, text="afficher toutes les voix", variable=self.toutes,
                        command=self._rafraichir_voix_systeme).pack(side="left", padx=8)

        self.liste_tts = tk.Listbox(f, height=8)
        self.liste_tts.pack(fill="x")
        self.liste_tts.bind("<<ListboxSelect>>", lambda e: self._proposer_genre())
        ligne_genre = ttk.Frame(f)
        ligne_genre.pack(fill="x", pady=4)
        ttk.Label(ligne_genre, text=f"{self.cfg['nom']} se présente au :").pack(side="left")
        self.genre_voix = tk.StringVar(value=self.cfg.get("genre", "neutre"))
        for cle, libelle in GENRES.items():
            ttk.Radiobutton(ligne_genre, text=libelle, value=cle, variable=self.genre_voix).pack(side="left", padx=4)
        boutons = ttk.Frame(f)
        boutons.pack(fill="x", pady=4)
        ttk.Button(boutons, text="▶ Écouter", command=self._tester_voix).pack(side="left")
        ttk.Button(boutons, text="Utiliser cette voix", command=self._choisir_voix).pack(side="left")
        ttk.Label(f, text="Orion comprend toujours le français ; seule sa voix change de langue.",
                  foreground=DISCRET).pack(anchor="w")

        self._section_piper(f)

        texte, liens = self.AIDE_VOIX.get(systeme, self.AIDE_VOIX["Linux"])
        aide = ttk.LabelFrame(f, text="Il manque une voix ? Comment en installer une", padding=6)
        aide.pack(fill="x", pady=6)
        ttk.Label(aide, text=texte, wraplength=680, justify="left").pack(anchor="w")
        rangee = ttk.Frame(aide)
        rangee.pack(anchor="w", pady=4)
        for libelle, cible in liens:
            ttk.Button(rangee, text=libelle, command=lambda c=cible: self._ouvrir_systeme(c)).pack(side="left")
        ttk.Button(rangee, text="Rechercher sur internet", command=self._rechercher_voix).pack(side="left")
        self._rafraichir_voix_systeme()

    def _section_piper(self, f):
        """Voix naturelles hors ligne (Piper), téléchargées à la demande."""
        from . import piper
        cadre = ttk.LabelFrame(f, text="Voix naturelles hors ligne (voix Piper) — recommandé", padding=6)
        cadre.pack(fill="x", pady=6)
        self.choix_piper = tk.StringVar(value=self.cfg.get("voix_piper") or "siwis")
        for i, (cle, v) in enumerate(piper.VOIX.items()):
            etat = "installée" if piper.installee(cle) else "à télécharger"
            ttk.Radiobutton(cadre, text=f"{v['nom']} · {v['licence']} · {etat}", value=cle,
                            variable=self.choix_piper).grid(row=i, column=0, columnspan=4, sticky="w")
        rangee = ttk.Frame(cadre)
        rangee.grid(row=len(piper.VOIX), column=0, columnspan=4, sticky="w", pady=4)
        self.etat_piper = tk.StringVar(value="Voix utilisée : " + (piper.VOIX[self.cfg["voix_piper"]]["nom"]
                                       if self.cfg.get("voix_piper") in piper.VOIX else "voix du système"))
        ttk.Button(rangee, text="Installer…", command=self._installer_piper).pack(side="left")
        ttk.Button(rangee, text="Utiliser", command=self._utiliser_piper).pack(side="left")
        ttk.Button(rangee, text="▶ Écouter", command=self._ecouter_piper).pack(side="left")
        ttk.Button(rangee, text="Revenir à la voix du système", command=self._voix_systeme).pack(side="left")
        ttk.Label(cadre, textvariable=self.etat_piper, foreground=ACCENT).grid(row=len(piper.VOIX) + 1, column=0,
                                                                               columnspan=4, sticky="w")

    def _installer_piper(self):
        from . import espace, piper
        cle = self.choix_piper.get()
        if piper.installee(cle):
            return self.etat_piper.set("Cette voix est déjà installée.")
        self.etat_piper.set("Calcul de l'espace nécessaire…")

        def estimer():
            try:
                lignes = piper.estimer(cle)
            except Exception as e:
                return self.root.after(0, lambda: self.etat_piper.set(f"Impossible d'estimer (internet ?) : {e}"))
            total = sum(o for _, o in lignes)
            detail = "\n".join(f"• {l} : {o / 1e6:.0f} Mo" for l, o in lignes)

            def confirmer():
                texte = (f"Installer la voix « {piper.VOIX[cle]['nom']} » occupera environ {total / 1e6:.0f} Mo :\n\n"
                         f"{detail}\n\nLicence de la voix : {piper.VOIX[cle]['licence']}. Le moteur sherpa-onnx (Apache 2.0) "
                         "est téléchargé depuis sa page officielle et reste un programme séparé.\n\nContinuer ?")
                if not messagebox.askokcancel("Voix naturelle", texte):
                    return self.etat_piper.set("")

                def installer():
                    try:
                        piper.installer(cle, lambda m: self.root.after(0, lambda: self.etat_piper.set(m)))
                    except Exception as e:
                        self.root.after(0, lambda: self.etat_piper.set(f"Échec : {e}"))
                threading.Thread(target=installer, daemon=True).start()
            self.root.after(0, confirmer)
        threading.Thread(target=estimer, daemon=True).start()

    def _utiliser_piper(self):
        from . import piper
        cle = self.choix_piper.get()
        if not piper.installee(cle):
            return self.etat_piper.set("Installez d'abord cette voix.")
        self.cfg.update(voix_piper=cle, genre=piper.VOIX[cle]["genre"])
        sauver(self.cfg)
        self.etat_piper.set(f"Voix utilisée : {piper.VOIX[cle]['nom']}. Orion l'utilise dès sa prochaine phrase.")

    def _voix_systeme(self):
        self.cfg["voix_piper"] = ""
        sauver(self.cfg)
        self.etat_piper.set("Voix utilisée : voix du système.")

    def _ecouter_piper(self):
        from . import piper
        cle = self.choix_piper.get()
        if not piper.installee(cle):
            return self.etat_piper.set("Installez d'abord cette voix.")
        bouche = Bouche(dict(self.cfg, voix_piper=cle, langue="fr"))
        cfg_essai = dict(self.cfg, genre=piper.VOIX[cle]["genre"])
        threading.Thread(target=lambda: (bouche.dire(salutation(cfg_essai) + " Voici ma voix naturelle."),
                                         bouche.fermer()), daemon=True).start()

    def _code_langue(self):
        return next(c for c, n in LANGUES.items() if n == self.langue.get())

    def _rafraichir_voix_systeme(self):
        self.liste_tts.delete(0, "end")
        code = self._code_langue()
        try:
            self.voix_affichees = [v for v in lister_voix() if self.toutes.get() or code in v[2]]
        except Exception:  # pyttsx3 absent ou moteur vocal indisponible
            self.voix_affichees = []
        for _, nom, codes, genre in self.voix_affichees:
            self.liste_tts.insert("end", f"{nom}  ({', '.join(sorted(codes)) or '?'})"
                                         f"{'  · ' + GENRES[genre] if genre else ''}")
        if not self.voix_affichees:
            self.liste_tts.insert("end", f"Aucune voix en {self.langue.get()} : voir l'aide ci-dessous.")

    def _voix_selectionnee(self):
        sel = self.liste_tts.curselection()
        return self.voix_affichees[sel[0]] if sel and self.voix_affichees else None

    def _proposer_genre(self):
        """Accorde la présentation à la voix choisie quand son genre est connu ; sinon on garde le réglage."""
        v = self._voix_selectionnee()
        if v and v[3]:
            self.genre_voix.set(v[3])

    def _tester_voix(self):
        v = self._voix_selectionnee()
        if v:
            bouche = Bouche(dict(self.cfg, voix_id=v[0]))
            threading.Thread(target=lambda: (bouche.dire(salutation(dict(self.cfg, genre=self.genre_voix.get()))),
                                             bouche.fermer()), daemon=True).start()

    def _choisir_voix(self):
        v = self._voix_selectionnee()
        if v:
            self.cfg.update(langue=self._code_langue(), voix_id=v[0], langue_confirmee=True,
                            genre=self.genre_voix.get())
            sauver(self.cfg)
            messagebox.showinfo("Voix", f"{self.cfg['nom']} utilisera la voix {v[1]}.")

    @staticmethod
    def _ouvrir_systeme(cible):
        if platform.system() == "Windows":
            os.startfile(cible)
        else:
            subprocess.Popen(["open", cible])

    def _rechercher_voix(self):
        systeme = {"Darwin": "macOS", "Windows": "Windows"}.get(platform.system(), "Linux")
        requete = f"installer voix synthèse vocale {self.langue.get()} {systeme} gratuite"
        webbrowser.open("https://duckduckgo.com/?q=" + requete.replace(" ", "+"))

    # --- Langues de discussion ------------------------------------------------------
    def _langues(self, f):
        ttk.Label(f, text="Langues dans lesquelles on peut parler à Orion. Elles s'installent sur cet ordinateur "
                          "(internet nécessaire une seule fois), puis tout fonctionne hors ligne.",
                  wraplength=720, justify="left").pack(anchor="w")
        self.arbre_langues = ttk.Treeview(f, columns=("etat", "place"), height=11)
        self.arbre_langues.heading("#0", text="Langue")
        self.arbre_langues.heading("etat", text="État")
        self.arbre_langues.heading("place", text="Espace occupé")
        self.arbre_langues.pack(fill="both", expand=True, pady=4)
        boutons = ttk.Frame(f)
        boutons.pack(fill="x")
        ttk.Button(boutons, text="Installer…", command=self._installer_langue).pack(side="left")
        ttk.Button(boutons, text="Retirer", command=self._retirer_langue).pack(side="left")
        ttk.Button(boutons, text="Discuter dans cette langue", command=self._utiliser_langue).pack(side="left")
        ttk.Button(boutons, text="Crédits des traductions", command=self._credits).pack(side="right")
        self.etat_langue = tk.StringVar()
        ttk.Label(f, textvariable=self.etat_langue, foreground=ACCENT).pack(anchor="w", pady=4)
        ttk.Label(f, text="Orion réfléchit en français : vos phrases sont traduites, puis ses réponses. La qualité "
                          "est correcte mais pas parfaite pour les termes techniques.",
                  foreground=DISCRET, wraplength=720, justify="left").pack(anchor="w")
        self._rafraichir_langues()

    def _rafraichir_langues(self):
        self.arbre_langues.delete(*self.arbre_langues.get_children())
        actuelle = self.cfg.get("langue_discussion", "fr")
        for code, infos in langues.CATALOGUE.items():
            if code == "fr":
                etat = "langue d'Orion (toujours présente)"
            elif langues.installee(code):
                etat = "installée"
            else:
                etat = "—"
            if code == actuelle:
                etat += " · utilisée pour discuter"
            place = f"{langues.occupe(code) / 1e6:.0f} Mo" if code != "fr" and langues.installee(code) else ""
            self.arbre_langues.insert("", "end", iid=code, text=infos["nom"], values=(etat, place))

    def _langue_choisie(self):
        sel = self.arbre_langues.selection()
        return sel[0] if sel else None

    def _installer_langue(self):
        code = self._langue_choisie()
        if not code or langues.installee(code):
            return
        self.etat_langue.set("Calcul de l'espace nécessaire…")

        def estimer():
            try:
                lignes, libre = langues.estimer(code)
            except Exception as e:
                self.root.after(0, lambda: self.etat_langue.set(f"Impossible d'estimer (internet ?) : {e}"))
                return
            self.root.after(0, lambda: self._confirmer_installation(code, lignes, libre))
        threading.Thread(target=estimer, daemon=True).start()

    def _confirmer_installation(self, code, lignes, libre):
        total = sum(o for _, o in lignes)
        detail = "\n".join(f"• {libelle} : {o / 1e6:.0f} Mo" for libelle, o in lignes)
        texte = (f"Installer le {langues.nom(code)} occupera environ {total / 1e6:.0f} Mo :\n\n{detail}\n\n"
                 f"Espace libre : {libre / 1e9:.1f} Go.\nLes modèles de traduction partagés (anglais ↔ français) "
                 "ne sont téléchargés qu'une fois pour toutes les langues.")
        if total * 1.2 > libre:
            messagebox.showerror("Espace insuffisant", texte)
            self.etat_langue.set("")
            return
        if not messagebox.askokcancel("Installer une langue", texte + "\n\nContinuer ?"):
            self.etat_langue.set("")
            return

        def installer():
            try:
                langues.installer(code, lambda m: self.root.after(0, lambda: self.etat_langue.set(m)))
            except Exception as e:
                self.root.after(0, lambda: self.etat_langue.set(f"Échec de l'installation : {e}"))
            self.root.after(0, self._rafraichir_langues)
        threading.Thread(target=installer, daemon=True).start()

    def _retirer_langue(self):
        code = self._langue_choisie()
        if not code or code == "fr" or not langues.installee(code):
            return
        if messagebox.askokcancel("Retirer", f"Retirer le {langues.nom(code)} et libérer "
                                             f"{langues.occupe(code) / 1e6:.0f} Mo ?"):
            langues.retirer(code)
            if self.cfg.get("langue_discussion") == code:
                self.cfg["langue_discussion"] = "fr"
                sauver(self.cfg)
            self._rafraichir_langues()

    def _utiliser_langue(self):
        code = self._langue_choisie()
        if code and langues.installee(code):
            self.cfg["langue_discussion"] = code
            sauver(self.cfg)
            self._rafraichir_langues()
            messagebox.showinfo("Langue", f"On parlera à Orion en {langues.nom(code)}. Pensez à lui choisir une "
                                          "voix dans cette langue (onglet Voix). Orion l'applique tout seul dans quelques secondes.")

    def _credits(self):
        textes = langues.credits()
        messagebox.showinfo("Crédits des traductions", "\n\n".join(textes) if textes else
                            "Aucun modèle de traduction installé.")

    # --- Famille ----------------------------------------------------------------
    def _famille(self, f):
        ttk.Label(f, text="Voix enregistrées (Orion reconnaît ces personnes) :").pack(anchor="w")
        self.liste_voix = tk.Listbox(f, height=8)
        self.liste_voix.pack(fill="x")
        self._rafraichir_voix()
        ligne = ttk.Frame(f)
        ligne.pack(fill="x", pady=6)
        self.prenom = tk.StringVar()
        ttk.Entry(ligne, textvariable=self.prenom).pack(side="left")
        ttk.Button(ligne, text="Enregistrer sa voix", command=self._enroler).pack(side="left")
        ttk.Button(ligne, text="Compléter sa voix", command=lambda: self._enroler(completer=True)).pack(side="left")
        ttk.Button(ligne, text="Supprimer", command=self._supprimer_voix).pack(side="left")
        ttk.Button(ligne, text="Couleur…", command=self._choisir_couleur).pack(side="left")
        ttk.Button(ligne, text="Comparer les voix…", command=self._comparer_voix).pack(side="left")
        ttk.Button(ligne, text="Mémoire…", command=self._memoire).pack(side="left")
        self.etat_enrolement = tk.StringVar(value="Cliquez, puis lisez 5 phrases à voix haute, une par une. "
                                                  "Fermez Orion vocal pendant l'enregistrement (micro partagé).")
        ttk.Label(f, textvariable=self.etat_enrolement, foreground=DISCRET, wraplength=720,
                  justify="left").pack(anchor="w")

    def _profils(self):
        return json.loads(PROFILS.read_text()) if PROFILS.exists() else {}

    def _rafraichir_voix(self):
        self.liste_voix.delete(0, "end")
        from . import personnes
        for nom in self._profils():
            self.liste_voix.insert("end", f"● {nom}")
            couleur = personnes.couleur(nom)
            if couleur:
                self.liste_voix.itemconfigure("end", foreground=couleur)

    def _memoire(self):
        """Mémoire d'une personne : recherche textuelle dans ses souvenirs et ses échanges, suppression choisie."""
        from . import personnes
        noms = sorted(set(personnes._lire()) | set(self._profils()))
        if not noms:
            messagebox.showinfo("Mémoire", "Orion ne garde encore rien sur personne.")
            return
        f = tk.Toplevel(self.root)
        f.title("Mémoire d'Orion")
        f.configure(bg=FOND)
        haut = ttk.Frame(f)
        haut.pack(fill="x", padx=10, pady=10)
        choix = self.liste_voix.curselection()
        # par défaut : la personne sélectionnée, sinon celle dont Orion garde le plus de choses
        plein = max(noms, key=lambda n: len(personnes.chercher_memoire(n, "")))
        qui = tk.StringVar(value=self.liste_voix.get(choix[0])[2:] if choix else plein)
        cherche = tk.StringVar()
        ttk.Label(haut, text="Personne").pack(side="left")
        style = ttk.Style(f)  # liste déroulante lisible sur le thème sombre (texte clair sur fond sombre)
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", TEXTE)],
                  selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXTE)])
        ttk.Combobox(haut, textvariable=qui, values=noms, width=16, state="readonly").pack(side="left", padx=6)
        ttk.Label(haut, text="Rechercher").pack(side="left")
        champ = ttk.Entry(haut, textvariable=cherche, width=30)
        champ.pack(side="left", padx=6)
        liste = tk.Listbox(f, selectmode="extended", width=110, height=16, bg=SURFACE, fg=TEXTE,
                           selectbackground=ACCENT, selectforeground=FOND, highlightthickness=0)
        liste.pack(fill="both", expand=True, padx=10)
        etat = tk.StringVar()
        ttk.Label(f, textvariable=etat, foreground=DISCRET).pack(anchor="w", padx=10)
        trouvees = []

        def rafraichir(*_):
            trouvees[:] = personnes.chercher_memoire(qui.get(), cherche.get())
            liste.delete(0, "end")
            for genre, _, texte in trouvees:
                liste.insert("end", f"{'★ souvenir' if genre == 'souvenir' else '  échange '}  {texte}")
            etat.set(f"{len(trouvees)} entrée(s)" + (f" contenant « {cherche.get()} »" if cherche.get() else "")
                     + ". Les souvenirs (★) sont gardés sans limite ; les échanges sont les derniers dialogues.")

        def supprimer():
            choisies = [trouvees[i] for i in liste.curselection()]
            if not choisies:
                messagebox.showinfo("Mémoire", "Sélectionnez d'abord les entrées à oublier.", parent=f)
                return
            if messagebox.askyesno("Mémoire", f"Oublier {len(choisies)} entrée(s) de {qui.get()} ?", parent=f):
                personnes.supprimer_entrees(qui.get(), choisies)
                rafraichir()
        bas = ttk.Frame(f)
        bas.pack(fill="x", padx=10, pady=10)
        ttk.Button(bas, text="Oublier la sélection", command=supprimer).pack(side="left")
        ttk.Button(bas, text="Tout sélectionner", command=lambda: liste.select_set(0, "end")).pack(side="left", padx=6)
        cherche.trace_add("write", rafraichir)
        qui.trace_add("write", rafraichir)
        rafraichir()
        champ.focus_set()

    def _comparer_voix(self):
        """Tableau des voix : traits et ressemblances. Ce qui rapproche deux voix au point de les confondre
        clignote en rouge gras ; ce qui les distingue est en vert. Une explication suit, paire par paire."""
        from .voix import HAUTEURS, PROFILS, TOLERANCES, Profils
        f = tk.Toplevel(self.root)
        f.title("Comparer les voix")
        f.configure(bg=FOND)
        zone = tk.Frame(f, bg=FOND)
        zone.pack(fill="both", expand=True)
        maj = tk.StringVar()
        tk.Label(f, textvariable=maj, bg=FOND, fg=DISCRET).pack(anchor="e", padx=10, pady=(0, 6))
        clignotants = []
        vu = {"dates": None}

        def dates():
            return tuple(fic.stat().st_mtime if fic.exists() else 0 for fic in (PROFILS, HAUTEURS))

        def surveiller():  # en direct : Orion apprend pendant la conversation, le tableau suit
            if not f.winfo_exists():
                return
            if dates() != vu["dates"]:
                vu["dates"] = dates()
                for enfant in zone.winfo_children():
                    enfant.destroy()
                clignotants.clear()
                construire()
                maj.set(f"● mis à jour à {__import__('time').strftime('%H:%M:%S')} (suivi en direct)")
            f.after(1500, surveiller)

        def clignoter(allume=[True]):  # rouge vif ↔ rouge sombre, toutes les 0,5 s
            if not f.winfo_exists():
                return
            allume[0] = not allume[0]
            for l in clignotants:
                if l.winfo_exists():
                    l.configure(fg="#ff4d4d" if allume[0] else "#6e1f1f")
            f.after(500, clignoter)

        def construire():
            self._remplir_comparaison(zone, clignotants)
        surveiller()
        clignoter()

    def _remplir_comparaison(self, zone, clignotants):
        """Contenu du comparateur (reconstruit dès qu'Orion apprend une nouvelle valeur de voix)."""
        from .voix import TOLERANCES, Profils
        seuil = self.cfg["seuil_locuteur"]
        donnees = Profils(seuil).comparaison()
        noms = list(donnees)
        traits = [("f0", "Hauteur", "Hz"), ("f1", "F1", "Hz"), ("f2", "F2", "Hz"), ("f3", "F3", "Hz"),
                  ("centre", "Timbre", "Hz"), ("debit", "Débit", "mots/s")]
        rouge, orange, vert = "#ff4d4d", "#ffb13c", "#4dff88"
        # paires confondues (ressemblance des empreintes au-dessus du seuil)
        paires = sorted({tuple(sorted((a, b))) for a in noms for b in noms
                         if a != b and donnees[a]["proches"][b] >= seuil})
        partenaires = {n: [b if a == n else a for a, b in paires if n in (a, b)] for n in noms}

        def proche(n, cle):  # ce trait est-il proche de celui d'une voix avec laquelle n est confondue ?
            v = donnees[n]["traits"].get(cle)
            return v is not None and any(abs(v - donnees[p]["traits"].get(cle, 1e9)) < TOLERANCES[cle]
                                         for p in partenaires[n])

        f = zone
        grille = tk.Frame(f, bg=FOND)
        grille.pack(padx=10, pady=10)

        def case(ligne, col, texte, couleur=TEXTE, gras=False, clignote=False):
            l = tk.Label(grille, text=texte, bg=SURFACE, fg=couleur, padx=8, pady=4,
                         font=("Helvetica", 11, "bold" if gras else "normal"))
            l.grid(row=ligne, column=col, sticky="nsew", padx=1, pady=1)
            if clignote:
                clignotants.append(l)
        entetes = ["Personne", "Empreintes"] + [t for _, t, _ in traits] + noms
        for c, t in enumerate(entetes):
            case(0, c, t, ACCENT, gras=True)
        for r, n in enumerate(noms, 1):
            d = donnees[n]
            case(r, 0, ("⚠ " if partenaires[n] else "") + n, rouge if partenaires[n] else TEXTE, gras=True)
            case(r, 1, d["empreintes"], orange if d["empreintes"] < 3 else TEXTE)
            for c, (cle, _, unite) in enumerate(traits, 2):
                v = d["traits"].get(cle)
                if v is None:
                    case(r, c, "—", DISCRET)
                elif partenaires[n] and proche(n, cle):
                    case(r, c, f"{v:g}", rouge, gras=True, clignote=True)   # rapproche : source de confusion
                elif partenaires[n]:
                    case(r, c, f"{v:g}", vert, gras=True)                   # distingue : aide à départager
                else:
                    case(r, c, f"{v:g}")
            for c, autre in enumerate(noms, 2 + len(traits)):
                if autre == n:
                    case(r, c, "—", DISCRET)
                    continue
                v = d["proches"][autre]
                if v >= seuil:
                    case(r, c, f"{v:.0%}", rouge, gras=True, clignote=True)
                elif v >= seuil - 0.05:
                    case(r, c, f"{v:.0%}", orange)
                else:
                    case(r, c, f"{v:.0%}")


        # explication, paire par paire
        lignes = []
        for a, b in paires:
            ta, tb = donnees[a]["traits"], donnees[b]["traits"]
            communs = [(t, u, ta[c], tb[c]) for c, t, u in traits if c in ta and c in tb]
            rapproche = [f"{t} {x:g}/{y:g} {u}" for t, u, x, y in communs
                         if abs(x - y) < TOLERANCES[next(c for c, tt, _ in traits if tt == t)]]
            distingue = [f"{t} {x:g}/{y:g} {u}" for t, u, x, y in communs
                         if abs(x - y) >= TOLERANCES[next(c for c, tt, _ in traits if tt == t)]]
            texte = f"{a} ↔ {b} : empreintes ressemblantes à {donnees[a]['proches'][b]:.0%} (seuil {seuil:.0%})"
            if rapproche:
                texte += " ; aussi proches : " + ", ".join(rapproche)
            if distingue:
                texte += " ; ce qui les distingue : " + ", ".join(distingue)
            if not communs:
                texte += " ; traits pas encore mesurés pour les deux : parlez-lui quelques phrases chacun"
            lignes.append(texte + ".")
        tk.Label(f, bg=FOND, fg=TEXTE, wraplength=760, justify="left", font=("Helvetica", 11),
                 text="\n".join(lignes) if lignes else "Aucune confusion : toutes les voix sont sous le seuil.").pack(
            anchor="w", padx=10)
        tk.Label(f, bg=FOND, fg=DISCRET, wraplength=760, justify="left", text=(
            "Rouge clignotant : ce qui rapproche deux voix au point de les confondre. Vert : ce qui les distingue. "
            "Orange : presque au seuil, ou trop peu d'empreintes. Pour départager : réenregistrez ces voix au calme, "
            "à la même distance du micro ; quand Orion hésite il demande qui parle, et « tu te trompes, c'est … » "
            "le corrige.")).pack(anchor="w", padx=10, pady=(4, 10))

    def _choisir_couleur(self):
        """Couleur de la personne sélectionnée : elle teinte le halo de l'hologramme quand Orion la reconnaît."""
        from tkinter import colorchooser
        from . import personnes
        choix = self.liste_voix.curselection()
        if not choix:
            messagebox.showinfo("Couleur", "Sélectionnez d'abord une personne dans la liste.")
            return
        nom = self.liste_voix.get(choix[0])[2:]
        couleur = colorchooser.askcolor(personnes.couleur(nom) or "#4d8bff", title=f"Couleur de {nom}")[1]
        if couleur:
            personnes.modifier(nom, couleur=couleur)
            self._rafraichir_voix()

    def _enroler(self, completer=False):
        """Enregistre la voix dans le panneau même (la version installée n'a pas de console). `completer` :
        cinq phrases de plus pour une voix déjà connue, sans effacer ce qu'Orion en a appris."""
        nom = self.prenom.get().strip()
        if not nom and self.liste_voix.curselection():  # sinon : la personne sélectionnée dans la liste
            nom = self.liste_voix.get(self.liste_voix.curselection()[0])[2:]
        if not nom:
            messagebox.showinfo("Voix", "Tapez un prénom, ou sélectionnez une personne dans la liste.")
            return
        connue = nom in self._profils()
        if connue and not completer and not messagebox.askyesno(
                "Remplacer la voix", f"La voix de {nom} est déjà enregistrée. La remplacer entièrement "
                "(empreintes apprises et traits compris) ? Pour seulement l'améliorer, choisissez « Compléter sa voix »."):
            return
        if completer and not connue:
            completer = False

        def afficher(message):
            self.root.after(0, lambda: self.etat_enrolement.set(message))

        def enregistrer():
            from .config import UTILISATEUR
            from .modeles import installer, manquants
            from .voix import Oreille, Profils
            try:
                if manquants(UTILISATEUR / "models"):
                    afficher("Téléchargement des modèles vocaux (première fois)…")
                    installer(UTILISATEUR / "models")
                oreille, vecteurs, mesures = Oreille(self.cfg), [], []
                afficher(f"{nom}, lisez une phrase à voix haute… (1/5)")
                while len(vecteurs) < 5:
                    texte, vecteur = oreille.phrase()
                    if vecteur:
                        vecteurs.append(vecteur)
                        mesures.append(oreille.traits)
                        afficher(f"✓ « {texte} » — phrase suivante ({len(vecteurs) + 1}/5)" if len(vecteurs) < 5
                                 else "Enregistrement terminé.")
                oreille.flux.stop()
                Profils(self.cfg["seuil_locuteur"]).enregistrer(nom, vecteurs, mesures, completer)
                afficher(f"La voix de {nom} est {'complétée' if completer else 'enregistrée'} : "
                         f"{self.cfg['nom']} la reconnaîtra mieux.")
                self.root.after(0, self._rafraichir_voix)
            except Exception as e:
                afficher(f"Échec de l'enregistrement : {e}")
        threading.Thread(target=enregistrer, daemon=True).start()

    def _supprimer_voix(self):
        profils = self._profils()
        for i in self.liste_voix.curselection():
            profils.pop(self.liste_voix.get(i)[2:], None)
        PROFILS.write_text(json.dumps(profils))
        self._rafraichir_voix()

    # --- Réglages ---------------------------------------------------------------
    def _reglages(self, f):
        c = self.cfg
        self.champs = {
            "nom": tk.StringVar(value=c["nom"]),
            "nom_phonetique": tk.StringVar(value=c.get("nom_phonetique", "")),
            "mots_eveil": tk.StringVar(value=", ".join(c["mots_eveil"])),
            "aimp_exe": tk.StringVar(value=c["aimp_exe"]),
            "dossier_musique": tk.StringVar(value=c["dossier_musique"]),
            "seuil_locuteur": tk.DoubleVar(value=c["seuil_locuteur"]),
            "transparent": tk.BooleanVar(value=c["hologramme"]["transparent"]),
            "bip_ecoute": tk.BooleanVar(value=c.get("bip_ecoute", True)),
        }
        lignes = [("Nom de l'assistant", "nom"), ("Prononciation du nom (facultatif, ex. Oh-ri-on)", "nom_phonetique"),
                  ("Mots d'éveil (séparés par des virgules)", "mots_eveil"),
                  ("Chemin d'AIMP", "aimp_exe"), ("Dossier de musique", "dossier_musique")]
        for i, (lib, cle) in enumerate(lignes):
            ttk.Label(f, text=lib).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=self.champs[cle], width=50).grid(row=i, column=1, sticky="we")
        ttk.Button(f, text="…", width=3, command=lambda: self.champs["aimp_exe"].set(
            filedialog.askopenfilename() or self.champs["aimp_exe"].get())).grid(row=3, column=2)
        ttk.Button(f, text="…", width=3, command=lambda: self.champs["dossier_musique"].set(
            filedialog.askdirectory() or self.champs["dossier_musique"].get())).grid(row=4, column=2)
        ttk.Button(f, text="▶", width=3, command=self._ecouter_nom).grid(row=1, column=2)
        n = len(lignes)
        ttk.Label(f, text="Exigence de reconnaissance des voix").grid(row=n, column=0, sticky="w")
        seuil = ttk.Frame(f)
        seuil.grid(row=n, column=1, sticky="we")
        valeur = ttk.Label(seuil, width=34)

        def afficher_seuil(*_):
            x = self.champs["seuil_locuteur"].get()
            valeur.configure(text=f"{x:.0%} — " + ("souple : reconnaît plus, confond plus" if x < 0.5 else
                                                   "strict : confond moins, reconnaît moins" if x > 0.65 else
                                                   "équilibré"))
        ttk.Scale(seuil, from_=0.3, to=0.8, variable=self.champs["seuil_locuteur"],
                  command=afficher_seuil).pack(side="left", fill="x", expand=True)
        valeur.pack(side="left", padx=6)
        afficher_seuil()
        ttk.Label(f, text="Le terminal d'Orion affiche la ressemblance de chaque voix entendue : réglez le seuil "
                          "un peu sous celle de la famille.", foreground="#8a94a6",
                  wraplength=520).grid(row=n + 1, column=1, sticky="w")
        ttk.Checkbutton(f, text="Bip doux quand Orion se met à écouter",
                        variable=self.champs["bip_ecoute"]).grid(row=n + 2, column=1, sticky="w")
        ttk.Checkbutton(f, text="Hologramme transparent sans bordure",
                        variable=self.champs["transparent"]).grid(row=n + 3, column=1, sticky="w")
        ttk.Button(f, text="Enregistrer", command=self._sauver).grid(row=n + 4, column=1, sticky="e", pady=8)

        cadre = ttk.LabelFrame(f, text="Espace disque d'Orion", padding=6)
        cadre.grid(row=n + 5, column=0, columnspan=3, sticky="we", pady=6)
        self.texte_espace = tk.StringVar()
        ttk.Label(cadre, textvariable=self.texte_espace, justify="left").grid(row=0, column=0, columnspan=4, sticky="w")
        self.jauge = ttk.Progressbar(cadre, length=420, maximum=100)
        self.jauge.grid(row=1, column=0, columnspan=4, sticky="we", pady=4)
        ttk.Label(cadre, text="Limite (Mo) :").grid(row=2, column=0, sticky="w")
        self.limite_mo = tk.IntVar(value=c.get("limite_disque_mo", espace.LIMITE_DEFAUT_MO))
        ttk.Entry(cadre, textvariable=self.limite_mo, width=8).grid(row=2, column=1, sticky="w")
        ttk.Button(cadre, text="Changer la limite…", command=self._changer_limite).grid(row=2, column=2)
        ttk.Button(cadre, text="Alléger", command=self._alleger).grid(row=2, column=3)
        self._rafraichir_espace()

        cadre_d = ttk.LabelFrame(f, text="Dossiers d'enregistrement des documents (mot-clé → chemin)", padding=6)
        cadre_d.grid(row=n + 6, column=0, columnspan=3, sticky="we", pady=6)
        self.liste_dossiers = tk.Listbox(cadre_d, height=4, width=80)
        self.liste_dossiers.grid(row=0, column=0, columnspan=4, sticky="we")
        ttk.Button(cadre_d, text="Ajouter…", command=self._ajouter_dossier).grid(row=1, column=0, sticky="w")
        ttk.Button(cadre_d, text="Retirer", command=self._retirer_dossier).grid(row=1, column=1, sticky="w")
        ttk.Button(cadre_d, text="Par défaut", command=self._dossier_defaut).grid(row=1, column=2, sticky="w")
        ttk.Label(cadre_d, text="À la voix : « fais une fiche PDF sur Pythagore dans école ». Ces documents ne "
                                "comptent pas dans la limite d'espace d'Orion.", foreground=DISCRET,
                  wraplength=700).grid(row=2, column=0, columnspan=4, sticky="w")
        self._rafraichir_dossiers()

        from . import conversation
        cadre_c = ttk.LabelFrame(f, text="Conversation libre — modèle local, rien ne sort de l'ordinateur", padding=6)
        cadre_c.grid(row=n + 7, column=0, columnspan=3, sticky="we", pady=6)
        self.conv_modele = tk.StringVar(value=conversation.choix(c))
        for i, (cle, m) in enumerate(conversation.MODELES.items()):
            etat = "installé" if conversation.installe(cle) else "à télécharger"
            ttk.Radiobutton(cadre_c, text=f"{m['nom']} · ~{m['memoire_go']} Go de mémoire · {m['licence']} · {etat}",
                            value=cle, variable=self.conv_modele).grid(row=i, column=0, columnspan=3, sticky="w")
        ttk.Button(cadre_c, text="Installer…", command=lambda: self._installer_composants(
            [("conversation", self.conv_modele.get())])).grid(row=len(conversation.MODELES), column=0, sticky="w")
        ttk.Label(cadre_c, text="Orion télécharge lui-même le moteur llama.cpp (MIT) et le modèle dans son dossier. "
                                "Sans modèle, il répond aux commandes et à son savoir, mais ne bavarde pas.",
                  foreground=DISCRET, wraplength=700, justify="left").grid(row=len(conversation.MODELES) + 1,
                                                                          column=0, columnspan=3, sticky="w")

    def _rafraichir_espace(self):
        o, l, r = espace.etat(self.cfg)
        lignes = [f"{k} : {v / espace.MO:.1f} Mo" for k, v in espace.categories().items()]
        alerte = "\n⚠ Seuil d'alerte dépassé : allégez ou augmentez la limite." if r >= espace.SEUIL_ALERTE else ""
        self.texte_espace.set("\n".join(lignes) + f"\nTotal : {o / espace.MO:.0f} Mo sur {l / espace.MO:.0f} Mo "
                              f"({r:.0%}) — {espace.libre() / espace.MO:.0f} Mo libres sur le disque" + alerte)
        self.jauge["value"] = min(100, r * 100)

    def _rafraichir_dossiers(self):
        from . import dossiers
        self.liste_dossiers.delete(0, "end")
        self._cles_dossiers = list(dossiers.liste(self.cfg))
        for cle, chemin in dossiers.liste(self.cfg).items():
            marque = "★ " if cle == dossiers.cle_par_defaut(self.cfg) else "   "
            self.liste_dossiers.insert("end", f"{marque}{cle}  →  {chemin}")

    def _cle_dossier(self):
        sel = self.liste_dossiers.curselection()
        return self._cles_dossiers[sel[0]] if sel else None

    def _ajouter_dossier(self):
        from tkinter import simpledialog
        from . import dossiers
        cle = simpledialog.askstring("Nouveau dossier", "Mot-clé pour le désigner à la voix (ex. école) :",
                                     parent=self.root)
        if not cle:
            return
        chemin = filedialog.askdirectory(title=f"Dossier « {cle} »")
        if chemin:
            dossiers.ajouter(self.cfg, cle, chemin)
            sauver(self.cfg)
            self._rafraichir_dossiers()

    def _retirer_dossier(self):
        from . import dossiers
        cle = self._cle_dossier()
        if cle and messagebox.askokcancel("Retirer", f"Retirer le dossier « {cle} » de la liste ? "
                                                      "(Les fichiers qu'il contient ne sont pas supprimés.)"):
            try:
                dossiers.retirer(self.cfg, cle)
            except ValueError as e:
                return messagebox.showerror("Dossiers", str(e))
            sauver(self.cfg)
            self._rafraichir_dossiers()

    def _dossier_defaut(self):
        cle = self._cle_dossier()
        if cle:
            self.cfg["dossier_defaut"] = cle
            sauver(self.cfg)
            self._rafraichir_dossiers()

    def _changer_limite(self):
        try:
            mo = int(self.limite_mo.get())
        except (tk.TclError, ValueError):
            return messagebox.showerror("Limite", "Indiquez une taille en Mo.")
        avertissements = espace.verifier_nouvelle_limite(mo)
        texte = f"Fixer la limite d'espace disque d'Orion à {mo} Mo ?"
        if avertissements:
            texte += "\n\n⚠ " + "\n⚠ ".join(avertissements)
        demander = messagebox.askyesno if not avertissements else messagebox.askokcancel
        if not demander("Limite d'espace disque", texte, icon="warning" if avertissements else "question"):
            return
        self.cfg["limite_disque_mo"] = mo
        sauver(self.cfg)
        if espace.occupe() > mo * espace.MO:
            espace.alleger(espace.occupe() - mo * espace.MO)
        self._rafraichir_espace()

    def _alleger(self):
        if messagebox.askokcancel("Alléger", "Ne garder que les 5 derniers échanges de chacun ? Les souvenirs "
                                              "demandés, les voix et les langues sont conservés."):
            libere = espace.alleger()
            messagebox.showinfo("Alléger", f"{libere / espace.MO:.1f} Mo libérés.")
            self._rafraichir_espace()

    def _ecouter_nom(self):
        """Fait dire le nom avec la prononciation saisie, pour l'ajuster à l'oreille."""
        cfg = dict(self.cfg, nom=self.champs["nom"].get() or "Orion",
                   nom_phonetique=self.champs["nom_phonetique"].get())
        bouche = Bouche(cfg)
        threading.Thread(target=lambda: (bouche.dire(f"Bonjour, je m'appelle {cfg['nom']}."), bouche.fermer()),
                         daemon=True).start()

    def _sauver(self):
        v = {k: var.get() for k, var in self.champs.items()}
        self.cfg.update(nom=v["nom"].strip() or "Orion", nom_phonetique=v["nom_phonetique"].strip(),
                        aimp_exe=v["aimp_exe"],
                        dossier_musique=v["dossier_musique"], seuil_locuteur=round(v["seuil_locuteur"], 2),
                        bip_ecoute=v["bip_ecoute"],
                        mots_eveil=[m.strip().lower() for m in v["mots_eveil"].split(",") if m.strip()])
        self.cfg["conversation"] = {**self.cfg.get("conversation", {}), "modele": self.conv_modele.get()}
        self.cfg["hologramme"].update(transparent=v["transparent"])
        sauver(self.cfg)
        messagebox.showinfo("Réglages", "Enregistré. Orion applique ces réglages tout seul dans quelques "
                                          "secondes (seule l'apparence de la fenêtre de l'hologramme demande "
                                          "de le relancer).")

    def _manquants(self):
        from . import composants
        return composants.manquants(self.cfg)

    def _installer_composants(self, composants):
        """Annonce l'espace nécessaire, propose de relever la limite si besoin (avec ses avertissements),
        puis installe, le tout sans figer la fenêtre."""
        from . import conversation, espace, piper
        if not composants:
            return messagebox.showinfo("Installation", "Tout est déjà installé.")
        modules = {"voix": piper, "conversation": conversation}
        self.etat_installation.set("Calcul de l'espace nécessaire…")

        def estimer():
            try:
                lignes = [l for genre, cle in composants for l in modules[genre].estimer(cle)]
            except Exception as e:
                return self.root.after(0, lambda: self.etat_installation.set(f"Impossible d'estimer (internet ?) : {e}"))
            self.root.after(0, lambda: confirmer(lignes))

        def confirmer(lignes):
            total = sum(o for _, o in lignes)
            detail = "\n".join(f"• {l} : {espace.mo(o)}" for l, o in lignes)
            texte = f"Orion va télécharger environ {espace.mo(total)} :\n\n{detail}"
            besoin = espace.occupe() + total
            if besoin > espace.limite(self.cfg):
                nouvelle = int((besoin / espace.MO + 511) // 512 * 512)  # arrondi au demi-Go supérieur
                avert = espace.verifier_nouvelle_limite(nouvelle)
                texte += (f"\n\nC'est plus que la limite actuelle d'Orion ({espace.mo(espace.limite(self.cfg))}). "
                          f"Il faut la porter à {nouvelle} Mo.")
                if avert:
                    texte += "\n\n⚠ " + "\n⚠ ".join(avert)
                if any("ne pourrait pas" in a for a in avert):
                    self.etat_installation.set("")
                    return messagebox.showerror("Espace insuffisant", texte)
                if not messagebox.askokcancel("Installation", texte + "\n\nRelever la limite et installer ?"):
                    return self.etat_installation.set("")
                self.cfg["limite_disque_mo"] = nouvelle
                sauver(self.cfg)
            elif not messagebox.askokcancel("Installation", texte + "\n\nContinuer ?"):
                return self.etat_installation.set("")

            def installer():
                from . import composants as comp
                try:
                    comp.installer(self.cfg, composants,
                                   lambda m: self.root.after(0, lambda: self.etat_installation.set(m)))
                    self.root.after(0, lambda: self.etat_installation.set(
                        "Installation terminée : Orion l'utilise tout seul dans quelques secondes."))
                except Exception as e:
                    self.root.after(0, lambda: self.etat_installation.set(f"Échec de l'installation : {e}"))
            threading.Thread(target=installer, daemon=True).start()
        threading.Thread(target=estimer, daemon=True).start()

    def _credits_pdf(self):
        from .credits import generer_pdf
        webbrowser.open(generer_pdf().as_uri())

    def lancer(self):
        self.root.mainloop()
