# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Onglet Famille du panneau : voix enregistrées (enregistrer, compléter, supprimer), couleur de chacun,
comparateur des voix en direct, mémoire de chaque personne."""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .theme import ACCENT, DISCRET, FOND, SURFACE, TEXTE
from .voix import Profils


class Famille:
    """Onglet Famille (mélangé à Panneau : utilise ses attributs root, cfg…)."""

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
        return Profils(self.cfg["seuil_locuteur"]).data

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
        f = self.secondaire("memoire", "Mémoire d'Orion")
        if f is None:
            return
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
        from .voix import HAUTEURS, PROFILS
        f = self.secondaire("comparer", "Comparer les voix")
        if f is None:
            return
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
        profils = Profils(self.cfg["seuil_locuteur"])
        for i in self.liste_voix.curselection():
            profils.retirer(self.liste_voix.get(i)[2:])
        self._rafraichir_voix()

    # --- Réglages ---------------------------------------------------------------
