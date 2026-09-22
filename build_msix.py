import argparse
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from build_licenses import _app_version, _is_reparse

ROOT = Path(__file__).resolve().parent

NAME_RE = re.compile(r'[A-Za-z0-9.-]{3,50}')

NS = 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'
NS_UAP = 'http://schemas.microsoft.com/appx/manifest/uap/windows10'
NS_UAP3 = 'http://schemas.microsoft.com/appx/manifest/uap/windows10/3'
NS_UAP5 = 'http://schemas.microsoft.com/appx/manifest/uap/windows10/5'
NS_DESKTOP4 = 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/4'
NS_RESCAP = ('http://schemas.microsoft.com/appx/manifest/foundation/'
             'windows10/restrictedcapabilities')


def msix_version(value):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,3}', value):
        raise ValueError('Expected three or four numeric version fields')
    parts = [int(p) for p in value.split('.')]
    parts += [0] * (4 - len(parts))
    if parts[0] == 0 or any(p > 65535 for p in parts) or parts[3] != 0:
        raise ValueError('Store version requires nonzero major, fields '
                         '<=65535, final field zero')
    return '.'.join(map(str, parts))


def build_manifest(identity_name, publisher, publisher_display_name,
                   version):
    ET.register_namespace('', NS)
    ET.register_namespace('uap', NS_UAP)
    ET.register_namespace('uap3', NS_UAP3)
    ET.register_namespace('uap5', NS_UAP5)
    ET.register_namespace('desktop4', NS_DESKTOP4)
    ET.register_namespace('rescap', NS_RESCAP)
    pkg = ET.Element(f'{{{NS}}}Package')
    pkg.set('IgnorableNamespaces', 'uap uap3 uap5 desktop4 rescap')
    ident = ET.SubElement(pkg, 'Identity')
    ident.set('Name', identity_name)
    ident.set('Publisher', publisher)
    ident.set('Version', version)
    ident.set('ProcessorArchitecture', 'x64')
    props = ET.SubElement(pkg, 'Properties')
    ET.SubElement(props, 'DisplayName').text = 'Image Layout Manager'
    ET.SubElement(props, 'PublisherDisplayName').text = \
        publisher_display_name
    ET.SubElement(props, 'Description').text = \
        'Academic figure layout editor'
    ET.SubElement(props, 'Logo').text = 'Assets\\StoreLogo.png'
    res = ET.SubElement(pkg, 'Resources')
    ET.SubElement(res, 'Resource').set('Language', 'en-us')
    ET.SubElement(res, 'Resource').set('Language', 'zh-cn')
    deps = ET.SubElement(pkg, 'Dependencies')
    ET.SubElement(deps, 'TargetDeviceFamily').set('Name', 'Windows.Desktop')
    deps[0].set('MinVersion', '10.0.19041.0')
    deps[0].set('MaxVersionTested', '10.0.26100.0')
    apps = ET.SubElement(pkg, 'Applications')
    app = ET.SubElement(apps, 'Application')
    app.set('Id', 'ImageLayoutManager')
    app.set('Executable', 'App\\ImageLayoutManager.exe')
    app.set('EntryPoint', 'Windows.FullTrustApplication')
    app.set(f'{{{NS_DESKTOP4}}}SupportsMultipleInstances', 'true')
    vis = ET.SubElement(app, f'{{{NS_UAP}}}VisualElements')
    vis.set('DisplayName', 'Image Layout Manager')
    vis.set('Description', 'Academic figure layout editor')
    vis.set('Square150x150Logo', 'Assets\\Square150x150Logo.png')
    vis.set('Square44x44Logo', 'Assets\\Square44x44Logo.png')
    vis.set('BackgroundColor', 'transparent')
    exts = ET.SubElement(app, 'Extensions')
    fta = ET.SubElement(exts, f'{{{NS_UAP3}}}Extension')
    fta.set('Category', 'windows.fileTypeAssociation')
    assoc = ET.SubElement(fta, f'{{{NS_UAP3}}}FileTypeAssociation')
    assoc.set('Name', 'ilmproject')
    assoc.set('Parameters', '"%1"')
    ET.SubElement(assoc, f'{{{NS_UAP}}}DisplayName').text = \
        'Image Layout Manager Project'
    types = ET.SubElement(assoc, f'{{{NS_UAP}}}SupportedFileTypes')
    ET.SubElement(types, f'{{{NS_UAP}}}FileType').text = '.figlayout'
    ET.SubElement(types, f'{{{NS_UAP}}}FileType').text = '.figpack'
    alias_ext = ET.SubElement(exts, f'{{{NS_UAP5}}}Extension')
    alias_ext.set('Category', 'windows.appExecutionAlias')
    alias_ext.set('Executable', 'App\\imagelayout-cli.exe')
    alias_ext.set('EntryPoint', 'Windows.FullTrustApplication')
    alias = ET.SubElement(alias_ext, f'{{{NS_UAP5}}}AppExecutionAlias')
    alias.set(f'{{{NS_DESKTOP4}}}Subsystem', 'console')
    ET.SubElement(alias, f'{{{NS_UAP5}}}ExecutionAlias').set(
        'Alias', 'imagelayout-cli.exe')
    caps = ET.SubElement(pkg, 'Capabilities')
    ET.SubElement(caps, f'{{{NS_RESCAP}}}Capability').set(
        'Name', 'runFullTrust')
    return ET.tostring(pkg, encoding='unicode', xml_declaration=True)


