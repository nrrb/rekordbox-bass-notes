#!/usr/bin/env bash
# Reproducible build: frontend -> PyInstaller .app -> .dmg
#
#   scripts/build_app.sh [--no-dmg]
#
# Run on an Apple Silicon Mac with the repo venv at ./.venv. PyInstaller does
# not cross-compile; an Intel build needs an Intel (or Rosetta) machine.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

APP_NAME="rekordbox bass notes"
VENV="${VENV:-$root/.venv}"
PY="$VENV/bin/python"
MAKE_DMG=1
[ "${1:-}" = "--no-dmg" ] && MAKE_DMG=0

[ -x "$PY" ] || { echo "no venv python at $PY" >&2; exit 1; }

echo "==> versions"
"$PY" --version
"$VENV/bin/pyinstaller" --version

echo "==> frontend build"
if [ -d frontend/node_modules ]; then
  npm --prefix frontend ci
else
  npm --prefix frontend ci
fi
npm --prefix frontend run build

echo "==> icon"
[ -f packaging/icon.icns ] || bash scripts/make_icns.sh

echo "==> PyInstaller"
rm -rf build "dist/$APP_NAME" "dist/$APP_NAME.app"
"$VENV/bin/pyinstaller" "$APP_NAME.spec" --noconfirm

APP="dist/$APP_NAME.app"
[ -d "$APP" ] || { echo "build produced no $APP" >&2; exit 1; }

echo "==> ad-hoc codesign (so it launches locally; real signing is Phase 2)"
codesign --force --deep --sign - "$APP" || true

if [ "$MAKE_DMG" = "1" ]; then
  echo "==> dmg"
  DMG="dist/$APP_NAME-$("$PY" -c 'import backend;print(backend.__version__)').dmg"
  rm -f "$DMG"
  if command -v create-dmg >/dev/null 2>&1; then
    create-dmg --volname "$APP_NAME" --app-drop-link 480 170 \
      --icon "$APP_NAME.app" 160 170 --window-size 660 360 \
      "$DMG" "$APP" || true
  fi
  if [ ! -f "$DMG" ]; then
    echo "   (create-dmg unavailable or failed; using hdiutil)"
    staging="$(mktemp -d)"
    cp -R "$APP" "$staging/"
    ln -s /Applications "$staging/Applications"
    hdiutil create -volname "$APP_NAME" -srcfolder "$staging" -ov -format UDZO "$DMG"
    rm -rf "$staging"
  fi
  echo "==> artifact"
  echo "$DMG"
  shasum -a 256 "$DMG"
else
  echo "==> artifact"
  echo "$APP"
fi
