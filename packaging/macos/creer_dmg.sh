#!/bin/sh
# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
# Crée dist/Orion-<version>.dmg à partir de dist/Orion.app (python build_exe.py), avec les outils de macOS.
# Usage : packaging/macos/creer_dmg.sh 0.1.0
set -eu
VERSION=${1:-0.1.0}
APP=dist/Orion.app
PLIST="$APP/Contents/Info.plist"

# Autorisation du micro (sans cette phrase, macOS refuse l'accès sans rien demander)
/usr/libexec/PlistBuddy -c "Delete :NSMicrophoneUsageDescription" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string Orion écoute votre voix pour vous répondre. Tout reste sur cet ordinateur." "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"

# Signature ad hoc : l'application n'est pas signée par un compte développeur Apple, macOS demandera
# au premier lancement de l'ouvrir par clic droit → Ouvrir.
codesign --force --deep --sign - "$APP"

DOSSIER=$(mktemp -d)
cp -R "$APP" "$DOSSIER/"
ln -s /Applications "$DOSSIER/Applications"
cp LICENSE THIRD_PARTY_NOTICES.md "$DOSSIER/"
hdiutil create -volname "Orion $VERSION" -srcfolder "$DOSSIER" -ov -format UDZO "dist/Orion-$VERSION.dmg"
rm -r "$DOSSIER"
echo "Prêt : dist/Orion-$VERSION.dmg"
