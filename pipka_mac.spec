# Сборка PIPKA.app для macOS: запускается из build_mac.command
from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets")]
binaries = []
hiddenimports = []
for package in ("vosk", "sounddevice", "edge_tts"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis(
    ["main.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PIPKA",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PIPKA")
app = BUNDLE(
    coll,
    name="PIPKA.app",
    icon="assets/pipka.png",
    bundle_identifier="com.pipka.assistant",
    info_plist={
        "CFBundleName": "PIPKA",
        "CFBundleDisplayName": "ПИПКА",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "ПИПКА слушает микрофон, чтобы услышать слово «ПИПКА» и твои команды.",
        "NSAppleEventsUsageDescription": "ПИПКА управляет громкостью, музыкой и выключением компьютера.",
    },
)
