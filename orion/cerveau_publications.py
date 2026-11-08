# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Réponses d'Orion tirées des publications téléchargées : versets, texte du jour, programme de la semaine,
recherche par thème, téléchargements proposés, sources citées."""
import datetime
import os
import re
from pathlib import Path

from . import bible, bibliotheque, dossiers, espace, knowledge, publications
from .texte import normaliser


class Publications:
    """Réponses tirées des publications (mélangé à Cerveau : utilise ses attributs cfg, actions, signaler…)."""

    def _verset(self, code, t, lien):
        """Lit le verset dans la Bible téléchargée ; sinon propose de la télécharger ; sinon l'ouvre."""
        livre, chapitre, debut = bible.LIVRES[int(code[:2]) - 1], int(code[2:5]), int(code[5:])
        # « 3 à 5 », « 3 et 4 » (le « et » disparaît à la conversion des nombres : « 21 3 4 »)
        m = re.search(rf"\b{chapitre}\D+{debut}\s*(?:a|au|jusqu a|et)?\s*(?:versets?\s*)?(\d+)\b", t)
        fin = int(m.group(1)) if m and int(m.group(1)) > debut else None
        nom = f"{bible.nom_livre(livre)} {chapitre}, {'versets' if fin else 'verset'} {debut}{f' à {fin}' if fin else ''}"
        self.derniere_origine = "bible"
        epub = publications.fichier_local("nwt", self._dossiers_publications())
        texte = publications.verset(epub, livre, chapitre, debut, fin) if epub else None
        if texte:
            self._citer(epub, nom, lien)
            return f"{nom} : {texte}", None

        def ouvrir():
            self.actions.ouvrir_lien(lien)
            return "Je n'ai pas trouvé ce verset dans la Bible téléchargée : je te l'affiche à l'écran."
        pub = None if epub else publications.chercher("nwt")
        if not pub:
            return None, ouvrir

        def telecharger_puis_lire():
            try:
                publications.telecharger(pub, dossiers.chemin(self.cfg))
            except OSError:
                return ouvrir()
            return self._verset(code, t, lien)[0] or ouvrir()
        self.en_attente = telecharger_puis_lire
        return (f"Je n'ai pas encore la Bible dans tes documents. Je la télécharge "
                f"({espace.mo(pub['octets'])}) pour te lire ce verset ?"), None

    def _chercher_publications(self, sujet, t):
        """Lit les deux passages les plus proches du sujet (Bible, ou textes du jour si on les demande)."""
        self.derniere_origine = "bible"
        publications.indexer(self._dossiers_publications())  # rapide : seuls les nouveaux fichiers sont lus
        source = ("es" if re.search(r"\btextes? du jour\b", t) else
                  "nwt" if re.search(r"\b(bible|versets?)\b", t) else None)
        trouves = publications.rechercher(sujet, source)
        if not trouves:
            return (f"Je ne trouve rien sur {sujet} dans tes publications téléchargées. Pour la Bible, "
                    "demande-moi « télécharge la Bible »."), None
        if source == "es":
            lieu, texte, _ = trouves[0]
            self._citer_passages(trouves[:1])
            texte = publications.sans_coupures(texte)
            return f"Le {lieu[len('texte du '):]} en parlait : {texte}", None
        self._citer_passages(trouves[:2])
        return " ".join(f"{lieu} : {texte}" for lieu, texte, _ in trouves[:2]), None

    def _telecharger_lien(self, lien):
        """Lien copié : publication du site de l'éditeur (EPUB proposé, retenu par son titre), ou tout autre
        document (URL internet ou intranet, fichier de l'ordinateur) ajouté à la bibliothèque et indexé."""
        lien = lien.strip().strip('"')
        d = publications.depuis_lien(lien) if "jw.org" in lien else None
        if not d and (re.match(r"(https?|file)://", lien) or Path(lien).expanduser().is_file()):
            def ajouter():
                try:
                    with self._redaction("l'index du document", "INDEX"):
                        nom, n = bibliotheque.ajouter(lien, dossiers.chemin(self.cfg) / "Bibliothèque")
                except Exception as e:
                    return f"Je n'arrive pas à lire ce document : {e}"
                return (f"J'ai ajouté « {nom} » à ma bibliothèque : {n} passage{'s' if n > 1 else ''} indexé"
                        f"{'s' if n > 1 else ''}. Pose-moi tes questions ; je citerai ce document, comme une "
                        "source non vérifiée.")
            return None, ajouter
        if not d:
            return ("Je ne trouve pas de lien de téléchargement jw.org copié. Sur la page de la publication, "
                    "ouvre la fenêtre de téléchargement et copie le lien de l'EPUB."), None
        pub = publications.chercher(*d)
        if not pub:
            return "Cette publication n'existe pas en EPUB en français.", None
        publications.retenir(pub, *d)
        return self._proposer_publications([pub])

    def _proposer_publications(self, pubs, cle=None, ouvrir=True, puis=None, question=None):
        """Annonce la taille des EPUB, puis (sur « oui ») les télécharge, les ouvre ou enchaîne sur `puis`."""
        titres = " et ".join(f"« {p['titre']} »" for p in pubs)
        taille = espace.mo(sum(p["octets"] for p in pubs))

        def telecharger():
            try:
                for pub in pubs:
                    chemin = publications.telecharger(pub, dossiers.chemin(self.cfg, cle))
                    if ouvrir:
                        self.actions.ouvrir_lien(chemin.as_uri())
            except OSError as e:
                return f"Le téléchargement n'a pas abouti : {e}."
            self.derniere_origine = "bible"
            return puis() if puis else f"Voilà {titres}, dans le dossier {cle or dossiers.cle_par_defaut(self.cfg)}."
        self.en_attente = telecharger
        if question:
            return question.format(titres=titres, taille=taille), None
        return (f"{titres} {'font' if len(pubs) > 1 else 'fait'} {taille}"
                f"{' en tout' if len(pubs) > 1 else ''}. Je {'les' if len(pubs) > 1 else 'le'} télécharge ?"), None

    def _publication_de_la_semaine(self, date, t, lien):
        """Réunion de semaine → cahier Vie et ministère ; week-end → Tour de Garde d'étude (parue deux mois
        avant). Ouvre le fichier déjà téléchargé, sinon propose de le télécharger ; la page web en dernier."""
        if re.search(r"\b(tour de garde|week end|weekend|dimanche|samedi|etude de la tour)\b", t):
            mois = date.replace(day=1) - datetime.timedelta(days=1)
            mois = mois.replace(day=1) - datetime.timedelta(days=1)  # deux mois plus tôt
            code, numero = "w", f"{mois.year}{mois.month:02d}"
        else:
            code, numero = "mwb", f"{date.year}{date.month - (date.month + 1) % 2:02d}"
        self.derniere_origine = "bible"
        ouvrir = bool(re.search(r"\b(ouvre|montre|affiche)\b", t))

        def lire_ou_ouvrir(chemin):
            if code == "mwb" and not ouvrir:  # le programme de la semaine, lu à voix haute
                r = publications.programme_semaine(chemin, date)
                if r:
                    self._citer(chemin, f"semaine du {r[0]}", lien)
                    parties = publications.partie_du_programme(r[1], t)
                    if parties is not r[1]:  # « le thème des joyaux », « les cantiques », « la lecture »…
                        return f"Semaine du {r[0]}. " + ". ".join(parties) + "."
                    return f"Programme de la semaine du {r[0]}. " + ". ".join(r[1]) + "."
            self.actions.ouvrir_lien(chemin.as_uri())
            return "Je t'ouvre " + ("le cahier Vie et ministère." if code == "mwb" else "La Tour de Garde d'étude.")
        nom = f"{code}_F_{numero}.epub"
        for dossier in self._dossiers_publications():  # déjà téléchargé : rien à demander au site
            if (dossier / nom).exists():
                return lire_ou_ouvrir(dossier / nom), None
        pub = publications.chercher(code, numero)
        if not pub:
            self.actions.ouvrir_lien(lien)
            return "Je ne trouve pas encore la publication de cette semaine : je t'affiche la page.", None
        return self._proposer_publications([pub], ouvrir=False, puis=lambda: lire_ou_ouvrir(
            next(d / pub["nom"] for d in self._dossiers_publications() if (d / pub["nom"]).exists())))

    def _citer(self, epub, lieu, url=None, reference=None):
        """Note la publication d'où vient l'information (et sa source d'origine), pour les documents générés."""
        self.sources_reponse.append({"titre": f"{publications.titre_epub(epub)}, {lieu}", "url": url,
                                     "niveau": 2, "consulte": knowledge.aujourdhui(), "portee": "fiche"})
        if reference:
            self.sources_reponse.append({"titre": f"Source d'origine : {publications.origine(reference)}",
                                         "url": None, "niveau": 2, "consulte": knowledge.aujourdhui(),
                                         "portee": "fiche"})

    def _citer_passages(self, trouves):
        for lieu, _, publication in trouves:
            epub = next((d / f"{publication}.epub" for d in self._dossiers_publications()
                         if (d / f"{publication}.epub").exists()), None)
            if epub:
                code = bible.reference(normaliser(lieu.replace(":", " "))) if publication.startswith("nwt") else None
                self._citer(epub, lieu, f"https://www.jw.org/finder?wtlocale=F&bible={code}" if code else None)

    def _dossiers_publications(self):
        return [Path(os.path.expanduser(c)) for c in dossiers.liste(self.cfg).values()]

    def _texte_du_jour(self, date, lien):
        """Lit le texte du jour dans « Examinons les Écritures » téléchargé ; s'il manque, propose de le
        télécharger ; la page web n'est ouverte qu'en dernier recours."""
        code = f"es{date.year % 100:02d}"
        epub = publications.fichier_local(code, self._dossiers_publications())
        self.derniere_origine = "bible"
        if epub:
            r = publications.texte_du_jour(epub, date)
            if r:
                titre, verset, commentaire = r
                reference = re.search(r"\b[a-z]{1,3}\d{2}\.\d{2}\b.*$", commentaire)
                self._citer(epub, titre[0].lower() + titre[1:], lien, reference.group(0) if reference else None)
                commentaire = re.sub(r"\s*\b[a-z]{1,3}\d{2}\.\d{2}\b.*$", "", commentaire)  # référence finale
                texte = f"Texte du {titre[0].lower() + titre[1:]}. {verset} {commentaire}"
                return publications.sans_coupures(texte), None
        pub = publications.chercher(code)

        def ouvrir():
            self.actions.ouvrir_lien(lien)
            return "Je n'ai pas le texte dans mes publications : je te l'affiche à l'écran."
        if not pub:
            return None, ouvrir

        def telecharger_puis_lire():
            try:
                publications.telecharger(pub, dossiers.chemin(self.cfg))
            except OSError:
                return ouvrir()
            return self._texte_du_jour(date, lien)[0] or ouvrir()
        self.en_attente = telecharger_puis_lire
        return (f"Je n'ai pas encore « {pub['titre']} » dans tes documents. Je le télécharge "
                f"({espace.mo(pub['octets'])}) pour te le lire ?"), None

    def _emission(self, t):
        """Émission vidéo du mois : déjà téléchargée → ouverte ; sinon téléchargement proposé (taille annoncée,
        360p par défaut, 720p sur demande) ; site injoignable → vidéothèque ouverte à l'écran."""
        from .brain import VIDEOS_MENSUELLES
        self.derniere_origine = "bible"
        haute = bool(re.search(r"\b(haute (?:qualite|definition)|hd|720)\b", t))
        video = publications.emission(t, "720p" if haute else "360p")
        if not video:
            return None, lambda: (self.actions.ouvrir_lien(VIDEOS_MENSUELLES),
                                  "Je t'ouvre la vidéothèque des émissions du mois.")[1]
        dossier = dossiers.chemin(self.cfg) / "Vidéos"
        if (dossier / video["nom"]).exists():
            return None, lambda: (self.actions.ouvrir_lien((dossier / video["nom"]).as_uri()),
                                  f"Je t'ouvre « {video['titre']} ».")[1]

        def telecharger():
            try:
                with self._redaction(f"le téléchargement de « {video['titre']} »", "MP4"):
                    chemin = publications.telecharger(video, dossier, self.signaler)
            except OSError as e:
                return f"Le téléchargement n'a pas abouti : {e}."
            self.actions.ouvrir_lien(chemin.as_uri())
            return f"Voilà « {video['titre']} », dans le dossier Vidéos de tes documents."
        self.en_attente = telecharger
        autre = "" if haute else " Dis « en haute qualité » pour la version 720p."
        return (f"« {video['titre']} » fait {espace.mo(video['octets'])} en {video['qualite']}. "
                f"Je la télécharge ?{autre}"), None
