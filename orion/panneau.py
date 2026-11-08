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
        self.root.geometry("780x560")
        theme(self.root)
        onglets = ttk.Notebook(self.root)
        onglets.pack(fill="both", expand=True)
        for titre, construire in (("Discussion", self._discussion), ("Savoir", self._savoir),
                                  ("Voix", self._voix), ("Langues", self._langues), ("Famille", self._famille), ("Réglages", self._reglages)):
            cadre = ttk.Frame(onglets, padding=8)
            onglets.add(cadre, text=titre)
            construire(cadre)
        bas = ttk.Frame(self.root)
        bas.pack(pady=6)
        lancer = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "orion"]
        ttk.Button(bas, text=f"▶ Lancer {self.cfg['nom']} (voix + hologramme)",
                   command=lambda: subprocess.Popen(lancer)).pack(side="left", padx=4)
        ttk.Button(bas, text="Crédits (PDF)", command=self._credits_pdf).pack(side="left", padx=4)

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
                                          "voix dans cette langue (onglet Voix). Relancez Orion pour appliquer.")

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
        ttk.Button(ligne, text="Supprimer", command=self._supprimer_voix).pack(side="left")
        self.etat_enrolement = tk.StringVar(value="Cliquez, puis lisez 5 phrases à voix haute, une par une. "
                                                  "Fermez Orion vocal pendant l'enregistrement (micro partagé).")
        ttk.Label(f, textvariable=self.etat_enrolement, foreground=DISCRET, wraplength=720,
                  justify="left").pack(anchor="w")

    def _profils(self):
        return json.loads(PROFILS.read_text()) if PROFILS.exists() else {}

    def _rafraichir_voix(self):
        self.liste_voix.delete(0, "end")
        for nom in self._profils():
            self.liste_voix.insert("end", nom)

    def _enroler(self):
        """Enregistre la voix dans le panneau même (la version installée n'a pas de console)."""
        nom = self.prenom.get().strip()
        if not nom:
            return

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
                oreille, vecteurs = Oreille(self.cfg), []
                afficher(f"{nom}, lisez une phrase à voix haute… (1/5)")
                while len(vecteurs) < 5:
                    texte, vecteur = oreille.phrase()
                    if vecteur:
                        vecteurs.append(vecteur)
                        afficher(f"✓ « {texte} » — phrase suivante ({len(vecteurs) + 1}/5)" if len(vecteurs) < 5
                                 else "Enregistrement terminé.")
                oreille.flux.stop()
                Profils(self.cfg["seuil_locuteur"]).enregistrer(nom, vecteurs)
                afficher(f"La voix de {nom} est enregistrée : {self.cfg['nom']} la reconnaîtra.")
                self.root.after(0, self._rafraichir_voix)
            except Exception as e:
                afficher(f"Échec de l'enregistrement : {e}")
        threading.Thread(target=enregistrer, daemon=True).start()

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
            "nom_phonetique": tk.StringVar(value=c.get("nom_phonetique", "")),
            "mots_eveil": tk.StringVar(value=", ".join(c["mots_eveil"])),
            "aimp_exe": tk.StringVar(value=c["aimp_exe"]),
            "dossier_musique": tk.StringVar(value=c["dossier_musique"]),
            "seuil_locuteur": tk.DoubleVar(value=c["seuil_locuteur"]),
            "llm_actif": tk.BooleanVar(value=c["llm"]["actif"]),
            "llm_modele": tk.StringVar(value=c["llm"]["modele"]),
            "transparent": tk.BooleanVar(value=c["hologramme"]["transparent"]),
        }
        lignes = [("Nom de l'assistant", "nom"), ("Prononciation du nom (facultatif, ex. Oh-ri-on)", "nom_phonetique"),
                  ("Mots d'éveil (séparés par des virgules)", "mots_eveil"),
                  ("Chemin d'AIMP", "aimp_exe"), ("Dossier de musique", "dossier_musique"),
                  ("Modèle Ollama", "llm_modele")]
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
        ttk.Scale(f, from_=0.3, to=0.8, variable=self.champs["seuil_locuteur"]).grid(row=n, column=1, sticky="we")
        ttk.Checkbutton(f, text="Hologramme transparent sans bordure",
                        variable=self.champs["transparent"]).grid(row=n + 1, column=1, sticky="w")
        ttk.Checkbutton(f, text="Réponses libres par IA locale (Ollama), signalées comme non sourcées",
                        variable=self.champs["llm_actif"]).grid(row=n + 2, column=1, sticky="w")
        ttk.Button(f, text="Enregistrer", command=self._sauver).grid(row=n + 3, column=1, sticky="e", pady=8)

        cadre = ttk.LabelFrame(f, text="Espace disque d'Orion", padding=6)
        cadre.grid(row=n + 4, column=0, columnspan=3, sticky="we", pady=6)
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
        cadre_d.grid(row=n + 5, column=0, columnspan=3, sticky="we", pady=6)
        self.liste_dossiers = tk.Listbox(cadre_d, height=4, width=80)
        self.liste_dossiers.grid(row=0, column=0, columnspan=4, sticky="we")
        ttk.Button(cadre_d, text="Ajouter…", command=self._ajouter_dossier).grid(row=1, column=0, sticky="w")
        ttk.Button(cadre_d, text="Retirer", command=self._retirer_dossier).grid(row=1, column=1, sticky="w")
        ttk.Button(cadre_d, text="Par défaut", command=self._dossier_defaut).grid(row=1, column=2, sticky="w")
        ttk.Label(cadre_d, text="À la voix : « fais une fiche PDF sur Pythagore dans école ». Ces documents ne "
                                "comptent pas dans la limite d'espace d'Orion.", foreground=DISCRET,
                  wraplength=700).grid(row=2, column=0, columnspan=4, sticky="w")
        self._rafraichir_dossiers()

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
                        mots_eveil=[m.strip().lower() for m in v["mots_eveil"].split(",") if m.strip()])
        self.cfg["llm"].update(actif=v["llm_actif"], modele=v["llm_modele"])
        self.cfg["hologramme"].update(transparent=v["transparent"])
        sauver(self.cfg)
        messagebox.showinfo("Réglages", "Enregistré. Relancez l'assistant pour appliquer.")

    def _credits_pdf(self):
        from .credits import generer_pdf
        webbrowser.open(generer_pdf().as_uri())

    def lancer(self):
        self.root.mainloop()
