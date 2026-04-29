# MacYandexMusicRPC.spec — PyInstaller spec for macOS .app bundle
# Build with: pyinstaller MacYandexMusicRPC.spec

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/Paused.png', 'assets'),
        ('assets/Playing.png', 'assets'),
        ('assets/pause.png', 'assets'),
    ],
    hiddenimports=[
        'yandex_music',
        'pypresence',
        'pystray',
        'PIL',
        'keyring.backends.macOS',
        'keyring.backends.SecretService',
        'PyQt6',
        'PyQt6.QtWebEngineWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['winrt', 'win32api', 'win32con', 'win32gui', 'win32console', 'pythoncom', 'winreg'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MacYandexMusicRPC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MacYandexMusicRPC',
)

app = BUNDLE(
    coll,
    name='MacYandexMusicRPC.app',
    # Replace with your .icns if available:
    # icon='assets/YMRPC.icns',
    bundle_identifier='com.makyandexmusicrpc.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': True,
        'CFBundleShortVersionString': '2.5.1',
        'LSUIElement': True,   # hides from Dock (tray-only app)
        'NSMicrophoneUsageDescription': 'Not used',
    },
)
