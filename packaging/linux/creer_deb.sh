#!/bin/sh
# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
# Crée dist/orion_<version>_amd64.deb (Debian, Ubuntu, Mint…) et dist/orion-<version>-linux-x86_64.tar.gz
# à partir de dist/Orion (python build_exe.py). Usage : packaging/linux/creer_deb.sh 0.1.0
set -eu
VERSION=${1:-0.1.0}
RACINE=$(mktemp -d)

mkdir -p "$RACINE/DEBIAN" "$RACINE/opt/orion" "$RACINE/usr/bin" "$RACINE/usr/share/applications" \
         "$RACINE/usr/share/doc/orion" "$RACINE/usr/share/icons/hicolor/256x256/apps" \
         "$RACINE/usr/share/icons/hicolor/512x512/apps"
cp -R dist/Orion/. "$RACINE/opt/orion/"
ln -s /opt/orion/Orion "$RACINE/usr/bin/orion"
cp LICENSE THIRD_PARTY_NOTICES.md "$RACINE/usr/share/doc/orion/"
cp orion/data/logos/orion.png "$RACINE/usr/share/icons/hicolor/256x256/apps/orion.png"
cp orion/data/logos/orion-512.png "$RACINE/usr/share/icons/hicolor/512x512/apps/orion.png"

cat > "$RACINE/usr/share/applications/orion.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Orion
Comment=Assistant vocal familial, léger et hors ligne
Exec=/opt/orion/Orion
Icon=orion
Terminal=false
Categories=Utility;Accessibility;
EOF

# PortAudio (micro) et eSpeak NG (voix) viennent du système sous Linux.
cat > "$RACINE/DEBIAN/control" <<EOF
Package: orion
Version: $VERSION
Architecture: amd64
Maintainer: Aymeric Malchrowicz <aymeric.malchrowicz@malchrosoft.fr>
Depends: libportaudio2, espeak-ng
Section: utils
Priority: optional
Homepage: https://github.com/malchrosoft/orion-assistant
Description: Orion, assistant vocal familial léger et hors ligne
 Converse en français, reconnaît chaque membre de la famille à sa voix,
 pilote la musique et répond avec des sources. Licence PolyForm Strict 1.0.0.
EOF

dpkg-deb --root-owner-group --build "$RACINE" "dist/orion_${VERSION}_amd64.deb"
tar -C dist -czf "dist/orion-$VERSION-linux-x86_64.tar.gz" Orion
rm -r "$RACINE"
echo "Prêt : dist/orion_${VERSION}_amd64.deb et dist/orion-$VERSION-linux-x86_64.tar.gz"
