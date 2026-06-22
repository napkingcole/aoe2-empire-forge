# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller aoe2civbuilder.spec
#
# Bundles app.py (the Flask UI) into a single executable so end users can
# double-click it with no Python install. All data files referenced via
# Path(__file__).parent at runtime (see CLAUDE.md "Key Files") are included
# here at the same relative paths so those lookups resolve unchanged inside
# the frozen bundle.

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('CivTechTrees', 'CivTechTrees'),
        ('uniticons', 'uniticons'),
        ('ai_stubs', 'ai_stubs'),
        ('vanilla/aoe2techtree_strings', 'vanilla/aoe2techtree_strings'),
        ('bonus_catalog_raw.json', '.'),
        ('bonus_names.json', '.'),
        ('civilizations.json', '.'),
        ('aiconfig.json', '.'),
        ('futuravailableunits.json', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AoE2CivBuilder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
