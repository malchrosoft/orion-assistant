# Composants tiers et licences

Orion est © 2026 Aymeric Malchrowicz, sous licence PolyForm Strict 1.0.0 (voir `LICENSE`). Il s'appuie sur les
composants ci-dessous, chacun sous sa propre licence. Leurs licences s'appliquent à ces composants, pas à Orion.
Dans les installateurs, les métadonnées et les textes de licence de chaque paquet Python embarqué sont conservés
(dossiers `*.dist-info`).

## Embarqués dans les installateurs

| Composant | Rôle | Licence |
|---|---|---|
| Python (CPython) | Environnement d'exécution | PSF License |
| Tcl/Tk (via Tkinter) | Hologramme et panneau | Licence de type BSD (Tcl/Tk) |
| Vosk (inclut Kaldi) | Reconnaissance vocale | Apache 2.0 |
| sounddevice (inclut PortAudio sous Windows et macOS) | Micro | MIT |
| cffi | Liaison avec les bibliothèques natives | MIT-0 |
| pyttsx3 | Synthèse vocale par les voix du système | MPL-2.0 — source : <https://github.com/nateshmbhat/pyttsx3> |
| comtypes, pywin32 (Windows) | Accès aux voix SAPI | MIT ; PSF |
| CTranslate2 | Moteur de traduction hors ligne | MIT |
| SentencePiece | Découpage du texte pour la traduction | Apache 2.0 |
| NumPy | Calcul (traits de la voix ; dépendance de CTranslate2) | BSD-3-Clause (et licences des sous-composants) |
| pypdf | Lecture du texte des PDF de la bibliothèque | BSD-3-Clause |
| PyYAML | Dépendance de CTranslate2 | MIT |
| requests, urllib3, idna, charset-normalizer | Dépendances de Vosk | Apache 2.0 ; MIT ; BSD-3-Clause ; MIT |
| tqdm | Dépendance de Vosk | MPL-2.0 et MIT — source : <https://github.com/tqdm/tqdm> |
| certifi | Certificats racine | MPL-2.0 — source : <https://github.com/certifi/python-certifi> |
| srt, websockets | Dépendances de Vosk | MIT ; BSD-3-Clause |

Les composants sous MPL-2.0 sont distribués **sans modification** ; leur code source est disponible aux adresses
indiquées.

Outils de fabrication (non distribués) : PyInstaller (GPL-2.0, avec une exception qui autorise la distribution
des programmes produits), Inno Setup (licence permissive de Jordan Russell et Martijn Laan).

## Téléchargés sur le poste, à la demande (non distribués avec Orion)

| Composant | Source | Licence |
|---|---|---|
| Modèles Vosk (français, voix de la famille, autres langues) | <https://alphacephei.com/vosk/models> | Apache 2.0 |
| sherpa-onnx (moteur de voix naturelle) | <https://github.com/k2-fsa/sherpa-onnx> | Apache 2.0. Son exécutable officiel embarque eSpeak NG (GPL-3.0) et ONNX Runtime (MIT) : Orion le lance comme un programme séparé, sans l'inclure ni le modifier |
| Voix Piper françaises (paquets sherpa-onnx) | <https://huggingface.co/rhasspy/piper-voices> | siwis : CC-BY 4.0 ; upmc (Jessica, Pierre) : CC-BY-SA 4.0 ; gilles : CC0. La fiche MODEL_CARD de chaque voix est conservée (attribution). Les voix « tom » et « tjiho » (AGPL-3.0) sont volontairement exclues |
| Voix Piper « Miro » (paquet sherpa-onnx, OpenVoiceOS) | <https://huggingface.co/OpenVoiceOS/pipertts_fr-FR_miro> | CC-BY-NC-ND 4.0 : usage non commercial, utilisée sans modification |
| Supertonic 3 (Supertone, paquet sherpa-onnx ; moteur sherpa-onnx v2.0.1 installé à part) | <https://huggingface.co/Supertone/supertonic-3> | Modèle : BigScience OpenRAIL-M (usage libre ; les restrictions d'usage nuisible de la licence s'appliquent aussi à l'utilisateur) ; code : MIT |
| Kokoro multilingue v1.0 (paquet sherpa-onnx, voix française ff_siwis) | <https://huggingface.co/hexgrad/Kokoro-82M> | Apache 2.0 ; licence conservée dans le paquet téléchargé |
| llama.cpp (moteur de conversation) | <https://github.com/ggml-org/llama.cpp> | MIT. Archive officielle téléchargée à la demande et lancée comme programme séparé |
| Modèles de conversation (GGUF) | <https://huggingface.co> | Ministral 3 3B (Mistral AI) : Apache 2.0 ; Qwen3 1.7B (Qwen) : Apache 2.0 ; Gemma 3 1B : conditions d'utilisation de Gemma (Google) |
| Modèles de traduction Argos Translate | <https://github.com/argosopentech/argos-translate> | Dérivés des modèles OPUS-MT : **CC-BY 4.0**. Le README d'attribution de chaque modèle est conservé et affiché dans le panneau (onglet Langues, « Crédits des traductions ») |

Attribution des modèles OPUS-MT : Jörg Tiedemann et Santhosh Thottingal, « OPUS-MT — Building open translation
services for the World », EAMT 2020.

## Contenus consultés à la demande

| Contenu | Usage | Licence |
|---|---|---|
| Wikipédia (API officielle) | Résumé de deux phrases, avec le titre de l'article et le lien affichés | CC BY-SA 4.0 — l'attribution et le lien vers l'article accompagnent chaque réponse |
| Sites cités en référence | Liens uniquement : aucun contenu n'est copié dans Orion | Selon chaque site |
