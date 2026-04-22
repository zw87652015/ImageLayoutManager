import os
import sys
import subprocess
import shutil
from pathlib import Path

def run(cmd, check=True):
    print(f"Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)

def main():
    if sys.platform != "darwin":
        print("This script must be run on macOS.")
        return 1

    project_root = Path(__file__).resolve().parent
    dist_dir = project_root / "dist"
    app_name = "ImageLayoutManager"
    app_path = dist_dir / f"{app_name}.app"
    dmg_name = f"{app_name}.dmg"
    dmg_path = dist_dir / dmg_name
    
    # 1. Check if the app exists
    if not app_path.exists():
        print(f"Error: {app_path} not found. Run 'python build_onefile_macos.py' first.")
        return 1

    # 2. Ad-hoc Sign the app (CRITICAL for fixing the 'Broken' error)
    print(f"Applying ad-hoc signature to {app_name}...")
    try:
        run(["codesign", "--deep", "--force", "--sign", "-", str(app_path)])
    except subprocess.CalledProcessError as e:
        print(f"Warning: codesign failed: {e.stderr}")

    # 3. Create a temporary staging area
    staging_dir = dist_dir / "dmg_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()

    print(f"Preparing staging area at {staging_dir}...")
    shutil.copytree(app_path, staging_dir / f"{app_name}.app", symlinks=True)
    
    # Create symlink to /Applications
    os.symlink("/Applications", staging_dir / "Applications")

    # 4. Create the DMG
    if dmg_path.exists():
        dmg_path.unlink()

    temp_dmg = dist_dir / "temp.dmg"
    if temp_dmg.exists():
        temp_dmg.unlink()

    print("Creating Disk Image...")
    try:
        # Create a raw DMG from the staging folder
        run([
            "hdiutil", "create",
            "-volname", app_name,
            "-srcfolder", str(staging_dir),
            "-ov", "-format", "UDRW",
            str(temp_dmg)
        ])

        # Convert to a compressed, read-only DMG (Standard for distribution)
        print("Compressing DMG...")
        run([
            "hdiutil", "convert", str(temp_dmg),
            "-format", "UDZO",
            "-o", str(dmg_path)
        ])
        
        print(f"\nSuccessfully created: {dmg_path}")
    finally:
        # Cleanup
        if temp_dmg.exists():
            temp_dmg.unlink()
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

    return 0

if __name__ == "__main__":
    sys.exit(main())
