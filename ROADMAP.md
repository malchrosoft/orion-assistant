# Feuille de route d'Orion

Ce qui est prévu, sans date ni promesse. Les idées passent de « À faire » à « Fait » au fil des versions.

## En cours

- **Programme de la semaine lu à voix haute** : lire le programme d'une publication hebdomadaire téléchargée
  (parties et durées) au lieu d'ouvrir le fichier, avec l'affichage défilant de l'hologramme.
- **« Oui » pris pour un écho** : ne plus commencer les saluts par « Oui », et réserver le filtre d'écho
  aux phrases d'au moins trois mots (le micro est déjà coupé pendant qu'Orion parle).

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

### Langues
- **Tenir compte de la langue de discussion** partout où Orion va chercher quelque chose :
  - **Météo** : noms de villes et bulletin dans la langue de discussion (le service de géocodage accepte
    la langue), unités et tournures adaptées.
  - **Publications** : télécharger l'EPUB dans la langue de discussion (code de langue du site à associer
    à chaque langue installée), avec repli sur le français si l'édition n'existe pas ; ouvrir la page de
    recherche du site dans la bonne langue ; textes du jour, versets et programmes lus dans cette langue
    (noms des livres, jours et mois propres à chaque langue).
  - **Index local** : une entrée par langue, pour ne pas mélanger les éditions.

### Voix et reconnaissance
- **Réglage fin du seuil de voix** d'après les ressemblances relevées en usage réel ; mieux distinguer
  les voix proches d'une même famille.
- **Interruption à la voix** pendant qu'Orion parle, sans qu'il s'entende (annulation d'écho acoustique).

### Distribution
- **Installateurs** : relancer et vérifier la construction des paquets (exe, dmg, deb) avant une version publiée.

## Fait récemment

- Compte à rebours interne : arc et chiffres sur l'hologramme, 5 bips lents à la fin, puis annonce
  à la personne qui l'a demandé si personne n'a cliqué.
- Fenêtres entièrement visibles à l'écran au chargement et après un déplacement.
- Publications EPUB : téléchargement à la demande, index local, vérification au démarrage.
- Texte lu affiché sur 4 lignes qui défilent pendant la lecture.
- Couleur par personne reconnue (halo et nom sur l'hologramme).
- Météo dite à voix haute (Open-Meteo), ville demandée ou devinée sur demande.
- Micro coupé pendant la parole, bip quand Orion écoute, « dis-moi Orion » par défaut.
