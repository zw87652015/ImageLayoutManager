import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path, PurePosixPath

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent

FALLBACKS = {
    ('rapidocr', '3.9.1'): 'rapidocr-3.9.1-LICENSE.txt',
    ('antlr4-python3-runtime', '4.9.3'): 'antlr4-python3-runtime-4.9.3-LICENSE.txt',
    ('flatbuffers', '25.12.19'): 'flatbuffers-25.12.19-LICENSE.txt',
}

PENDING = [
    'Verify every native library and asset in the final frozen artifact, '
    'including Qt, MuPDF, GEOS, OpenCV and Python runtime libraries.',
    'Provide and verify the complete version-matched dependency/native-library '
    'corresponding source and build information.',
    'Publish matching source access with the binary; no source release has '
    'been published by this preparation step.',
]

SCOPE = ('declared dependency closure and PyInstaller bootloader; '
         'not a final-binary audit')

TOP_PARAGRAPH = ('License notices and application source. This preparation is '
                 'not release clearance. Dependency/native-library source '
                 'verification and publication remain outstanding.')

VENDORED = {
    'GPL-3.0.txt', 'LGPL-3.0.txt', 'AGPL-3.0.txt',
    'rapidocr-3.9.1-LICENSE.txt',
    'antlr4-python3-runtime-4.9.3-LICENSE.txt',
    'flatbuffers-25.12.19-LICENSE.txt',
    'PaddleOCR-3.7.0-LICENSE.txt',
}

VERSION_RE = re.compile(r'[0-9]+(?:\.[0-9]+){1,3}')

ROOT_FILES = [
    'main.py', 'cli_main.py', 'requirements.txt', 'environment.yml',
    'LICENSE', 'NOTICE', 'build_licenses.py', 'build_onefile.py',
    'build_installer_windows.py', 'build_onefile_macos.py',
    'build_dmg_macos.py', 'build_icns_figpack.py', 'verify_licenses.py',
    'build_msix.py', 'verify_msix.py', 'audit_release.py',
    'verify_release_audit.py', 'SOURCES.md', 'build_source_index.py',
    'verify_source_index.py',
]

SOURCE_TREES = {'src': {'.py'}, 'assets': None, 'docs': None, 'licenses': None}
SECRET_SUFFIXES = {'.env', '.pem', '.key', '.pfx', '.p12', '.crt', '.cer',
                   '.keystore', '.jks', '.ppk', '.kdbx', '.asc'}
COMPILED_SUFFIXES = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.dylib',
                     '.o', '.a', '.class', '.wasm'}
TEXT_SUFFIXES = {'', '.txt', '.md', '.rst', '.text', '.notice', '.html',
                 '.htm'}
NOTICE_NAME_RE = re.compile(r'license|licence|copying|copyright|notice',
                            re.IGNORECASE)


def _dist_name(dist):
    return canonicalize_name(dist.metadata['Name'])


def dependency_distributions(requirements_path: Path,
                             extra_requirements=()):
    env = default_environment()
    reqs = {}
    extras_of = {}
    root_lines = requirements_path.read_text(
        encoding='utf-8').splitlines()
    for raw in [*root_lines, *extra_requirements, 'PyInstaller']:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate({**env, 'extra': ''}):
            continue
        name = canonicalize_name(req.name)
        reqs.setdefault(name, []).append(req)
        extras_of.setdefault(name, set()).update(req.extras)
    queue = list(extras_of)
    processed = set()
    while queue:
        name = canonicalize_name(queue.pop(0))
        key = (name, frozenset(extras_of[name]))
        if key in processed:
            continue
        processed.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            raise RuntimeError(
                f'Required distribution not installed: {name}')
        for req in reqs.get(name, []):
            if req.specifier and not req.specifier.contains(
                    dist.version, prereleases=True):
                raise RuntimeError(
                    f'Installed {name}=={dist.version} does not satisfy {req}')
        for dep_raw in dist.metadata.get_all('Requires-Dist') or []:
            dep = Requirement(dep_raw)
            dep_name = canonicalize_name(dep.name)
            if dep.marker and not any(
                    dep.marker.evaluate({**env, 'extra': e})
                    for e in ({''} | extras_of[name])):
                continue
            reqs.setdefault(dep_name, []).append(dep)
            extras_of.setdefault(dep_name, set()).update(dep.extras)
            queue.append(dep_name)
    selected = []
    for name in sorted(extras_of):
        dist = metadata.distribution(name)
        for req in reqs.get(name, []):
            if req.specifier and not req.specifier.contains(
                    dist.version, prereleases=True):
                raise RuntimeError(
                    f'Installed {name}=={dist.version} does not satisfy {req}')
        selected.append(dist)
    selected.sort(key=_dist_name)
    return selected