def _contained_file(root: Path, path: Path):
    base = Path(root).resolve()
    node = base
    rel = Path(path).relative_to(base)
    for part in rel.parts:
        node = node / part
        if _is_reparse(node):
            return None
    try:
        resolved = path.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None


def _render_icons(assets_dir: Path) -> None:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtCore import Qt
    app = QGuiApplication.instance() or QGuiApplication([])
    icon_svg = ROOT / 'assets' / 'icon.svg'
    renderer = QSvgRenderer(str(icon_svg))
    if not renderer.isValid():
        raise RuntimeError(f'Cannot render {icon_svg}')
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name, px in (('StoreLogo.png', 50), ('Square44x44Logo.png', 44),
                     ('Square150x150Logo.png', 150)):
        img = QImage(px, px, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        if not img.save(str(assets_dir / name)):
            raise RuntimeError(f'Failed writing {name}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='build_msix.py')
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--identity-name', required=True)
    parser.add_argument('--publisher', required=True)
    parser.add_argument('--publisher-display-name', required=True)
    parser.add_argument('--makeappx', type=Path, default=None)
    ns = parser.parse_args(argv)

    if sys.platform != 'win32' or struct.calcsize('P') != 8 \
            or platform.machine().lower() not in ('amd64', 'x86_64'):
        print('error: MSIX packaging requires a Windows x64 environment')
        return 1

    if not NAME_RE.fullmatch(ns.identity_name):
        print('error: --identity-name must match [A-Za-z0-9.-]{3,50}')
        return 1
    if not ns.publisher or not ns.publisher.startswith('CN='):
        print('error: --publisher must be nonempty and start with CN=')
        return 1
    if not ns.publisher_display_name:
        print('error: --publisher-display-name must be nonempty')
        return 1

    bundle_input = ns.bundle.absolute()
    output_input = ns.output.absolute()
    if any(_is_reparse(p)
           for leaf in (bundle_input, output_input)
           for p in (leaf, *leaf.parents)):
        print('error: bundle/output must not use reparse paths')
        return 1
    bundle, output = bundle_input.resolve(), output_input.resolve()
    if not bundle.is_dir():
        print(f'error: bundle not found: {bundle}')
        return 1
    for a, b in ((bundle, output), (output, bundle)):
        try:
            a.relative_to(b)
            print('error: bundle and output must not contain each other')
            return 1
        except ValueError:
            pass
    if output.exists():
        print(f'error: --output must not exist: {output}')
        return 1
    if ns.makeappx is not None and not ns.makeappx.is_file():
        print(f'error: --makeappx not found: {ns.makeappx}')
        return 1

    if not (bundle / 'ImageLayoutManager.exe').is_file():
        print('error: bundle is missing ImageLayoutManager.exe')
        return 1
    if not (bundle / 'imagelayout-cli.exe').is_file():
        print('error: bundle is missing imagelayout-cli.exe')
        return 1
    manifest_path = bundle / '_internal' / 'licenses' / 'components.json'
    if not manifest_path.is_file():
        print(f'error: bundle is missing {manifest_path}')
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'error: cannot parse license manifest: {exc}')
        return 1
    if not isinstance(manifest, dict):
        print('error: license manifest must be a JSON object')
        return 1
    if manifest.get('source_status') != 'incomplete':
        print('error: license manifest source_status must be incomplete')
        return 1
    if not isinstance(manifest.get('app_version'), str):
        print('error: license manifest app_version missing')
        return 1
    try:
        manifest_version = msix_version(manifest['app_version'])
        repo_version = msix_version(_app_version(ROOT))
    except (RuntimeError, ValueError) as exc:
        print(f'error: {exc}')
        return 1
    if repo_version != manifest_version:
        print(f'error: bundle app_version {manifest_version} does not match '
              f'repo version {repo_version}')
        return 1
    version = manifest_version

    members = []
    for dirpath, dirnames, filenames in os.walk(bundle, followlinks=False):
        current = Path(dirpath)
        for name in dirnames + filenames:
            if _is_reparse(current / name):
                print(f'error: unsafe bundle member: {current / name}')
                return 1
        for fname in filenames:
            src = current / fname
            if _contained_file(bundle, src) is None:
                print(f'error: unsafe bundle member: {src}')
                return 1
            members.append((src, src.relative_to(bundle)))

    layout = output / 'layout'
    app_dir = layout / 'App'
    app_dir.mkdir(parents=True)
    for src, rel in members:
        dest = app_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest, follow_symlinks=False)

    assets_dir = layout / 'Assets'
    try:
        _render_icons(assets_dir)
    except RuntimeError as exc:
        print(f'error: {exc}')
        return 1

    xml_text = build_manifest(ns.identity_name, ns.publisher,
                              ns.publisher_display_name, version)
    (layout / 'AppxManifest.xml').write_text(xml_text, encoding='utf-8')

    if ns.makeappx is None:
        print('warning: --makeappx not provided; wrote layout only, '
              'no .msix produced')
        print(f'Layout: {layout}')
        return 0
    msix_path = output / f'ImageLayoutManager-{version}-x64.msix'
    subprocess.run([str(ns.makeappx), 'pack', '/d', str(layout),
                    '/p', str(msix_path)], check=True)
    print(f'Unsigned engineering candidate: {msix_path}')
    print('NOT signed, NOT release-cleared, NOT installed — '
          'license source_status=incomplete remains outstanding.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
