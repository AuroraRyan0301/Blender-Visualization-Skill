#!/usr/bin/env bash
# blender_kit installer: downloads + extracts Blender 4.2 LTS, prints how to
# wire it up. Idempotent — skip if blender/ already exists.
#
# Usage:
#   bash install.sh                # default: linux x64
#   BLENDER_VERSION=4.2.18 bash install.sh
#
# After install, point the kit at the bundled blender:
#   export BLENDER="$PWD/blender/blender"
set -e

VERSION="${BLENDER_VERSION:-4.2.18}"
MAJOR_MINOR="${VERSION%.*}"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLENDER_DIR="$KIT_DIR/blender"

if [[ -x "$BLENDER_DIR/blender" ]]; then
    echo "[install] blender already present at $BLENDER_DIR/blender"
    "$BLENDER_DIR/blender" --version | head -1
    echo
    echo "Point the kit at it with:"
    echo "  export BLENDER=\"$BLENDER_DIR/blender\""
    exit 0
fi

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)
case "$OS-$ARCH" in
    Linux-x86_64)   PKG="blender-${VERSION}-linux-x64.tar.xz";    DIRNAME="blender-${VERSION}-linux-x64" ;;
    Darwin-x86_64)  PKG="blender-${VERSION}-macos-x64.dmg";        DIRNAME="" ;;
    Darwin-arm64)   PKG="blender-${VERSION}-macos-arm64.dmg";      DIRNAME="" ;;
    *) echo "[install] unsupported platform: $OS $ARCH"; echo "Download Blender ${VERSION} manually from https://www.blender.org/download/ and symlink it as $BLENDER_DIR/blender"; exit 1 ;;
esac

if [[ "$PKG" == *.dmg ]]; then
    echo "[install] macOS: install Blender ${VERSION} from https://www.blender.org/download/"
    echo "  then create the symlink:  ln -s /Applications/Blender.app/Contents/MacOS/Blender $BLENDER_DIR/blender"
    exit 1
fi

URL="https://download.blender.org/release/Blender${MAJOR_MINOR}/${PKG}"
TMP="$KIT_DIR/.blender_dl"
mkdir -p "$TMP"
echo "[install] downloading $URL"
curl -fL --progress-bar -o "$TMP/$PKG" "$URL"

echo "[install] extracting"
tar -xf "$TMP/$PKG" -C "$TMP"
mv "$TMP/$DIRNAME" "$BLENDER_DIR"
rm -rf "$TMP"

echo
echo "[install] done."
"$BLENDER_DIR/blender" --version | head -1
echo
echo "Point the kit at it with:"
echo "  export BLENDER=\"$BLENDER_DIR/blender\""
echo
echo "Quick test:"
echo "  bash examples/smoke.sh"
