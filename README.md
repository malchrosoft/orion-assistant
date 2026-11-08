# Orion — assistant vocal familial, léger et hors ligne

Orion parle et écoute en français, sans Internet. Il reconnaît chaque membre de la famille à sa voix et pilote la musique (AIMP, Spotify, touches multimédia). Il répond sur les maths jusqu'au bac, la mécanique, l'électronique et les bases du bâtiment, **en citant ses sources**. Un hologramme animé montre ce qu'il fait : il est en veille, écoute, réfléchit, parle ou exécute une tâche.

Projet ludique et public, inspiré de [jarvis-assistant](https://github.com/jaouadinoham2/jarvis-assistant).

## Installer (sans Python)

Téléchargez l'installateur de votre système dans les [Releases](https://github.com/malchrosoft/orion-assistant/releases) :

| Système | Fichier | Remarque |
|---|---|---|
| Windows 10/11 (64 bits) | `Orion-Setup-x.y.z.exe` | Installation sans droits administrateur |
| macOS (Apple Silicon ou Intel) | `Orion-x.y.z-macos-*.dmg` | Application non signée par Apple : au premier lancement, clic droit → Ouvrir |
| Linux (Debian, Ubuntu, Mint…) | `orion_x.y.z_amd64.deb` ou `.tar.gz` | Le `.deb` installe aussi PortAudio et eSpeak NG |

Python est inclus. Au premier lancement, Orion télécharge ses modèles vocaux (≈ 55 Mo) ; ensuite tout fonctionne hors ligne. Les systèmes 32 bits et trop anciens ne sont pas pris en charge ; Orion vise en revanche les machines **modestes** (≈ 300 Mo de mémoire).

Réglages, voix de la famille, langues et fiches sont rangés dans le dossier de l'utilisateur : `%APPDATA%\Orion`, `~/Library/Application Support/Orion` ou `~/.local/share/orion`.

### Depuis les sources

Double-cliquez sur **`Orion.bat`** (Windows), **`Orion.command`** (macOS) ou **`orion.sh`** (Linux) : Orion s'installe au premier lancement (Python requis).

Avec la souris :
- **Clic droit sur l'hologramme** : se taire, ouvrir le panneau, quitter.
- **Double-clic** : ouvre le panneau.
- **Glisser** : déplace l'hologramme.

Au tout premier démarrage, Orion annonce la langue de sa voix et **demande confirmation à voix haute**. On répond « oui », ou bien la langue souhaitée.

## Parler avec Orion

- Commencez par « Orion, … ». Après sa réponse, vous avez 8 secondes pour enchaîner sans répéter son nom.
- **Pour l'interrompre**, dites « stop », « tais-toi », « chut », « arrête », ou simplement « Orion » suivi d'une autre demande. Il se tait immédiatement et vous écoute.
- Exemples :
  - « mets de la musique », « morceau suivant », « joue Daft Punk sur Spotify »
  - « monte le son », « ouvre la calculatrice », « combien font 12 fois 7 »
  - « c'est quoi le théorème de Pythagore », « faut-il isoler la toiture en premier »
  - « parle avec moi en espagnol », « qui suis-je »
  - « retiens que je suis allergique aux arachides », « que sais-tu de moi ? »
  - « fais-moi une fiche PDF sur le théorème de Pythagore avec renvois », « génère les crédits en PDF »
  - « quelles bibliothèques utilises-tu ? », « qui a fait ta reconnaissance vocale ? »

## Chaque personne, à sa façon

- **Tutoiement ou vouvoiement** : au premier échange, Orion demande « est-ce qu'on se tutoie ? ». On peut changer à tout moment (« vouvoie-moi », « tutoie-moi »). Le choix est retenu pour chaque voix.
- **Voix non reconnue** : Orion le signale une fois, puis répond de façon générale. Il ne retient rien des personnes qu'il ne connaît pas.
- **Ce qu'il retient** des voix connues, **uniquement sur cet ordinateur** :
  - l'âge, le niveau scolaire et l'humeur récente, quand la personne les mentionne (« j'ai 12 ans », « je suis en cinquième », « je suis fatigué ») ;
  - les 20 derniers échanges, pas davantage ;
  - **sans limite de temps, seulement à la demande** : « retiens que… », « souviens-toi que… ».
- **Garder la main** : « que sais-tu de moi ? » pour tout voir, « oublie que… » pour un souvenir, « oublie ce que tu sais sur moi » pour tout effacer.

> Avec des haut-parleurs, Orion ignore les mots qu'il est en train de prononcer pour ne pas s'interrompre lui-même. Un casque ou un micro directionnel rend l'interruption plus fiable.

## Le panneau (interface graphique facultative)

Pour l'ouvrir : `python -m orion panneau`, ou un double-clic sur l'hologramme.

| Onglet | Contenu |
|---|---|
| Discussion | Discuter au clavier ; chaque réponse affiche ses sources, cliquables |
| Savoir | Fiches, **apprendre depuis un lien**, oublier, vérifier les références en ligne |
| Voix | Langue et voix d'Orion, écoute d'essai, **façon de se présenter** (neutre par défaut, simplement « Orion » ; féminin ou masculin, proposé selon la voix choisie), **aide pour installer des voix** selon l'OS (bouton vers les réglages système, recherche internet type) |
| Langues | **Ajouter ou retirer des langues de discussion** (sauf le français), avec l'**espace nécessaire annoncé avant** toute installation, et les crédits des modèles de traduction |
| Famille | Enregistrer (directement dans le panneau) ou supprimer la voix d'un membre de la famille |
| Réglages | **Espace disque** (jauge, limite, alléger), **dossiers d'enregistrement**, nom, **prononciation du nom** (facultatif, ex. « Oh-ri-on », avec écoute d'essai), mots d'éveil, AIMP, dossier de musique, exigence de reconnaissance, IA locale |

Un bouton **Crédits (PDF)** produit la liste des composants utilisés, avec leurs auteurs et licences.

## Espace disque limité

Orion ne remplira jamais votre disque : ses données internes n'occupent pas plus de **1 Go** par défaut (modèles vocaux, langues et mémoire). Les documents qu'il génère vous appartiennent : ils vont dans vos dossiers (voir ci-dessous) et ne comptent pas.

- **Alerte à 80 %** : Orion prévient une fois par session, et le panneau affiche une jauge détaillée.
- **Limite atteinte** : il s'allège d'abord (historiques réduits aux 5 derniers échanges). Si ça ne suffit pas, il refuse et explique que sa place est limitée par la configuration. Les souvenirs demandés et les voix ne sont jamais supprimés automatiquement.
- **Changer la limite** : uniquement dans le panneau (Réglages → Espace disque) ou avec `python -m orion limite 2048`, **jamais à la voix**, et toujours après confirmation. Orion avertit si la valeur est incohérente : plus petite que ce qu'il occupe, supérieure à l'espace libre, ou trop gourmande.
- « Combien de place occupes-tu ? » : Orion répond à voix haute.

## Où sont enregistrés les documents

Les fiches et les crédits en PDF sont enregistrés dans **vos** dossiers : par défaut `Documents/Orion`.

- **Plusieurs dossiers**, chacun avec un **mot-clé** pour le désigner à la voix : « fais une fiche PDF sur Pythagore **dans école** ».
- **Réglage** au choix :
  - dans le panneau (Réglages → Dossiers d'enregistrement) ;
  - en commande : `python -m orion dossiers ajouter école ~/Documents/École`, `… retirer école`, `… defaut école` ;
  - dans `config.json` : `"dossiers": {"documents": "…", "école": "…"}` et `"dossier_defaut"`.
- Retirer un dossier de la liste ne supprime pas ses fichiers.

## Voix naturelle et conversation libre (installées par Orion)

Orion peut s'installer lui-même, **sur l'ordinateur, sans rien envoyer en ligne** :

| Composant | Rôle | Taille | Licence |
|---|---|---|---|
| sherpa-onnx + voix Piper Siwis (ou Jessica, Pierre, Gilles) | Voix naturelle, bien moins synthétique | ≈ 90 Mo | Apache 2.0 ; voix CC-BY 4.0, CC-BY-SA 4.0 ou CC0 |
| llama.cpp + Ministral 3 3B (ou Qwen3 1.7B, Gemma 3 1B) | Conversation libre en français | ≈ 2,2 Go (0,8 Go pour Gemma) | MIT ; Apache 2.0 (Gemma : conditions Google) |

- **Dans le panneau** : bouton « Installer ce qui manque… ». L'espace nécessaire est annoncé avant. Si la limite d'espace d'Orion est trop basse, il propose de la relever, avec confirmation et vérification de l'espace libre.
- **À la voix** : « installe ce qui te manque ». Orion annonce la taille et attend ton « oui ». La limite ne se change jamais à la voix.
- **Ordre des réponses** : commandes, puis savoir sourcé, puis Wikipédia avec accord pour les questions factuelles, et enfin la conversation libre pour le reste. Le modèle connaît le contexte de la personne (prénom, tutoiement, âge, souvenirs), qui ne quitte jamais l'ordinateur.
- **Mémoire** : le moteur de conversation démarre au premier besoin et s'arrête après 10 minutes sans échange.

## Langues de discussion

Orion pense en français. Pour une autre langue, vos phrases sont traduites en français, puis ses réponses dans votre langue, **sur l'ordinateur, hors ligne**.

- **Langues proposées** : anglais, espagnol, allemand, italien, portugais, néerlandais, polonais, turc, russe, chinois, arabe.
- **Rien n'est stocké dans le dépôt** : la reconnaissance vocale de la langue (Vosk, 32 à 52 Mo) et les modèles de traduction (Argos Translate / OPUS-MT, 65 à 285 Mo par sens) se téléchargent à l'installation de la langue. Internet n'est nécessaire qu'à ce moment-là.
- **L'espace nécessaire est annoncé avant**, comparé à l'espace libre. Les modèles anglais ↔ français, qui servent de relais aux autres langues, ne sont téléchargés qu'une fois.
- **Retirer une langue** libère sa place, sauf ce qui sert encore à une autre langue. Le français ne se retire pas.
- **Les mots essentiels** (« stop », « oui », « non ») sont reconnus grâce à un petit lexique fait à la main dans chaque langue, plus fiable que la traduction automatique.
- La traduction est correcte, mais imparfaite pour les termes techniques. Pour le russe, le chinois et l'arabe, ajoutez le nom d'Orion écrit dans cet alphabet aux mots d'éveil.

## Des réponses sourcées, et une méfiance envers le web

Les réponses scientifiques et les conseils suivent les principes de la skill *shoulders-of-giants* :

- **Hiérarchie des sources** :
  - ★★★ norme, texte officiel ou publication fondatrice (Euclide, Newton, BIPM, INRS…) ;
  - ★★ manuel ouvert reconnu (OpenStax…) ;
  - ★ vulgarisation ;
  - ⚠ page web non vérifiée.
- **Des sources consultées, pas mémorisées** : `python -m orion verifier` ouvre chaque référence en ligne et note la date. Une référence jamais vérifiée n'est **jamais citée**.
- **Citer ce qui appuie l'affirmation** : seules les sources propres à une fiche sont citées. Les références générales d'un domaine sont proposées en « pour aller plus loin ».
- **Questions de décision** (« faut-il… », « devrais-je… ») : Orion ne décide pas à votre place. Il expose ce qui est établi et les conditions à vérifier, et renvoie vers un professionnel pour le bâtiment et l'électricité.
- **Liens internet ajoutés à la demande** (panneau ou `python -m orion apprendre URL [sujet]`) :
  - Orion prévient d'abord du risque de fausse information.
  - Il donne un avis prudent sur le site.
  - Il stocke la fiche en « non vérifiée » et **rappelle ce doute à chaque réponse**.
  - Le texte récupéré est traité comme une simple donnée, jamais comme une consigne.
- **Base de connaissance externe, seulement avec votre accord** : quand la réponse n'est pas dans sa mémoire locale, Orion demande « Puis-je consulter ma base de connaissance externe ? ». Si vous dites « oui », il interroge **Wikipédia** par son API officielle, cite l'article, et le panneau affiche le **lien cliquable**. Il rappelle que Wikipédia est collaborative.
- **« Quelle est ta source ? »** : Orion dit toujours d'où venait sa dernière réponse.
- **IA locale facultative** (Ollama) : ses réponses sont annoncées comme générées et non sourcées.

## Pourquoi il est léger

| Brique | Choix | Poids |
|---|---|---|
| Reconnaissance vocale | Vosk `small-fr` | 42 Mo |
| Reconnaissance des voix | Vosk `spk` | 13 Mo |
| Synthèse vocale | Voix du système via pyttsx3, dans un processus séparé (interruptible) | 0 |
| Hologramme et panneau | Tkinter (inclus avec Python). Constellation d'Orion en perspective, halos, particules, spectre vocal, fondus de couleur : moins de 200 formes par image à 25 images/s | 0 |
| Savoir | SQLite FTS5 (inclus avec Python) | < 200 Ko |

Il faut environ 300 Mo de RAM et Python 3.9 ou plus récent, sur Windows, macOS ou Linux.

## Installation manuelle et packaging

```bash
python install.py              # installation guidée : 3 questions, Entrée = valeur proposée
python install.py --auto       # installation sans question
pip install pyinstaller -r requirements.txt -r requirements-traduction.txt
python build_exe.py            # application autonome dans dist/ (pour l'OS courant)
```

Les installateurs des trois systèmes sont fabriqués par GitHub Actions (`.github/workflows/paquets.yml`) : lancement manuel depuis l'onglet Actions, ou automatique en poussant une étiquette `vX.Y.Z`, qui publie une Release. Scripts : `packaging/windows/orion.iss` (Inno Setup), `packaging/macos/creer_dmg.sh`, `packaging/linux/creer_deb.sh`.

Les modèles ne sont pas inclus, pour rester léger. Les composants tiers et leurs licences sont listés dans [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Commandes

```
python -m orion              voix + hologramme
python -m orion panneau      interface graphique
python -m orion texte        conversation au clavier
python -m orion enroler Léa  enregistre une voix
python -m orion apprendre URL [sujet]
python -m orion verifier     vérifie les références livrées
python -m orion savoir       réindexe après modification de orion/data/*.json
python -m orion holo         démonstration de l'hologramme
```

## Enrichir le savoir

- **Fiches** : `orion/data/savoir.json` (`domaine`, `titre`, `motscles`, `contenu`, `sources` facultatif).
- **Références** : `orion/data/references.json`, par domaine ou par titre de fiche, avec un niveau de 1 à 3.

N'ajoutez que des sources **ouvertes et gratuites**, sans paywall. Lancez ensuite `python -m orion verifier`.

## Licence

© 2026 Aymeric Malchrowicz — [PolyForm Strict 1.0.0](LICENSE) (identifiant SPDX : `LicenseRef-PolyForm-Strict-1.0.0`, la licence ne figurant pas dans la liste officielle SPDX).

- **Utilisation libre, telle quelle**, pour tout usage non commercial : personnel, familial, associatif, éducatif…
- **Interdit** : tout usage commercial, la modification et la redistribution, y compris de versions dérivées.
- **Contributions bienvenues** : un fork n'est autorisé que pour proposer une pull request. Voir [`CONTRIBUTING.md`](CONTRIBUTING.md).
