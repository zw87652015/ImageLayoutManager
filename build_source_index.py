"""Build the published corresponding-source index for a release.

Two stages, deliberately separated so the published index does not depend on
the disposable ``build/`` tree:

``collect``
    Reads the recorded download/provenance manifests under ``build/`` and
    writes the tracked machine-readable ``licenses/sources.json``.

``render``
    Reads ``licenses/sources.json`` only and writes the human-readable
    ``SOURCES.md``. This is what ships next to a release.

Every entry keeps the status string recorded when the source was located, so
"downloaded but correspondence not verified" is never silently upgraded to
"verified". Components with no open-source counterpart (the Microsoft Visual
C++ runtime) stay in the index as explicit exceptions rather than being
dropped.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from packaging.utils import canonicalize_name

from src.version import APP_VERSION

ROOT = Path(__file__).resolve().parent
SOURCES_JSON = ROOT / 'licenses' / 'sources.json'
SOURCES_MD = ROOT / 'SOURCES.md'
SCHEMA_VERSION = 2

# Native notice components whose corresponding source is recorded elsewhere.
# Maps the components.json name to (manifest key, source record locator).
NATIVE_SOURCE_KEYS = {
    'Qt Base upstream notices': 'qtbase',
    'Qt SVG upstream notices': 'qtsvg',
    'Qt Image Formats upstream notices': 'qtimageformats',
    'Qt PDF and Chromium upstream notices': 'qtwebengine',
    'Mesa software renderer upstream notices': 'mesa',
    'LLVM software renderer upstream notices': 'llvm',
    'MuPDF upstream notices': 'mupdf',
    'GEOS upstream notices': 'geos',
    'Conda bzip2 runtime notices': 'bzip2',
    'Conda libexpat runtime notices': 'libexpat',
    'Conda libffi runtime notices': 'libffi',
    'Conda libmpdec runtime notices': 'libmpdec',
    'Conda libzlib runtime notices': 'libzlib',
    'Conda openssl runtime notices': 'openssl',
    'Conda python runtime notices': 'python',
    'Conda vc14_runtime runtime notices': 'vc14_runtime',
    'Conda xz runtime notices': 'xz',
}

# Distributions with no usable PyPI sdist for the exact shipped version.
# PyQt6-Qt6 ships prebuilt Qt libraries, so its source is the Qt modules.
QT_MODULE_KEYS = ('qtbase', 'qtsvg', 'qtimageformats', 'qttranslations',
                  'qtwebengine')

# Archives fetched from a regional mirror are published under the upstream
# project's own location; the recorded digest identifies the same bytes.
MIRROR_CANONICAL = {
    'https://ftp.jaist.ac.jp/pub/qtproject/archive/':
        'https://download.qt.io/archive/',
}

BUILD_STEPS = [
    'Install Python 3.13.15 and create an environment from environment.yml.',
    'Install the exact dependency versions recorded in '
    '`installed-versions.txt` inside the release licence materials.',
    'Run `python build_licenses.py` to stage the licence materials.',
    'Run `python build_installer_windows.py` for the Windows installer, '
    '`python build_onefile.py` for the portable executable, or '
    '`python build_msix.py` for the Store package.',
]


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _records_by_name(items, key='name'):
    out = {}
    for item in items:
        out[str(item[key])] = item
    return out


def _version_map(items):
    return {canonicalize_name(str(item['name'])): str(item['version'])
            for item in items}


def _matching_manifest(paths, description, expected, *, list_key='components',
                       exact=False, scope_prefix=None):
    candidates = sorted({Path(path) for path in paths if Path(path).is_file()},
                        key=lambda path: (path.stat().st_mtime, str(path)),
                        reverse=True)
    for path in candidates:
        try:
            data = _load(path)
            items = data[list_key]
            actual = _version_map(items)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if scope_prefix and not str(data.get('scope', '')).startswith(
                scope_prefix):
            continue
        matches = actual == expected if exact else all(
            actual.get(name) == version for name, version in expected.items())
        if matches:
            return data
    versions = ', '.join(f'{name} {version}'
                         for name, version in sorted(expected.items()))
    raise SystemExit(f'no {description} manifest matches: {versions}')


def _matching_record(paths, description, name, version):
    candidates = sorted({Path(path) for path in paths if Path(path).is_file()},
                        key=lambda path: (path.stat().st_mtime, str(path)),
                        reverse=True)
    for path in candidates:
        try:
            record = _load(path)
        except (OSError, ValueError, TypeError):
            continue
        if (canonicalize_name(str(record.get('name', '')))
                == canonicalize_name(name)
                and str(record.get('version')) == str(version)):
            return record
    raise SystemExit(f'no {description} record matches: {name} {version}')


def _sha(value):
    return value if isinstance(value, str) and re.fullmatch(
        r'[0-9a-f]{64}', value) else None


def _python_source(record):
    """Return a source dict for a PyPI sdist record, or None."""
    archives = record.get('archives') or []
    for archive in archives:
        digest = _sha(archive.get('sha256'))
        url = archive.get('url')
        if digest and isinstance(url, str) and url.startswith('https://'):
            return {'type': 'pypi_sdist', 'url': url, 'sha256': digest}
    return None


def _git_source(record):
    commit = record.get('commit')
    repo = record.get('repo')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}',
                                                      commit):
        return None
    source = {'type': 'git_commit', 'repo': f'https://github.com/{repo}',
              'commit': commit}
    if record.get('tag'):
        source['tag'] = record['tag']
    source['notes'] = (
        'Cite the commit, not a generated tarball: GitHub archive bytes are '
        'not stable, while the commit identifies the exact tree. '
        f'`git clone https://github.com/{repo} && git checkout {commit}`')
    return source


def _canonical_url(url: str):
    """Prefer the upstream project URL over whichever mirror was used.

    Qt publishes its archives and their SHA-256 files under download.qt.io;
    a download may have come from a regional mirror with identical bytes.
    Publishing the canonical location keeps the index usable if a mirror
    disappears, and the recorded digest still identifies the archive.
    """
    for mirror, canonical in MIRROR_CANONICAL.items():
        if url.startswith(mirror):
            return canonical + url[len(mirror):], url
    return url, None


def _archive_source(record, kind='release_archive'):
    url = record.get('url')
    digest = _sha(record.get('sha256')) or _sha(
        record.get('downloaded_sha256'))
    if not isinstance(url, str) or not url.startswith('https://'):
        return None
    canonical, mirror = _canonical_url(url)
    source = {'type': kind, 'url': canonical}
    if digest:
        source['sha256'] = digest
    if mirror:
        source['downloaded_from_mirror'] = mirror
    if record.get('hash_source'):
        source['hash_source'] = record['hash_source']
    return source


def collect(build_dir: Path) -> dict:
    build = Path(build_dir)
    candidates = sorted(build.glob('store-candidate-*/dist/ImageLayoutManager'
                                   '/_internal/licenses/components.json'),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    manifest = None
    for path in candidates:
        found = _load(path)
        if found.get('app_version') == APP_VERSION:
            manifest = found
            break
    if manifest is None:
        raise SystemExit(
            f'no built candidate for version {APP_VERSION} found under '
            f'{build}; run a build first')

    python_expected = {
        canonicalize_name(str(comp['name'])): str(comp['version'])
        for comp in manifest['components']
        if not str(comp.get('role', '')).startswith('native')}
    native_expected = {
        NATIVE_SOURCE_KEYS[comp['name']]: str(comp['version'])
        for comp in manifest['components']
        if comp['name'] in NATIVE_SOURCE_KEYS}

    py_manifest = _matching_manifest(
        build.rglob('*source-downloads.json'), 'exact-version Python source',
        python_expected, exact=False,
        scope_prefix='Exact-version PyPI sdists')
    py_records = {
        canonicalize_name(name): record
        for name, record in _records_by_name(
            py_manifest['components']).items()}
    tagged_expected = {
        name: version for name, version in python_expected.items()
        if name != 'pyqt6-qt6'
        and _python_source(py_records.get(name, {})) is None}
    tagged = {}
    if tagged_expected:
        tagged_manifest = _matching_manifest(
            build.rglob('*tagged-source-downloads.json'),
            'tagged Git source', tagged_expected, exact=False)
        tagged = {
            canonicalize_name(name): record
            for name, record in _records_by_name(
                tagged_manifest['components']).items()}

    conda_keys = {'bzip2', 'libexpat', 'libffi', 'libmpdec', 'libzlib',
                  'openssl', 'python', 'vc14-runtime', 'xz'}
    conda_expected = {
        canonicalize_name(name): version
        for name, version in native_expected.items()
        if canonicalize_name(name) in conda_keys}
    conda_manifest = _matching_manifest(
        build.rglob('*conda-source-downloads.json'), 'Conda source',
        conda_expected, exact=True)

    qt_expected = {
        canonicalize_name(name): version
        for name, version in native_expected.items()
        if name in {'qtbase', 'qtsvg', 'qtimageformats'}}
    qt_manifest = _matching_manifest(
        build.rglob('*qt-source-downloads.json'), 'Qt module source',
        qt_expected, list_key='modules')
    qt_modules = _records_by_name(qt_manifest['modules'])
    qtbase_records = list(build.rglob('*qtbase-resumed-download.json'))
    if qtbase_records:
        record = _matching_record(qtbase_records, 'Qt Base resumed source',
                                  'qtbase', native_expected['qtbase'])
        if record.get('status') == 'upstream_hash_verified':
            qt_modules['qtbase'] = record

    qt_native_expected = {
        canonicalize_name(name): version
        for name, version in native_expected.items()
        if name in {'mesa', 'llvm', 'qtwebengine'}}
    qt_native_manifest = _matching_manifest(
        build.rglob('*source-downloads.json'), 'native Qt source',
        qt_native_expected,
        scope_prefix='Native source archives and Qt binary provenance')

    native = _records_by_name(conda_manifest['components'])
    native.update(qt_modules)
    native.update(_records_by_name(qt_native_manifest['components']))
    native['mupdf'] = _matching_record(
        build.rglob('*mupdf-source-download.json'), 'MuPDF source', 'mupdf',
        native_expected['mupdf'])
    native['geos'] = _matching_record(
        build.rglob('*geos-download.json'), 'GEOS source', 'geos',
        native_expected['geos'])
    python_record = _matching_record(
        build.rglob('*python-download.json'), 'Python source', 'python',
        native_expected['python'])
    native['python'] = {**native.get('python', {}), **python_record}

    entries = []
    unresolved = []
    for comp in manifest['components']:
        name = comp['name']
        version = comp['version']
        role = comp.get('role') or 'dependency'
        entry = {'name': name, 'version': version, 'role': role,
                 'license_expression': comp.get('license_expression')}
        if str(role).startswith('native'):
            key = NATIVE_SOURCE_KEYS.get(name)
            record = native.get(key) if key else None
            entry['kind'] = 'native'
            if key == 'vc14_runtime':
                entry['source'] = {
                    'type': 'proprietary_redistributable',
                    'notes': 'Microsoft Visual C++ runtime. Redistributed '
                             'under Microsoft redistribution terms; no '
                             'open-source corresponding source exists. '
                             'Notices are shipped with the application.'}
                entry['status'] = record.get('status') if record else 'unknown'
            elif record is None:
                entry['source'] = None
                entry['status'] = 'no_source_record'
                unresolved.append({'name': name, 'version': version,
                                   'reason': 'no recorded source archive'})
            else:
                kind = ('conda_recipe_upstream'
                        if str(record.get('status', '')).startswith('conda')
                        else 'release_archive')
                entry['source'] = _archive_source(record, kind)
                entry['status'] = record.get('status', 'unknown')
                if entry['source'] is None:
                    unresolved.append({
                        'name': name, 'version': version,
                        'reason': record.get('reason')
                        or 'no usable https url or digest recorded'})
        else:
            canon = canonicalize_name(name)
            entry['kind'] = 'python'
            record = py_records.get(canon) or py_records.get(name)
            source = _python_source(record) if record else None
            if source is None and canon in tagged:
                source = _git_source(tagged[canon])
                entry['status'] = tagged[canon].get('status', 'unknown')
            elif source is not None:
                entry['status'] = record.get('status', 'unknown')
            if source is None and canon == 'pyqt6-qt6':
                source = {
                    'type': 'bundled_upstream_project',
                    'components': [
                        {'name': key,
                         **{k: v for k, v in
                            (_archive_source(native[key]) or {}).items()
                            if k != 'type'}}
                        for key in QT_MODULE_KEYS if key in native],
                    'notes': 'This wheel redistributes prebuilt Qt libraries; '
                             'its corresponding source is the Qt module '
                             'source listed here.'}
                entry['status'] = 'qt_module_source_recorded'
            if source is None:
                entry['source'] = None
                entry['status'] = entry.get('status', 'no_source_record')
                unresolved.append({
                    'name': name, 'version': version,
                    'reason': (record or {}).get('reason')
                    or 'no recorded source archive'})
            else:
                entry['source'] = source
        entries.append(entry)

    entries.sort(key=lambda e: (e['kind'], e['name'].lower()))
    return {
        'schema_version': SCHEMA_VERSION,
        'app_version': APP_VERSION,
        'python_version': manifest.get('python_version'),
        'scope': 'Corresponding-source pointers for the bundled components '
                 'of the Windows x64 build of Image Layout Manager '
                 f'{APP_VERSION}. Application source is published as the '
                 'release source archive; this index locates the source of '
                 'every third-party component shipped inside the binary.',
        'index_status': 'pointers_recorded',
        'source_status': manifest.get('source_status', 'incomplete'),
        'application_source_archive':
            manifest.get('application_source_archive'),
        'build_steps': BUILD_STEPS,
        'component_count': len(entries),
        'no_open_source_counterpart': [
            {'name': e['name'], 'version': e['version'],
             'reason': (e['source'] or {}).get('notes')}
            for e in entries
            if (e['source'] or {}).get('type')
            == 'proprietary_redistributable'],
        'components': entries,
        'unresolved': unresolved,
    }


def _md_source(source) -> str:
    if source is None:
        return 'not recorded'
    kind = source.get('type')
    if kind == 'pypi_sdist':
        return f'[sdist]({source["url"]})<br>`{source["sha256"]}`'
    if kind == 'git_commit':
        tag = f' (tag `{source["tag"]}`)' if source.get('tag') else ''
        return (f'[{source["repo"]}]({source["repo"]}) commit '
                f'`{source["commit"]}`{tag}')
    if kind == 'bundled_upstream_project':
        parts = []
        for comp in source.get('components', []):
            url = comp.get('url')
            label = comp['name']
            parts.append(f'[{label}]({url})' if url else label)
        return 'Qt sources: ' + ', '.join(parts)
    if kind == 'proprietary_redistributable':
        return 'no open-source counterpart'
    url = source.get('url')
    digest = source.get('sha256')
    text = f'[archive]({url})' if url else 'not recorded'
    return f'{text}<br>`{digest}`' if digest else text


def render(data: dict) -> str:
    lines = [
        f'# Corresponding source for Image Layout Manager {data["app_version"]}',
        '',
        'The application source in this repository is licensed under '
        'Apache-2.0. The distributed Windows builds also bundle components '
        'under the GNU GPL v3 and AGPL v3, so this page records where to '
        'obtain the source of every third-party component inside those '
        'builds, at the exact versions shipped.',
        '',
        f'- Application version: **{data["app_version"]}**',
        f'- Python runtime: **{data.get("python_version") or "see below"}**',
        f'- Components covered: **{data["component_count"]}**',
        '- Components with no open-source counterpart: '
        f'**{len(data.get("no_open_source_counterpart", []))}** '
        '(see the exceptions section)',
        '- Application source archive: '
        f'`{data.get("application_source_archive") or "see release assets"}`',
        '',
        '## How to rebuild',
        '',
    ]
    for step in data['build_steps']:
        lines.append(f'1. {step}')
    lines += [
        '',
        'Each archive below is identified by its SHA-256 where the upstream '
        'project publishes stable archives. Components taken from Git are '
        'identified by commit, because generated archive bytes are not '
        'stable while a commit identifies the exact tree.',
        '',
    ]
    for kind, title in (('python', 'Python distributions'),
                        ('native', 'Native components')):
        rows = [c for c in data['components'] if c['kind'] == kind]
        if not rows:
            continue
        lines += [f'## {title} ({len(rows)})', '',
                  '| Component | Version | Licence | Source | Recorded status |',
                  '| --- | --- | --- | --- | --- |']
        for comp in rows:
            licence = comp.get('license_expression') or 'see notices'
            lines.append(
                f'| {comp["name"]} | {comp["version"]} | {licence} | '
                f'{_md_source(comp.get("source"))} | '
                f'`{comp.get("status", "unknown")}` |')
        lines.append('')
    if data['unresolved']:
        lines += ['## Components without a recorded source archive', '']
        for item in data['unresolved']:
            lines.append(
                f'- **{item["name"]} {item["version"]}** — {item["reason"]}')
        lines.append('')
    exceptions = data.get('no_open_source_counterpart') or []
    if exceptions:
        lines += ['## Exceptions', '']
        for item in exceptions:
            lines.append(f'- **{item["name"]} {item["version"]}** — '
                         f'{item["reason"]}')
        lines.append('')
    lines += [
        '## Status of this index',
        '',
        f'- Index status: `{data["index_status"]}`',
        f'- Release source status: `{data["source_status"]}`',
        '',
        'Recorded statuses are reproduced exactly as captured when each '
        'source was located. `sdist_downloaded_not_correspondence_verified` '
        'means the archive for the shipped version was retrieved and hashed, '
        'not that a byte-for-byte rebuild of the shipped binary was '
        'reproduced. The Microsoft Visual C++ runtime is redistributed under '
        'Microsoft terms and has no open-source counterpart.',
        '',
        'Machine-readable form: `licenses/sources.json`.',
        '',
    ]
    return '\n'.join(lines)


def index_errors(data, app_version=APP_VERSION):
    errors = []
    if data.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version {data.get("schema_version")} != '
                      f'{SCHEMA_VERSION}')
    if data.get('app_version') != app_version:
        errors.append(f'app_version {data.get("app_version")} != '
                      f'{app_version}')
    if 'application_source_sha256' in data:
        errors.append('application_source_sha256 is self-referential; '
                      'components.json owns that hash')
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='build_source_index.py')
    sub = parser.add_subparsers(dest='command', required=True)
    collect_cmd = sub.add_parser('collect')
    collect_cmd.add_argument('--build-dir', type=Path, default=ROOT / 'build')
    sub.add_parser('render')
    sub.add_parser('check')
    args = parser.parse_args(argv)

    if args.command == 'collect':
        data = collect(args.build_dir)
        SOURCES_JSON.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8')
        print(f'{SOURCES_JSON.name}: {data["component_count"]} components, '
              f'{len(data["unresolved"])} without a recorded archive, '
              f'{len(data["no_open_source_counterpart"])} with no '
              f'open-source counterpart')
        return 0

    if not SOURCES_JSON.is_file():
        print(f'error: {SOURCES_JSON} is missing; run `collect` first')
        return 2
    data = _load(SOURCES_JSON)
    if args.command == 'render':
        SOURCES_MD.write_text(render(data), encoding='utf-8')
        print(f'{SOURCES_MD.name} written from {SOURCES_JSON.name}')
        return 0

    errors = index_errors(data)
    if errors:
        print(f'error: sources.json {errors[0]}')
        return 2
    expected = render(data)
    if not SOURCES_MD.is_file() or SOURCES_MD.read_text(
            encoding='utf-8') != expected:
        print('error: SOURCES.md is stale; run `render`')
        return 2
    print(f'source index current: {data["component_count"]} components, '
          f'{len(data["unresolved"])} without a recorded archive, '
          f'{len(data.get("no_open_source_counterpart", []))} with no '
          f'open-source counterpart')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
