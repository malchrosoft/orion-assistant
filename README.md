# Orion — assistant vocal familial, léger et hors ligne

Orion parle et écoute en français, sans Internet. Il reconnaît chaque membre de la famille à sa voix et pilote la musique (AIMP, Spotify, touches multimédia). Il répond sur les maths jusqu'au bac, la mécanique, l'électronique et les bases du bâtiment, **en citant ses sources**. Un hologramme animé montre ce qu'il fait : il est en veille, écoute, réfléchit, parle ou exécute une tâche.

Projet ludique et public, inspiré de [jarvis-assistant](https://github.com/jaouadinoham2/jarvis-assistant).

## Démarrer (utilisateur lambda)

1. Téléchargez et décompressez le dossier d'Orion.
2. Double-cliquez sur **`Orion.bat`** (Windows), **`Orion.command`** (macOS) ou **`orion.sh`** (Linux).

Au premier lancement, Orion s'installe tout seul : composants, modèles vocaux (≈ 55 Mo) et raccourci sur le bureau. Ensuite, il suffit d'utiliser le raccourci. Si Python manque, la page de téléchargement s'ouvre.

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
  - « parle en anglais », « qui suis-je »

> Avec des haut-parleurs, Orion ignore les mots qu'il est en train de prononcer pour ne pas s'interrompre lui-même. Un casque ou un micro directionnel rend l'interruption plus fiable.

## Le panneau (interface graphique facultative)

Pour l'ouvrir : `python -m orion panneau`, ou un double-clic sur l'hologramme.

| Onglet | Contenu |
|---|---|
| Discussion | Discuter au clavier ; chaque réponse affiche ses sources, cliquables |
| Savoir | Fiches, **apprendre depuis un lien**, oublier, vérifier les références en ligne |
| Voix | Langue et voix d'Orion, écoute d'essai, **façon de se présenter** (neutre par défaut, simplement « Orion » ; féminin ou masculin, proposé selon la voix choisie), **aide pour installer des voix** selon l'OS (bouton vers les réglages système, recherche internet type) |
| Famille | Enregistrer ou supprimer la voix d'un membre de la famille |
| Réglages | Nom, mots d'éveil, AIMP, dossier de musique, exigence de reconnaissance, IA locale |

La langue choisie s'applique à la **voix** d'Orion. Sa compréhension reste en français, avec le modèle Vosk `small-fr`.

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
pip install pyinstaller && python build_exe.py   # dossier dist/Orion avec Orion.exe, sans Python
```

La version packagée n'inclut pas les modèles, pour rester légère : ils se téléchargent au premier lancement. Construisez-la sur l'OS cible.

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
