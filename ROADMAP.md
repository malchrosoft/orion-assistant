# Feuille de route d'Orion

Ce qui est prévu, sans date ni promesse. Les idées passent de « À faire » à « Fait » au fil des versions.

## À faire

### Temps et organisation
- **Alarme via l'application du système** : « réveille-moi à 7 h » programme une alarme dans l'application
  par défaut (Horloge / Rappels sur macOS, Alarmes et horloge sur Windows, l'outil du bureau sous Linux),
  après confirmation de l'heure. Orion ne garde pas d'alarme lui-même : elle doit sonner même s'il est fermé.
- **Rendez-vous dans le calendrier personnel** : selon la personne reconnue à sa voix, Orion crée l'évènement
  dans son calendrier (Calendrier macOS, Outlook, ou fichier .ics à importer). Il pose les questions
  manquantes une à une : date, heure, durée, lieu, invités (avec confirmation de chaque adresse), rappel.
  Chaque membre de la famille choisit son calendrier dans le panneau, onglet Famille.
- **Plusieurs comptes à rebours nommés** (« le minuteur des pâtes »), et reprise après un redémarrage.

### Savoir et publications
- **Recherche par le sens** dans les publications téléchargées (petit modèle local d'« embeddings »,
  100 à 500 Mo) : la recherche actuelle par mots manque les passages qui n'emploient pas les mêmes mots.
- **Autres publications reconnues à la voix** : compléter la liste au fil des besoins.

### Compétences ajoutées (skills)
- **Ajouter des compétences depuis le panneau** : indiquer l'emplacement d'un dossier de compétences
  (fichiers `SKILL.md` : nom, description, méthode), qu'Orion garde en mémoire et relit au démarrage.
- **Les indexer** : nom, description et mots-clés dans l'index local, pour retrouver la compétence adaptée
  à une demande (« fais une recherche… », « prépare un plan… »).
- **Les utiliser automatiquement** : quand une demande correspond, Orion annonce la compétence choisie,
  suit sa méthode avec le modèle local, et respecte ses propres règles (accord avant internet, sources
  citées, rien d'exécuté sur l'ordinateur sans confirmation). Une compétence n'élargit jamais ses droits.
- **Les gérer** : liste dans le panneau, activer/désactiver, retirer ; question à la voix « quelles
  compétences as-tu ? ».

### Documents de qualité professionnelle
- **Installer Tectonic à la demande** (moteur LaTeX, licence MIT, programme séparé), avec annonce de la
  place nécessaire : aujourd'hui, le rapport LaTeX n'est utilisé que si Tectonic est déjà installé.
- **Rapport LaTeX pour les fiches** et la recherche « sur les épaules de géants » (lignée en tableau).
- **Choix du thème** clair ou sombre dans le panneau.

### Interfaces ouvertes à brancher (gratuites, sans clé, vérifiées en novembre 2026)
Chaque appel garde les règles d'Orion : accord avant internet (sauf sites autorisés), rien de stocké
sans raison, source citée.
- **Jours fériés** : `calendrier.api.gouv.fr` (France, Etalab) ou `date.nager.at` (tous pays) — « le 11 novembre
  est-il férié ? », « prochain pont ».
- **Communes et géographie** : `geo.api.gouv.fr` — code postal, département, population.
- **Lever et coucher du soleil** : `api.sunrise-sunset.org` (avec la ville déjà connue pour la météo).
- **Livres** : Open Library (`openlibrary.org`) — auteur, résumé, « trouve un livre sur… ».
- **Produits alimentaires** : Open Food Facts — composition, allergènes, Nutri-Score d'après un nom ou un
  code-barres (licence ODbL).
- **Radios** : Radio Browser (`api.radio-browser.info`) — « mets France Inter », lecture du flux.
- **Taux de change** : Frankfurter (taux de la Banque centrale européenne).
- **Pays** : REST Countries — capitale, monnaie, langues.
- **Quiz en famille** : Open Trivia DB (questions surtout en anglais : à traduire, ou à remplacer par une
  réserve locale en français).
- **Blagues en ligne** : JokeAPI (déjà branchée mais désactivée par défaut, voir plus bas).

### Chansons
- **Pas de chansons connues chantées** : leurs paroles sont protégées, et les services de paroles
  (lyrics.ovh…) les diffusent sans en avoir clairement les droits ; les voix d'Orion ne savent pas chanter
  (synthèse parlée).
- **Possible** : faire écouter un titre dans Spotify ou AIMP (déjà fait), ou réciter / fredonner des
  **comptines du domaine public** (« Au clair de la lune », « Frère Jacques ») avec une petite mélodie
  synthétisée sous la voix.

### Langues
- **Tenir compte de la langue de discussion** partout où Orion va chercher quelque chose :
  - **Météo** : noms de villes et bulletin dans la langue de discussion (le service de géocodage accepte
    la langue), unités et tournures adaptées.
  - **Publications** : télécharger l'EPUB dans la langue de discussion (code de langue du site à associer
    à chaque langue installée), avec repli sur le français si l'édition n'existe pas ; ouvrir la page de
    recherche du site dans la bonne langue ; textes du jour, versets et programmes lus dans cette langue
    (noms des livres, jours et mois propres à chaque langue).
  - **Programme de la semaine** : reconnaître les semaines (« 16-22 novembre », « November 16-22 »…), les
    durées (« min ») et les rubriques dans chaque langue, et lire le programme avec les tournures de la
    langue de discussion (« Programme de la semaine du… », « minutes », « Lecture de la semaine »).
  - **Demandes à la voix** : vocabulaire des réunions, des publications et des comptes à rebours dans
    chaque langue (aujourd'hui seulement en français), et fiches de capacités traduites.
  - **Index local** : une entrée par langue, pour ne pas mélanger les éditions.

### Voix et reconnaissance
- **Réglage fin du seuil de voix** d'après les ressemblances relevées en usage réel ; mieux distinguer
  les voix proches d'une même famille.
- **Interruption à la voix** pendant qu'Orion parle, sans qu'il s'entende (annulation d'écho acoustique).
- **Piloter la musique pendant une lecture** (texte du jour, programme, document lu) :
  - à la voix, une fois l'annulation d'écho en place : « pause », « suivant », « moins fort » sans couper
    la lecture ;
  - dès maintenant possible à la souris : menu du clic droit sur l'hologramme (lecture/pause, suivant,
    volume) et touches multimédia du clavier, qui ne passent pas par le micro ;
  - baisser automatiquement le volume de la musique pendant qu'Orion parle, puis le rétablir.

