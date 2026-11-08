# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Documents rédigés par Orion : fiches PDF, export de la dernière réponse (Word, Markdown, HTML, PDF),
recherche « sur les épaules de géants », avec annonce et proposition d'ouverture."""
import contextlib
import random
import re
import subprocess
import time
from pathlib import Path

from . import dossiers, export, knowledge, web


class Documents:
    """Rédaction de documents (mélangé à Cerveau : utilise ses attributs cfg, actions, signaler…)."""

    def _fiche_pdf(self, sujet, renvois, cle=None):
        """Fiche PDF : base locale d'abord ; sinon Wikipédia, après accord (comme pour les réponses orales)."""
        from . import document
        fiche = knowledge.chercher(sujet)

        def produire(f):
            try:
                dossier = dossiers.chemin(self.cfg, cle)
                with self._redaction(f"la fiche sur {f['titre']}") as mesure:
                    chemin = document.generer(f, renvois, dossier)
            except OSError as e:
                return f"Je n'arrive pas à enregistrer la fiche : {e}."
            return self._document_pret(chemin, "la fiche", mesure["duree"])
        if fiche:
            if any(s["niveau"] == 0 for s in fiche["sources"] if s["consulte"]):
                fiche["avertissement"] = ("Attention : cette fiche provient d'une page internet non vérifiée. "
                                          "Recoupez-la avec une source sûre.")
            fiche["lectures"] = [s for s in fiche["sources"] if s["portee"] == "domaine"]
            fiche["sources"] = [s for s in fiche["sources"] if s["portee"] == "fiche"]
            return None, lambda: produire(fiche)

        def depuis_wikipedia():
            try:
                article = web.wikipedia(sujet)
            except Exception:
                return "Je n'arrive pas à joindre ma base externe. Vérifie la connexion internet."
            if not article:
                return "Je n'ai rien trouvé de fiable sur ce sujet."
            return produire({"titre": article["titre"], "contenu": article["contenu"], "domaine": "Wikipédia",
                             "avertissement": "Extrait de Wikipédia, encyclopédie collaborative (CC BY-SA 4.0) : "
                                              "vérifiez les points importants.",
                             "sources": [{"titre": f"Wikipédia, article « {article['titre']} »", "url": article["url"],
                                          "niveau": 1, "consulte": knowledge.aujourdhui()}]})
        if self._libre("wikipedia"):
            return None, depuis_wikipedia
        self.en_attente = depuis_wikipedia
        return "Je n'ai pas ce sujet dans ma mémoire locale. Puis-je consulter ma base de connaissance externe ?", None

    def _geants(self, sujet):
        """Propose la recherche (internet, avec accord), puis dit la synthèse et ouvre la fiche PDF."""
        from . import document, geants

        def chercher():
            r = geants.rechercher(sujet, self.conversation, self.signaler)
            self.derniere_origine = "geants"
            if r["lignee"] or r["wikipedia"]:
                try:
                    with self._redaction("la fiche de recherche") as mesure:
                        chemin = document.generer(geants.fiche(r), True, dossiers.chemin(self.cfg))
                    return geants.a_dire(r).replace(" Je t'ai préparé une fiche avec la lignée complète et les "
                                                    "sources.", "") + " " + self._document_pret(
                        chemin, "la fiche avec la lignée et les sources", mesure["duree"])
                except OSError:
                    pass
            self.signaler("")
            return geants.a_dire(r)
        if self._libre("geants"):
            return None, chercher
        self.en_attente = chercher
        return (f"Je vais chercher comment d'autres ont déjà résolu « {sujet} », dans des sources ouvertes en "
                "ligne : Wikipédia et le catalogue scientifique OpenAlex. J'y vais ?"), None

    @contextlib.contextmanager
    def _redaction(self, libelle, format_="PDF"):
        """Pendant qu'Orion rédige : il l'annonce, et une feuille s'écrit sur l'hologramme (1,5 s au moins,
        même si le fichier est prêt plus vite, pour qu'on voie ce qu'il fait)."""
        debut, mesure = time.monotonic(), {}
        self.symboliser(format_)
        self.signaler(f"Je rédige {libelle}…")
        try:
            yield mesure
        finally:
            mesure["duree"] = time.monotonic() - debut  # temps réel de rédaction, avant l'attente d'affichage
            time.sleep(max(0.0, 1.5 - mesure["duree"]))
            self.symboliser(None)
            self.signaler("")

    def _document_pret(self, chemin, libelle, duree):
        """Annonce le document et propose de l'ouvrir ; de temps en temps, Orion se vante de sa rapidité."""
        dossier = "ton dossier personnel" if chemin.parent == Path.home() else f"le dossier {chemin.parent.name}"
        ms = round(duree * 1000)
        temps = ("moins d'une milliseconde" if ms < 1 else f"{ms} milliseconde{'s' if ms > 1 else ''}" if duree < 1
                 else f"{duree:.1f} secondes".replace(".", ","))
        f = libelle.startswith("la ")  # « la fiche », « la page web » : accords au féminin
        e, il, Libelle = ("e" if f else ""), ("Elle" if f else "Il"), libelle[:1].upper() + libelle[1:]
        if random.random() < 0.35:
            texte = random.choice([
                f"Et voilà : {libelle} rédigé{e} en {temps}, pas mal, non ? {il} s'appelle {chemin.name}, dans {dossier}.",
                f"{temps[:1].upper() + temps[1:]} chrono pour {libelle} ! C'est {chemin.name}, rangé{e} dans {dossier}.",
                f"Je n'ai pas traîné : {temps}. {Libelle} s'appelle {chemin.name}, dans {dossier}."])
        else:
            texte = f"{Libelle} est prêt{e} : {chemin.name}, dans {dossier}."
        self.en_attente = lambda: (self.actions.ouvrir_lien(chemin.as_uri()), "Je te l'ouvre.")[1]
        return texte + " Je l'ouvre ?"

    def _exporter(self, format_, cle=None):
        """Enregistre la dernière réponse dans le format demandé, puis l'ouvre."""
        r = self.derniere_reponse
        if not r:
            return "Pose-moi d'abord une question : j'en ferai ensuite un document.", None
        noms = {"docx": "le document Word", "md": "le fichier Markdown", "html": "la page web", "pdf": "le PDF",
                "pdf_pro": "le rapport PDF"}

        def creer():
            titre = re.sub(r"[?!.]+$", "", r["question"]).strip()
            doc = {"titre": titre[:1].upper() + titre[1:], **r}
            try:
                with self._redaction(noms[format_], "PDF PRO" if format_ == "pdf_pro" else format_.upper()) as mesure:
                    chemin = export.generer(doc, format_, dossiers.chemin(self.cfg, cle))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
                return f"Je n'arrive pas à enregistrer le document : {e}."
            self.export_en_cours = True
            return self._document_pret(chemin, noms[format_], mesure["duree"])
        return None, creer
