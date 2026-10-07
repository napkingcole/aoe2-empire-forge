# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller aoe2civbuilder.spec
#
# EF_STORE=1 builds the Microsoft Store variant instead: a one-FOLDER bundle
# (dist/AOE2EmpireForge/) for packaging/msix to wrap.  The MSIX install folder
# is read-only and already unpacked, so the one-file self-extraction to %TEMP%
# would only cost startup time and antivirus suspicion.
#
# Bundles app.py (the Flask UI) into a single executable so end users can
# double-click it with no Python install. All data files referenced via
# Path(__file__).parent at runtime (see CLAUDE.md "Key Files") are included
# here at the same relative paths so those lookups resolve unchanged inside
# the frozen bundle.
import os

STORE = os.environ.get('EF_STORE') == '1'

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
        ('team_bonus_names.json', '.'),
        ('civilizations.json', '.'),
        ('aiconfig.json', '.'),
        ('futuravailableunits.json', '.'),
        # Names every unit-voice clip in the game's Wwise banks.  The clips
        # themselves are read from the PLAYER's install at build time
        # (voice_source.py), so no game audio ships in the exe; the picker
        # previews in static/audio/voice are the only bundled voice lines.
        ('voice_wwise_map.json', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if STORE:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='AOE2EmpireForge',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
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
        name='AOE2EmpireForge',
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='AOE2EmpireForge',
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
