#!/usr/bin/env bash
# Regenerate packaging/icon.icns from packaging/icon-src.svg.
#
# Uses macOS QuickLook (WebKit) to rasterise the SVG — no Homebrew rsvg needed.
# Run on macOS. The .icns is committed, so this only needs re-running when the
# source SVG changes.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$here/packaging/icon-src.svg"
out="$here/packaging/icon.icns"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

[ -f "$src" ] || { echo "missing $src" >&2; exit 1; }

# 1024px master via QuickLook
qlmanage -t -s 1024 -o "$work" "$src" >/dev/null 2>&1
master="$work/$(basename "$src").png"
[ -f "$master" ] || { echo "QuickLook did not produce a PNG" >&2; exit 1; }

# standard iconset ladder
set_dir="$work/icon.iconset"
mkdir -p "$set_dir"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size"        "$master" --out "$set_dir/icon_${size}x${size}.png"     >/dev/null
  sips -z $((size*2)) $((size*2)) "$master" --out "$set_dir/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$set_dir" -o "$out"
echo "wrote $out"