def _is_build_tool(dist):
    return _dist_name(dist) == 'pyinstaller'


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    junction = getattr(path, 'is_junction', None)
    return bool(junction and junction())


def _contained_regular_file(root: Path, path):
    if not isinstance(path, (str, os.PathLike)):
        return None
    base = Path(root).resolve()
    text = str(path).replace('\\', '/')
    rel = PurePosixPath(text)
    if not text or rel.is_absolute() or Path(path).is_absolute() or '..' in rel.parts or any(':' in part for part in rel.parts):
        return None
    node = base
    for part in rel.parts:
        node = node / part
        if _is_reparse(node):
            return None
    try:
        resolved = node.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() and not _is_reparse(resolved) else None


def _record_license_files(dist):
    dist_root = Path(dist.locate_file('')).resolve()
    found = []
    for f in dist.files or []:
        rel = PurePosixPath(str(f).replace('\\', '/'))
        if rel.is_absolute() or '..' in rel.parts:
            continue
        src = _contained_regular_file(dist_root, Path(*rel.parts))
        if src is None:
            continue
        lower = [p.lower() for p in rel.parts]
        dir_hit = any(
            part == 'licenses' and i > 0 and lower[i - 1].endswith('.dist-info')
            for i, part in enumerate(lower[:-1]))
        base = rel.name
        suffix = rel.suffix.lower()
        name_hit = bool(NOTICE_NAME_RE.search(base)) and \
            suffix in TEXT_SUFFIXES
        if not (dir_hit or name_hit):
            continue
        if suffix in {'.py', '.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe'}:
            continue
        found.append((rel, src))
    return found


def _verified_fallback(name, version, license_dir):
    target = FALLBACKS.get((name, version))
    if target is None:
        return None
    origins_path = license_dir / 'origins.json'
    if not origins_path.is_file():
        return None
    origins = json.loads(origins_path.read_text(encoding='utf-8'))
    entry = next((o for o in origins if o.get('file') == target), None)
    if entry is None:
        return None
    data = (license_dir / target).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        return None
    return data


