import re
import sys
import subprocess
import textwrap
import shutil
from pathlib import Path


# Common Inno Setup 6 install locations — scan C–F drives to cover non-default installs
_ISCC_CANDIDATES = [
    rf"{drive}\{folder}\Inno Setup 6\ISCC.exe"
    for drive in [r"C:", r"D:", r"E:", r"F:"]
    for folder in [r"Program Files (x86)", r"Program Files"]
]

_WINGET_ID = "JRSoftware.InnoSetup"


def find_iscc() -> Path | None:
    """Return the path to ISCC.exe, or None if Inno Setup is not installed."""
    for candidate in _ISCC_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return p
    found = shutil.which("ISCC")
    return Path(found) if found else None


def install_inno_via_winget() -> bool:
    """Try to install Inno Setup 6 silently via winget. Return True on success."""
    if shutil.which("winget") is None:
        return False
    print("Installing Inno Setup 6 via winget...")
    result = subprocess.run(
        ["winget", "install", "--id", _WINGET_ID, "--silent", "--accept-package-agreements", "--accept-source-agreements"],
        capture_output=False,
    )
    return result.returncode == 0


def ensure_iscc() -> Path | None:
    """Return ISCC.exe path, installing Inno Setup automatically if needed."""
    iscc = find_iscc()
    if iscc:
        return iscc

    print("Inno Setup 6 (ISCC.exe) was not found.")

    if shutil.which("winget"):
        answer = input("Install it now via winget? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            if install_inno_via_winget():
                # winget installs to the standard path; search again
                iscc = find_iscc()
                if iscc:
                    print(f"Inno Setup installed: {iscc}")
                    return iscc
                print("Installation seemed to succeed but ISCC.exe still not found.")
                print("Try re-running this script.")
            else:
                print("winget installation failed.")
        else:
            print("Skipping automatic install.")
    else:
        print("winget is not available on this machine.")

    print()
    print("Please install Inno Setup 6 manually:")
    print("  https://jrsoftware.org/isdl.php")
    print("Then re-run this script.")
    return None


def main() -> int:
    """Build a Windows installer using PyInstaller (--onedir) + Inno Setup.

    Workflow
    --------
    1. PyInstaller with --onedir produces dist/ImageLayoutManager/ (a folder).
       Because files are already extracted, the app launches instantly — no
       5-10 s extraction delay like --onefile.
    2. Inno Setup compiles the folder into a single Setup exe that users install
       once.  After install the app opens instantly on every subsequent launch.

    Prerequisites
    -------------
    - pip install pyinstaller
    - Inno Setup 6  https://jrsoftware.org/isdl.php
    """

    if sys.platform != "win32":
        print("This script is intended for Windows only.")
        print(f"Current platform: {sys.platform}")
        return 1

    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except Exception as e:
        print("PyInstaller is not installed or failed to import.")
        print("Install it with: pip install pyinstaller")
        print(f"Import error: {e}")
        return 1

    iscc = ensure_iscc()
    if iscc is None:
        return 1

    project_root = Path(__file__).resolve().parent
    entry = project_root / "main.py"

    if not entry.exists():
        print(f"Entry file not found: {entry}")
        return 1

    src_path = str(project_root / "src")
    assets_dir = project_root / "assets"
    icon_path = assets_dir / "icon.ico"

    # ------------------------------------------------------------------ #
    # Step 1 – PyInstaller --onedir                                        #
    # ------------------------------------------------------------------ #

    used_qt_modules = [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtSvg",
    ]

    unused_qt_modules = [
        "PyQt6.QtNetwork",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebChannel",
        "PyQt6.Qt3DCore",
        "PyQt6.Qt3DRender",
        "PyQt6.Qt3DInput",
        "PyQt6.Qt3DLogic",
        "PyQt6.Qt3DAnimation",
        "PyQt6.Qt3DExtras",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtLocation",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtXml",
        "numpy",
        # Not used by this app — pulled in from conda env, ships a ~60 MB ffmpeg binary
        "imageio",
        "imageio_ffmpeg",
    ]

    args = [
        "--noconfirm",
        "--clean",
        # --onedir: all files stay extracted in dist/ImageLayoutManager/
        # No runtime extraction on launch → instant startup.
        "--onedir",
        "--windowed",
        "--name=ImageLayoutManager",
        f"--paths={src_path}",
        "--noupx",
    ]

    if icon_path.exists():
        args.append(f"--icon={icon_path}")

    if assets_dir.exists():
        args.append(f"--add-data={assets_dir};assets")

    for mod in used_qt_modules:
        args.append(f"--collect-submodules={mod}")

    # Ensure Qt6 C++ DLLs, platform plugins (e.g., qwindows.dll), styles, and data files are bundled.
    args.append("--collect-binaries=PyQt6")
    args.append("--collect-data=PyQt6")
    args.append("--hidden-import=PyQt6.sip")
    args.append("--hidden-import=shiboken6")

    for mod in unused_qt_modules:
        args.append(f"--exclude-module={mod}")

    args.append(str(entry))

    print("Running PyInstaller with args:")
    for a in args:
        print(f"  {a}")

    pyinstaller_run(args)

    dist_dir = project_root / "dist" / "ImageLayoutManager"
    if not dist_dir.exists():
        print("PyInstaller finished but output directory not found:")
        print(f"  {dist_dir}")
        return 2

    print(f"PyInstaller OK: {dist_dir}")

    # ------------------------------------------------------------------ #
    # Step 1b – Remove DLLs that shadow incompatible system copies         #
    # ------------------------------------------------------------------ #
    # PyInstaller's dependency scanner picks up DLLs from the conda env
    # that shadow the system copies with ABI-incompatible versions,
    # causing Qt6Core.dll to fail with ERROR_PROC_NOT_FOUND (WinError 127).
    #
    # Offenders:
    #  - icuuc.dll / icudt*.dll / icuin.dll — PyInstaller finds a full ICU
    #    (2.7 MB) from conda, but the PyQt6-Qt6 pip wheel was built against
    #    Windows' built-in ICU stub (~37 KB in System32).  ABI mismatch.
    #  - ucrtbase.dll / api-ms-win-* — can be from an older Windows SDK
    #    than what Qt6 was compiled against.  Qt6 requires Win10+ which
    #    always ships a current UCRT and resolves api-ms-win-* via the
    #    API-set schema.
    #
    # Fix: remove them so the OS uses the correct system copies.

    internal_dir = dist_dir / "_internal"

    removed = 0
    for p in internal_dir.iterdir():
        name_lower = p.name.lower()
        if (
            name_lower.startswith("api-ms-win-")
            or name_lower == "ucrtbase.dll"
            or name_lower.startswith("icu")  # icuuc.dll, icudt*.dll, icuin.dll
        ):
            p.unlink()
            print(f"  Removed: {p.name}")
            removed += 1
    print(f"Removed {removed} rogue/stale DLL(s) from _internal.")


    # ------------------------------------------------------------------ #
    # Step 2 – Generate Inno Setup script and compile                     #
    # ------------------------------------------------------------------ #

    # Read version from src/version.py (APP_VERSION = "x.y.z")
    version_py = project_root / "src" / "version.py"
    app_version = "1.0.0"
    if version_py.exists():
        match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', version_py.read_text(encoding="utf-8"))
        if match:
            app_version = match.group(1)
    print(f"App version: {app_version}")

    iss_path = project_root / "build" / "installer.iss"
    iss_path.parent.mkdir(parents=True, exist_ok=True)

    icon_iss = str(icon_path) if icon_path.exists() else ""
    icon_lines = (
        f'SetupIconFile={icon_iss}\n'
        f'UninstallDisplayIcon={{app}}\\ImageLayoutManager.exe'
        if icon_iss else ""
    )

    iss_content = textwrap.dedent(f"""\
        ; Inno Setup script — auto-generated by build_installer_windows.py
        ; Do not edit by hand; re-run the build script to regenerate.

        [Setup]
        AppName=ImageLayoutManager
        AppVersion={app_version}
        AppPublisher=Meow
        AppId={{{{8F3A1C2D-4E5B-6F7A-8B9C-0D1E2F3A4B5C}}}}
        DefaultDirName={{autopf}}\\ImageLayoutManager
        DefaultGroupName=ImageLayoutManager
        OutputDir={project_root / "dist"}
        OutputBaseFilename=ImageLayoutManager_Setup
        Compression=lzma2/ultra64
        SolidCompression=yes
        PrivilegesRequired=admin
        ArchitecturesAllowed=x64compatible
        ArchitecturesInstallIn64BitMode=x64compatible
        ChangesAssociations=yes
        ShowLanguageDialog=yes
        {icon_lines}

        [Languages]
        Name: "english";    MessagesFile: "compiler:Default.isl"
        Name: "french";     MessagesFile: "compiler:Languages\\French.isl"
        Name: "german";     MessagesFile: "compiler:Languages\\German.isl"
        Name: "spanish";    MessagesFile: "compiler:Languages\\Spanish.isl"
        Name: "italian";    MessagesFile: "compiler:Languages\\Italian.isl"
        Name: "japanese";   MessagesFile: "compiler:Languages\\Japanese.isl"
        Name: "korean";     MessagesFile: "compiler:Languages\\Korean.isl"
        Name: "chinesesimplified";  MessagesFile: "compiler:Languages\\ChineseSimplified.isl"
        Name: "chinesetraditional"; MessagesFile: "compiler:Languages\\ChineseTraditional.isl"
        Name: "portuguese"; MessagesFile: "compiler:Languages\\BrazilianPortuguese.isl"
        Name: "russian";    MessagesFile: "compiler:Languages\\Russian.isl"

        [CustomMessages]
        english.AssocDescription=Associate .figlayout and .figpack files with ImageLayoutManager
        english.AssocGroupDescription=File associations:
        chinesesimplified.AssocDescription=将 .figlayout 和 .figpack 文件关联至 ImageLayoutManager
        chinesesimplified.AssocGroupDescription=文件关联：
        chinesetraditional.AssocDescription=將 .figlayout 和 .figpack 檔案關聯至 ImageLayoutManager
        chinesetraditional.AssocGroupDescription=檔案關聯：

        [Tasks]
        Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"
        Name: "assoc"; Description: "{{cm:AssocDescription}}"; GroupDescription: "{{cm:AssocGroupDescription}}"; Flags: checkedonce

        [Files]
        Source: "{dist_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

        [Icons]
        Name: "{{group}}\\ImageLayoutManager"; Filename: "{{app}}\\ImageLayoutManager.exe"
        Name: "{{group}}\\Uninstall ImageLayoutManager"; Filename: "{{uninstallexe}}"
        Name: "{{userdesktop}}\\ImageLayoutManager"; Filename: "{{app}}\\ImageLayoutManager.exe"; Tasks: desktopicon

        [Registry]
        ; .figlayout extension → ProgID
        Root: HKCR; Subkey: ".figlayout";                                          ValueType: string; ValueName: "";                ValueData: "FigLayout.Document"; Flags: uninsdeletevalue; Tasks: assoc
        Root: HKCR; Subkey: ".figlayout";                                          ValueType: string; ValueName: "Content Type";    ValueData: "application/x-figlayout"; Tasks: assoc

        ; .figlayout ProgID
        Root: HKCR; Subkey: "FigLayout.Document";                                  ValueType: string; ValueName: "";                ValueData: "Academic Figure Layout File"; Flags: uninsdeletekey; Tasks: assoc
        Root: HKCR; Subkey: "FigLayout.Document\\DefaultIcon";                     ValueType: string; ValueName: "";                ValueData: \"{{app}}\\ImageLayoutManager.exe,0\"; Tasks: assoc
        Root: HKCR; Subkey: "FigLayout.Document\\shell\\open";                     ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Academic Figure Layout"; Tasks: assoc
        Root: HKCR; Subkey: "FigLayout.Document\\shell\\open\\command";            ValueType: string; ValueName: "";                ValueData: \"\"\"{{app}}\\ImageLayoutManager.exe\"\" \"\"%1\"\"\"; Tasks: assoc

        ; .figpack extension → ProgID
        Root: HKCR; Subkey: ".figpack";                                            ValueType: string; ValueName: "";                ValueData: "FigPack.Document"; Flags: uninsdeletevalue; Tasks: assoc
        Root: HKCR; Subkey: ".figpack";                                            ValueType: string; ValueName: "Content Type";    ValueData: "application/x-figpack"; Tasks: assoc

        ; .figpack ProgID
        Root: HKCR; Subkey: "FigPack.Document";                                    ValueType: string; ValueName: "";                ValueData: "Academic Figure Bundle"; Flags: uninsdeletekey; Tasks: assoc
        ; NOTE: PyInstaller --onedir places extra files under _internal\, so the
        ; icon lives at {{app}}\\_internal\\assets\\icon_figpack.ico, not {{app}}\\assets\\.
        Root: HKCR; Subkey: "FigPack.Document\\DefaultIcon";                       ValueType: string; ValueName: "";                ValueData: \"{{app}}\\_internal\\assets\\icon_figpack.ico\"; Tasks: assoc
        Root: HKCR; Subkey: "FigPack.Document\\shell\\open";                       ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Academic Figure Layout"; Tasks: assoc
        Root: HKCR; Subkey: "FigPack.Document\\shell\\open\\command";              ValueType: string; ValueName: "";                ValueData: \"\"\"{{app}}\\ImageLayoutManager.exe\"\" \"\"%1\"\"\"; Tasks: assoc

        ; App Capabilities (powers the "Open with" dialog and Default Programs)
        Root: HKLM; Subkey: "SOFTWARE\\ImageLayoutManager";                        ValueType: string; ValueName: "";                ValueData: "Academic Figure Layout"; Flags: uninsdeletekey
        Root: HKLM; Subkey: "SOFTWARE\\ImageLayoutManager\\Capabilities";          ValueType: string; ValueName: "ApplicationName"; ValueData: "Academic Figure Layout"
        Root: HKLM; Subkey: "SOFTWARE\\ImageLayoutManager\\Capabilities";          ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Multi-panel academic figure editor"
        Root: HKLM; Subkey: "SOFTWARE\\ImageLayoutManager\\Capabilities\\FileAssociations"; ValueType: string; ValueName: ".figlayout"; ValueData: "FigLayout.Document"
        Root: HKLM; Subkey: "SOFTWARE\\ImageLayoutManager\\Capabilities\\FileAssociations"; ValueType: string; ValueName: ".figpack";   ValueData: "FigPack.Document"
        Root: HKLM; Subkey: "SOFTWARE\\RegisteredApplications";                    ValueType: string; ValueName: "ImageLayoutManager"; ValueData: "SOFTWARE\\ImageLayoutManager\\Capabilities"; Flags: uninsdeletevalue

        [Run]
        Filename: "{{app}}\\ImageLayoutManager.exe"; Description: "{{cm:LaunchProgram,ImageLayoutManager}}"; Flags: nowait postinstall skipifsilent

        [Code]
        // Notify Windows Shell that file associations changed so Explorer
        // refreshes icons and context menus without requiring a reboot.
        procedure SHChangeNotify(wEventId: Integer; uFlags: Cardinal; dwItem1: Longword; dwItem2: Longword);
          external 'SHChangeNotify@shell32.dll stdcall';

        procedure CurStepChanged(CurStep: TSetupStep);
        begin
          if CurStep = ssPostInstall then
            // SHCNE_ASSOCCHANGED = $08000000, SHCNF_DWORD = $1000 (items are DWORDs, not PIDLs)
            SHChangeNotify($08000000, $1000, 0, 0);
        end;
    """)

    iss_path.write_text(iss_content, encoding="utf-8")
    print(f"Inno Setup script written: {iss_path}")

    print(f"Running Inno Setup compiler: {iscc}")
    result = subprocess.run([str(iscc), str(iss_path)], capture_output=False)

    if result.returncode != 0:
        print(f"Inno Setup compilation failed (exit code {result.returncode}).")
        return result.returncode

    setup_exe = project_root / "dist" / "ImageLayoutManager_Setup.exe"
    if setup_exe.exists():
        print(f"\nBuild OK: {setup_exe}")
        return 0

    print("Inno Setup finished but installer not found at expected path:")
    print(f"  {setup_exe}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