### Distribution
- **Installateurs** : relancer et vérifier la construction des paquets (exe, dmg, deb) avant une version publiée.

## Fait récemment

- Traits de la voix en plus de l'empreinte : hauteur, trois premiers formants (prédiction linéaire),
  brillance du timbre et débit ; appris par personne, ils départagent les voix proches.
- Mémoire sur soi plus fine : « oublie ça / cette histoire / ce que tu viens de dire » n'efface que
  l'échange juste avant ; « cherche dans ta mémoire sur moi à propos de… » retrouve les souvenirs et
  échanges contenant ces mots, les cite, puis les efface sur confirmation.
- Voix proches mieux départagées : hauteur moyenne de la voix mesurée et apprise en plus de l'empreinte ;
  quand plusieurs voix se ressemblent trop, Orion demande qui parle ; « tu te trompes, c'est … » le fait
  basculer sur la bonne personne et apprendre ; comparaison des voix dans le panneau, onglet Famille.
- Noms de fichiers et formats lus comme on les dit, dans chaque langue : « rapport.pdf » → « rapport point
  P D F », « .docx » → « doc X », « epub » en un mot ; jamais la signification du sigle.
- Sources citées dans les documents générés à partir des publications téléchargées : publication et
  emplacement exact (verset, jour, semaine), lien de consultation, et source d'origine quand le texte en
  donne une (référence d'article en fin de texte du jour).
- Orion se remet seul d'une erreur, avec humour, et relance son écoute si elle s'arrête.
- Rapport PDF de qualité professionnelle composé en LaTeX (« fais-en un rapport PDF de qualité pro »),
  si Tectonic est installé ; sinon le PDF intégré.
- Documents annoncés avec leur nom et leur emplacement, ouverture proposée ; Orion se vante parfois de sa
  rapidité (temps réel de rédaction).
- Blagues pour toute la famille, depuis une réserve locale relue (sans répétition avant d'avoir tout dit) ;
  JokeAPI en option (« blagues_internet »), filtrée, car son « mode sûr » laisse passer des blagues
  inadaptées en français.
- Document tiré de la dernière réponse, à la demande : Word (.docx), Markdown, page web (.html) ou PDF,
  avec la question, la réponse et ses sources ; sans dépendance supplémentaire.
- « Sur les épaules de géants » : comment d'autres ont déjà résolu un problème, d'après des sources
  ouvertes (Wikipédia, catalogue scientifique OpenAlex), avec accord ; idée fondatrice dite en trois
  phrases, lignée complète et sources dans une fiche PDF.
- Orion connaît ses propres capacités (une fiche courte par sujet) : « comment je lance un compte à
  rebours ? » donne la bonne fiche en deux ou trois phrases, « que sais-tu faire ? » un résumé d'une phrase.
- Questions sur l'ordinateur, en lecture seule : espace libre, disques, informations système, versions,
  recherche de fichiers et de dossiers dans le dossier personnel (« ouvre le premier » affiche le dossier).
- Programme de la semaine lu à voix haute depuis la publication hebdomadaire téléchargée (passage biblique,
  cantiques, parties et durées) ; « ouvre » affiche le fichier à la place.
- Réponses courtes (« oui », « non ») jamais prises pour un écho ; saluts qui ne commencent plus par « Oui ».
- Compte à rebours interne : arc et chiffres sur l'hologramme, 5 bips lents à la fin, puis annonce
  à la personne qui l'a demandé si personne n'a cliqué.
- Fenêtres entièrement visibles à l'écran au chargement et après un déplacement.
- Publications EPUB : téléchargement à la demande, index local, vérification au démarrage.
- Texte lu affiché sur 4 lignes qui défilent pendant la lecture.
- Couleur par personne reconnue (halo et nom sur l'hologramme).
- Météo dite à voix haute (Open-Meteo), ville demandée ou devinée sur demande.
- Micro coupé pendant la parole, bip quand Orion écoute, « dis-moi Orion » par défaut.