def _verify_vendored(license_dir: Path):
    origins_path = license_dir / 'origins.json'
    if not origins_path.is_file():
        raise RuntimeError(f'Missing {origins_path}')
    try:
        origins = json.loads(origins_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError('Cannot read vendored license origins') from exc
    if not isinstance(origins, list):
        raise RuntimeError('Vendored license origins must be a list')
    by_file = {}
    for entry in origins:
        if not isinstance(entry, dict):
            raise RuntimeError('Invalid vendored license origin')
        name = entry.get('file')
        if not isinstance(name, str) or not isinstance(entry.get('source'), str) or not entry['source'].strip() or not isinstance(entry.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise RuntimeError('Invalid vendored license origin fields')
        if name in by_file:
            raise RuntimeError(f'Duplicate vendored license origin: {name}')
        by_file[name] = entry
    if not VENDORED.issubset(by_file):
        raise RuntimeError('Vendored license missing mandatory origins entries')
    for name, entry in by_file.items():
        p = _contained_regular_file(license_dir, name)
        if p is None:
            raise RuntimeError(f'Vendored license missing or unsafe: {name}')
        if hashlib.sha256(p.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError(f'Vendored license hash mismatch: {name}')
    checks = {
        'GPL-3.0.txt': ('GNU GENERAL PUBLIC LICENSE', 'Version 3',
                        'END OF TERMS AND CONDITIONS'),
        'AGPL-3.0.txt': ('GNU AFFERO GENERAL PUBLIC LICENSE',
                         'END OF TERMS AND CONDITIONS'),
        'LGPL-3.0.txt': ('GNU LESSER GENERAL PUBLIC LICENSE',),
    }
    for name, markers in checks.items():
        text = (license_dir / name).read_text(encoding='utf-8',
                                              errors='replace')
        for marker in markers:
            if marker not in text:
                raise RuntimeError(
                    f'Vendored license incomplete: {name} lacks {marker!r}')


def _native_notice_components(license_dir: Path):
    origins = json.loads(
        (license_dir / 'origins.json').read_text(encoding='utf-8'))
    groups = {}
    verified_bindings = set()
    for entry in origins:
        component = entry.get('component')
        if component is None:
            continue
        version = entry.get('component_version')
        platform_name = entry.get('platform')
        if not isinstance(component, str) or not component.strip() \
                or not isinstance(version, str) or not version.strip():
            raise RuntimeError(
                'Invalid native notice component fields')
        if platform_name is not None and platform_name not in (
                'win32', 'darwin', 'linux'):
            raise RuntimeError(
                f'Invalid native notice platform: {platform_name}')
        if platform_name is not None and platform_name != sys.platform:
            continue
        binding = entry.get('binding')
        if not isinstance(binding, dict):
            raise RuntimeError(
                f'Native notice requires binding: {entry.get("file")}')
        binding_key = json.dumps(binding, sort_keys=True)
        if binding_key in verified_bindings:
            groups.setdefault((component, version), []).append(entry)
            continue
        kind = binding.get('kind')
        if kind == 'distribution':
            dist_name = binding.get('name')
            want = binding.get('version')
            if not isinstance(dist_name, str) or not dist_name.strip() \
                    or not isinstance(want, str) or not want.strip():
                raise RuntimeError('Invalid distribution binding fields')
            try:
                installed = metadata.distribution(dist_name).version
            except metadata.PackageNotFoundError as exc:
                raise RuntimeError(
                    f'Native notice distribution missing: {dist_name}'
                ) from exc
            if installed != want:
                raise RuntimeError(
                    f'Native notice distribution version mismatch: '
                    f'{dist_name} {installed} != {want}')
        elif kind == 'runtime_file':
            rel = binding.get('path')
            digest = binding.get('sha256')
            if not isinstance(rel, str) or not rel.strip() \
                    or not isinstance(digest, str) \
                    or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise RuntimeError('Invalid runtime_file binding fields')
            target = _contained_regular_file(Path(sys.prefix), rel)
            if target is None or hashlib.sha256(
                    target.read_bytes()).hexdigest() != digest:
                raise RuntimeError(
                    f'Native notice runtime file mismatch: {rel}')
        else:
            raise RuntimeError(f'Invalid native notice binding: {kind}')
        verified_bindings.add(binding_key)
        groups.setdefault((component, version), []).append(entry)
    components = []
    for component, version in sorted(groups):
        entries = groups[(component, version)]
        components.append({
            'name': component,
            'version': version,
            'role': 'native upstream notices; may include optional '
                    'source components',
            'license_expression': None,
            'license_files': sorted('licenses/' + e['file']
                                    for e in entries),
            'project_urls': sorted({e['source'] for e in entries}),
        })
    return components


def _app_version(project_root):
    version_py = project_root / 'src' / 'version.py'
    text = version_py.read_text(encoding='utf-8') if version_py.exists() else ''
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not m or not VERSION_RE.fullmatch(m.group(1)):
        raise RuntimeError(
            f'Cannot determine filename-safe APP_VERSION from {version_py}')
    return m.group(1)


def application_source_files(project_root: Path):
    root = Path(project_root).resolve()
    files = []
    for name in ROOT_FILES:
        p = _contained_regular_file(root, name)
        if p is not None:
            files.append(p)
    for tree, allowed in SOURCE_TREES.items():
        base = root / tree
        if not base.is_dir() or _is_reparse(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base,
                                                    followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [d for d in sorted(dirnames)
                           if not d.startswith('.')
                           and d != '__pycache__'
                           and not _is_reparse(current / d)]
            for fname in sorted(filenames):
                p = current / fname
                rel = p.relative_to(base)
                parts = rel.parts
                if any(part.startswith('.') or part == '__pycache__'
                       for part in parts):
                    continue
                suffix = p.suffix.lower()
                if suffix in SECRET_SUFFIXES or p.name.lower() == '.env':
                    continue
                if allowed is not None:
                    if suffix not in allowed:
                        continue
                elif tree in ('docs', 'src') and suffix in COMPILED_SUFFIXES:
                    continue
                if suffix in COMPILED_SUFFIXES and tree != 'assets':
                    continue
                if _contained_regular_file(root, p.relative_to(root)) \
                        is not None:
                    files.append(p)
    seen = set()
    out = []
    for p in files:
        rp = p.resolve()
        try:
            rp.relative_to(root)
        except ValueError:
            continue
        if rp not in seen:
            seen.add(rp)
            out.append(rp)
    return out


def create_application_source(project_root: Path, license_dir: Path) -> Path:
    version = _app_version(project_root)
    dest = license_dir / f'ImageLayoutManager-{version}-application-source.zip'
    root = Path(project_root).resolve()
    entries = []
    for p in application_source_files(root):
        entries.append((p, p.relative_to(root).as_posix()))
    versions_file = license_dir / 'installed-versions.txt'
    if versions_file.is_file():
        entries.append((versions_file, 'installed-versions.txt'))
    entries.sort(key=lambda e: e[1])
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for src, arcname in entries:
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, src.read_bytes())
    return dest


def _license_expression(dist):
    expr = dist.metadata.get('License-Expression')
    if expr:
        return expr
    short = dist.metadata.get('License')
    if short and len(short) < 200:
        return short
    return None


def prepare_licenses(project_root: Path = ROOT,
                     output: Path | None = None,
                     additional_requirements=()) -> Path:
    root = Path(project_root).resolve()
    license_dir = root / 'licenses'
    _verify_vendored(license_dir)
    for top in ('LICENSE', 'NOTICE', 'SOURCES.md'):
        if not (root / top).is_file():
            raise RuntimeError(f'Missing required root file: {top}')
    if output is None:
        build = root / 'build'
        build.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='licenses-', dir=build))
    else:
        staging = Path(output).resolve()
        if staging == root:
            raise RuntimeError(f'--output must not be {root}')
        for tree in SOURCE_TREES:
            try:
                staging.relative_to(root / tree)
            except ValueError:
                continue
            raise RuntimeError(
                f'--output must not be inside {root / tree}')
        if staging.exists() and any(staging.iterdir()):
            raise RuntimeError(
                f'--output must be a new or empty directory: {staging}')
        staging.mkdir(parents=True, exist_ok=True)
    staging = staging.resolve()

    components_dir = staging / 'components'
    components_dir.mkdir(parents=True, exist_ok=True)

    dists = dependency_distributions(root / 'requirements.txt',
                                     extra_requirements=additional_requirements)
    components = []
    installed_lines = []
    for dist in dists:
        name = _dist_name(dist)
        version = dist.version
        installed_lines.append(f'{name}=={version}')
        dest_dir = components_dir / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        meta_text = dist.read_text('METADATA') \
            or dist.read_text('PKG-INFO') or str(dist.metadata)
        (dest_dir / 'METADATA.txt').write_bytes(meta_text.encode('utf-8'))
        metadata_rel = f'components/{name}/METADATA.txt'
        rel_dests = [metadata_rel]
        for rel, src in _record_license_files(dist):
            target = dest_dir / Path(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read_bytes())
            rel_dests.append(f'components/{name}/{rel.as_posix()}')
        if name == 'pymupdf':
            agpl = license_dir / 'AGPL-3.0.txt'
            if agpl.is_file():
                target = dest_dir / 'AGPL-3.0.txt'
                target.write_bytes(agpl.read_bytes())
                rel_dests.append(f'components/{name}/AGPL-3.0.txt')
        notice_files = [r for r in rel_dests if r != metadata_rel]
        if not notice_files:
            fallback = _verified_fallback(name, version, license_dir)
            if fallback is None:
                raise RuntimeError(
                    f'No license/notice files found for {name}=={version} '
                    'and no verified fallback is available.')
            target = dest_dir / FALLBACKS[(name, version)]
            target.write_bytes(fallback)
            rel_dests.append(
                f'components/{name}/{FALLBACKS[(name, version)]}')
        urls = []
        for raw in dist.metadata.get_all('Project-URL') or []:
            urls.append(raw.split(',', 1)[-1].strip())
        entry = {
            'name': name,
            'version': version,
            'license_expression': _license_expression(dist),
            'license_files': sorted(set(rel_dests)),
            'project_urls': urls,
        }
        if _is_build_tool(dist):
            entry['role'] = 'build tool'
        components.append(entry)
    components.extend(_native_notice_components(license_dir))

    python_license = None
    for base in (Path(sys.base_prefix), Path(sys.prefix)):
        for cand in ('LICENSE_PYTHON.txt', 'LICENSE.txt'):
            p = base / cand
            if p.is_file():
                python_license = p
                break
        if python_license:
            break
    if python_license is None:
        raise RuntimeError('Python interpreter license file not found.')
    py_dir = staging / 'python'
    py_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_license, py_dir / python_license.name)

    for top in ('LICENSE', 'NOTICE', 'SOURCES.md'):
        src = root / top
        if src.is_file():
            shutil.copy2(src, staging / top)
    if license_dir.is_dir():
        shutil.copytree(license_dir, staging / 'licenses',
                        dirs_exist_ok=False)

    installed_lines.sort()
    versions_path = staging / 'installed-versions.txt'
    versions_path.write_text('\n'.join(installed_lines) + '\n',
                             encoding='utf-8')

    zip_path = create_application_source(root, staging)
    zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    manifest = {
        'schema_version': 1,
        'app_version': _app_version(root),
        'python_version': sys.version.split()[0],
        'scope': SCOPE,
        'source_status': 'incomplete',
        'application_source_archive': zip_path.name,
        'application_source_sha256': zip_hash,
        'components': components,
        'pending': list(PENDING),
    }
    (staging / 'components.json').write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8')

    lines = ['<!DOCTYPE html>', '<html><head><meta charset="utf-8">',
             f'<title>{html.escape("Licenses and source")}</title></head>',
             '<body>',
             f'<p>{html.escape(TOP_PARAGRAPH)}</p>',
             '<ul>',
             '<li><a href="LICENSE">LICENSE</a></li>',
             '<li><a href="NOTICE">NOTICE</a></li>',
             '<li><a href="SOURCES.md">SOURCES.md</a></li>',
             f'<li><a href="{html.escape(zip_path.name)}">'
             f'{html.escape(zip_path.name)}</a> '
             f'(sha256 {zip_hash})</li>',
             '<li><a href="installed-versions.txt">installed-versions.txt'
             '</a></li>',
             '<li><a href="components.json">components.json</a></li>',
             '</ul>', '<h2>Components</h2>', '<ul>']
    for comp in components:
        label = f"{comp['name']} {comp['version']}"
        role = f" ({comp['role']})" if comp.get('role') else ''
        lines.append(f'<li>{html.escape(label + role)}<ul>')
        for rel in comp['license_files']:
            lines.append(
                f'<li><a href="{html.escape(rel)}">'
                f'{html.escape(rel)}</a></li>')
        lines.append('</ul></li>')
    lines += ['</ul>', '<h2>Pending</h2>', '<ul>']
    for item in PENDING:
        lines.append(f'<li>{html.escape(item)}</li>')
    lines += ['</ul>', '</body></html>', '']
    (staging / 'index.html').write_text('\n'.join(lines), encoding='utf-8')
    return staging


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='build_licenses.py')
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--check-release', action='store_true')
    parser.add_argument('--additional-requirement', action='append',
                        default=[])
    ns = parser.parse_args(argv)
    try:
        staging = prepare_licenses(
            ROOT, ns.output,
            additional_requirements=ns.additional_requirement)
    except RuntimeError as exc:
        print(f'error: {exc}')
        return 1
    print(f'License staging directory: {staging}')
    print('WARNING: source_status=incomplete — this preparation is not '
          'release clearance.')
    for item in PENDING:
        print(f'  pending: {item}')
    if ns.check_release:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
