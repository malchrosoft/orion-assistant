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
from tkinter import filedialog, messagebox, ttk

from . import knowledge, web
from .bouche import LANGUES, Bouche, lister_voix
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
        self.root.geometry("780x560")
        theme(self.root)
        onglets = ttk.Notebook(self.root)
        onglets.pack(fill="both", expand=True)
        for titre, construire in (("Discussion", self._discussion), ("Savoir", self._savoir),
                                  ("Voix", self._voix), ("Famille", self._famille), ("Réglages", self._reglages)):
            cadre = ttk.Frame(onglets, padding=8)
            onglets.add(cadre, text=titre)
            construire(cadre)
        ttk.Button(self.root, text=f"▶ Lancer {self.cfg['nom']} (voix + hologramme)",
                   command=lambda: subprocess.Popen([sys.executable, "-m", "orion"])).pack(pady=6)

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

        cadre = ttk.LabelFrame(f, text="Apprendre depuis un lien internet", padding=6)
        cadre.pack(fill="x", pady=6)
        self.url, self.sujet, self.domaine = tk.StringVar(), tk.StringVar(), tk.StringVar(value="web")
        for i, (lib, var) in enumerate((("Lien", self.url), ("Sujet (facultatif)", self.sujet))):
            ttk.Label(cadre, text=lib).grid(row=i, column=0, sticky="w")
            ttk.Entry(cadre, textvariable=var, width=60).grid(row=i, column=1, sticky="we")
        ttk.Combobox(cadre, textvariable=self.domaine, values=DOMAINES, width=12).grid(row=0, column=2)
        ttk.Button(cadre, text="Lire et retenir", command=self._apprendre).grid(row=1, column=2)

        boutons = ttk.Frame(f)
        boutons.pack(fill="x")
        ttk.Button(boutons, text="Oublier la fiche apprise", command=self._oublier).pack(side="left")
        ttk.Button(boutons, text="Vérifier les références en ligne", command=self._verifier).pack(side="left")

    def _rafraichir_savoir(self):
        self.arbre.delete(*self.arbre.get_children())
        appris = {f["titre"] for f in knowledge._lire(knowledge.APPRIS)}
        for fi in knowledge.toutes_les_fiches():
            self.arbre.insert("", "end", text=fi["titre"], values=(
                fi["domaine"], "⚠ internet, non vérifiée" if fi["titre"] in appris else "livrée"))

    def _apprendre(self):
        url = self.url.get().strip()
        if not url or not messagebox.askokcancel("Prudence", web.AVERTISSEMENT + "\n\nContinuer ?"):
            return

        def tache():
            try:
                _, message = web.apprendre(url, self.sujet.get().strip() or None, self.domaine.get())
            except Exception as e:
                message = f"Impossible de lire la page : {e}"
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
        boutons = ttk.Frame(f)
        boutons.pack(fill="x", pady=4)
        ttk.Button(boutons, text="▶ Écouter", command=self._tester_voix).pack(side="left")
        ttk.Button(boutons, text="Utiliser cette voix", command=self._choisir_voix).pack(side="left")
        ttk.Label(f, text="Orion comprend toujours le français ; seule sa voix change de langue.",
                  foreground=DISCRET).pack(anchor="w")

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

    def _code_langue(self):
        return next(c for c, n in LANGUES.items() if n == self.langue.get())

    def _rafraichir_voix_systeme(self):
        self.liste_tts.delete(0, "end")
        code = self._code_langue()
        try:
            self.voix_affichees = [v for v in lister_voix() if self.toutes.get() or code in v[2]]
        except Exception:  # pyttsx3 absent ou moteur vocal indisponible
            self.voix_affichees = []
        for _, nom, codes in self.voix_affichees:
            self.liste_tts.insert("end", f"{nom}  ({', '.join(sorted(codes)) or '?'})")
        if not self.voix_affichees:
            self.liste_tts.insert("end", f"Aucune voix en {self.langue.get()} : voir l'aide ci-dessous.")

    def _voix_selectionnee(self):
        sel = self.liste_tts.curselection()
        return self.voix_affichees[sel[0]] if sel and self.voix_affichees else None

    def _tester_voix(self):
        v = self._voix_selectionnee()
        if v:
            bouche = Bouche(dict(self.cfg, voix_id=v[0]))
            threading.Thread(target=lambda: (bouche.dire(f"Bonjour, je suis {self.cfg['nom']}."),
                                             bouche.proc.kill()), daemon=True).start()

    def _choisir_voix(self):
        v = self._voix_selectionnee()
        if v:
            self.cfg.update(langue=self._code_langue(), voix_id=v[0], langue_confirmee=True)
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
        ttk.Button(ligne, text="Supprimer", command=self._supprimer_voix).pack(side="left")
        ttk.Label(f, text="L'enregistrement s'ouvre dans une console : lisez 5 phrases à voix haute.",
                  foreground=DISCRET).pack(anchor="w")

    def _profils(self):
        return json.loads(PROFILS.read_text()) if PROFILS.exists() else {}

    def _rafraichir_voix(self):
        self.liste_voix.delete(0, "end")
        for nom in self._profils():
            self.liste_voix.insert("end", nom)

    def _enroler(self):
        if self.prenom.get().strip():
            subprocess.Popen([sys.executable, "-m", "orion", "enroler", self.prenom.get().strip()])

    def _supprimer_voix(self):
        profils = self._profils()
        for i in self.liste_voix.curselection():
            profils.pop(self.liste_voix.get(i), None)
        PROFILS.write_text(json.dumps(profils))
        self._rafraichir_voix()

    # --- Réglages ---------------------------------------------------------------
    def _reglages(self, f):
        c = self.cfg
        self.champs = {
            "nom": tk.StringVar(value=c["nom"]),
            "mots_eveil": tk.StringVar(value=", ".join(c["mots_eveil"])),
            "aimp_exe": tk.StringVar(value=c["aimp_exe"]),
            "dossier_musique": tk.StringVar(value=c["dossier_musique"]),
            "seuil_locuteur": tk.DoubleVar(value=c["seuil_locuteur"]),
            "llm_actif": tk.BooleanVar(value=c["llm"]["actif"]),
            "llm_modele": tk.StringVar(value=c["llm"]["modele"]),
            "transparent": tk.BooleanVar(value=c["hologramme"]["transparent"]),
        }
        lignes = [("Nom de l'assistant", "nom"), ("Mots d'éveil (séparés par des virgules)", "mots_eveil"),
                  ("Chemin d'AIMP", "aimp_exe"), ("Dossier de musique", "dossier_musique"),
                  ("Modèle Ollama", "llm_modele")]
        for i, (lib, cle) in enumerate(lignes):
            ttk.Label(f, text=lib).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=self.champs[cle], width=50).grid(row=i, column=1, sticky="we")
        ttk.Button(f, text="…", width=3, command=lambda: self.champs["aimp_exe"].set(
            filedialog.askopenfilename() or self.champs["aimp_exe"].get())).grid(row=2, column=2)
        ttk.Button(f, text="…", width=3, command=lambda: self.champs["dossier_musique"].set(
            filedialog.askdirectory() or self.champs["dossier_musique"].get())).grid(row=3, column=2)
        n = len(lignes)
        ttk.Label(f, text="Exigence de reconnaissance des voix").grid(row=n, column=0, sticky="w")
        ttk.Scale(f, from_=0.3, to=0.8, variable=self.champs["seuil_locuteur"]).grid(row=n, column=1, sticky="we")
        ttk.Checkbutton(f, text="Hologramme transparent sans bordure",
                        variable=self.champs["transparent"]).grid(row=n + 1, column=1, sticky="w")
        ttk.Checkbutton(f, text="Réponses libres par IA locale (Ollama), signalées comme non sourcées",
                        variable=self.champs["llm_actif"]).grid(row=n + 2, column=1, sticky="w")
        ttk.Button(f, text="Enregistrer", command=self._sauver).grid(row=n + 3, column=1, sticky="e", pady=8)

    def _sauver(self):
        v = {k: var.get() for k, var in self.champs.items()}
        self.cfg.update(nom=v["nom"].strip() or "Orion", aimp_exe=v["aimp_exe"],
                        dossier_musique=v["dossier_musique"], seuil_locuteur=round(v["seuil_locuteur"], 2),
                        mots_eveil=[m.strip().lower() for m in v["mots_eveil"].split(",") if m.strip()])
        self.cfg["llm"].update(actif=v["llm_actif"], modele=v["llm_modele"])
        self.cfg["hologramme"].update(transparent=v["transparent"])
        sauver(self.cfg)
        messagebox.showinfo("Réglages", "Enregistré. Relancez l'assistant pour appliquer.")

    def lancer(self):
        self.root.mainloop()
