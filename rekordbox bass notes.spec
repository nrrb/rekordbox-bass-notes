# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for "rekordbox bass notes" (macOS .app).

Build with the repo venv, after `npm run build` has populated frontend/dist:

    .venv/bin/pyinstaller "rekordbox bass notes.spec" --noconfirm

or just run scripts/build_app.sh, which also makes the .dmg.

Notes for this stack:
  - sqlcipher3-wheels ships a compiled extension imported dynamically by
    pyrekordbox -> collect_dynamic_libs.
  - pyrekordbox bundles the offline key blob + a config module reading plists
    -> collect_all.
  - imageio_ffmpeg ships the ffmpeg binary in its package dir -> collect_all,
    and we re-mark it executable at runtime (see backend.analysis).
  - soundfile bundles libsndfile under _soundfile_data -> collect_all.
  - uvicorn late-imports its protocol/lifespan impls -> hiddenimports.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

APP_NAME = "rekordbox bass notes"
# The Mach-O executable is named separately from the .app so the running process
# is NOT "rekordbox bass notes" — a process-name prefix match for "rekordbox"
# (ours, or a third party's) would otherwise mistake this app for Rekordbox
# itself. CFBundleName / the window title stay "rekordbox bass notes".
EXE_NAME = "bass-notes"
BUNDLE_ID = "com.example.rekordbox-bass-notes"  # set to your reverse-domain id

spec_dir = Path(os.path.abspath(SPECPATH))

# --- version from backend/__init__.py --------------------------------------
_ver = "0.0.0"
for line in (spec_dir / "backend" / "__init__.py").read_text().splitlines():
    if line.strip().startswith("__version__"):
        _ver = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

# --- frontend build must exist -------------------------------------------
dist_index = spec_dir / "frontend" / "dist" / "index.html"
if not dist_index.is_file():
    raise SystemExit(
        "frontend/dist/index.html is missing — run `npm --prefix frontend run build` first"
    )

datas = [(str(spec_dir / "frontend" / "dist"), "frontend/dist")]
binaries = []
hiddenimports = [
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
]

for pkg in ("pyrekordbox", "soundfile", "imageio_ffmpeg", "scipy", "numpy"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# sqlcipher3 compiled extension (SQLCipher + OpenSSL, statically linked)
for mod in ("sqlcipher3", "sqlcipher3.dbapi2", "pysqlcipher3"):
    try:
        binaries += collect_dynamic_libs(mod)
    except Exception:
        pass

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=[str(spec_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(spec_dir / "packaging" / "icon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=_ver,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": _ver,
        "CFBundleVersion": _ver,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.music",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
