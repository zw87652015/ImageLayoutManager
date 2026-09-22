import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path

from packaging.utils import canonicalize_name

from build_licenses import _contained_regular_file, _is_reparse

NATIVE_SUFFIXES = {'.dll', '.pyd', '.exe'}
ASSET_SUFFIXES = {'.ttf', '.otf', '.onnx', '.jpg', '.png', '.svg', '.ico', '.icns'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular_files(root):
    root = Path(root).absolute()
    if any(_is_reparse(p) for p in (root, *root.parents)):
        raise ValueError('Reparse paths are not accepted')
    if not root.is_dir():
        raise ValueError('Input directory does not exist')
    for directory, directories, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in directories + filenames:
            if _is_reparse(current / name):
                raise ValueError('Input contains a reparse point')
        for name in sorted(filenames):
            path = current / name
            if not path.is_file():
                raise ValueError('Input contains a non-regular file')
            yield path


def record_index(distributions, wanted_names):
    index = defaultdict(list)
    for dist in distributions:
        name = canonicalize_name(dist.metadata['Name'])
        for item in dist.files or []:
            if Path(item).name.lower() not in wanted_names:
                continue
            recorded = item.hash
            if recorded is None or recorded.mode != 'sha256':
                continue
            try:
                value = base64.urlsafe_b64decode(recorded.value + '===')
            except ValueError:
                continue
            if len(value) != 32:
                continue
            index[(Path(item).name.lower(), value.hex())].append({
                'name': name, 'version': dist.version,
                'record_path': str(item).replace('\\', '/'),
            })
    return index


def inventory(bundle):
    from PyInstaller.archive.readers import CArchiveReader

    root = Path(bundle).absolute()
    paths = sorted(regular_files(root))
    manifest_path = _contained_regular_file(root, '_internal/licenses/components.json')
    if manifest_path is None:
        raise ValueError('Bundle license manifest is missing')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    components = manifest['components']
    declared = {(canonicalize_name(c['name']), c['version']) for c in components}
    distributions = list(metadata.distributions())
    records = record_index(distributions, {p.name.lower() for p in paths})
    files = []
    observed = set()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        sha256 = digest(path)
        candidates = records.get((path.name.lower(), sha256), [])
        observed.update((c['name'], c['version']) for c in candidates)
        files.append({
            'path': rel, 'size': path.stat().st_size, 'sha256': sha256,
            'kind': 'native' if path.suffix.lower() in NATIVE_SUFFIXES else
                    'asset' if path.suffix.lower() in ASSET_SUFFIXES else 'other',
            'record_digest_matches': candidates,
        })
    archives = []
    top_levels = set()
    for executable in ('ImageLayoutManager.exe', 'imagelayout-cli.exe'):
        path = _contained_regular_file(root, executable)
        if path is None:
            raise ValueError('Expected application executable is missing')
        reader = CArchiveReader(str(path))
        modules = set()
        for name, entry in reader.toc.items():
            if entry[-1] == 'z':
                modules.update(reader.open_embedded_archive(name).toc)
        top_levels.update(name.split('.')[0] for name in modules)
        archives.append({'path': executable, 'python_modules': sorted(modules)})
    package_map = metadata.packages_distributions()
    module_candidates = []
    for top_level in sorted(top_levels):
        owners = []
        for name in package_map.get(top_level, []):
            dist = metadata.distribution(name)
            pair = (canonicalize_name(dist.metadata['Name']), dist.version)
            observed.add(pair)
            owners.append({'name': pair[0], 'version': pair[1]})
        if owners:
            module_candidates.append({'module': top_level, 'installed_candidates': owners})
    return {
        'schema_version': 1, 'source_status': 'incomplete',
        'scope': 'Actual onedir file hashes and embedded Python module names; '
                 'installed RECORD digest matches and module-owner candidates are '
                 'provenance evidence, not legal clearance or native subcomponent coverage.',
        'app_version': manifest['app_version'],
        'license_manifest_sha256': digest(manifest_path),
        'build_python_version': sys.version.split()[0],
        'declared_components': [{'name': n, 'version': v} for n, v in sorted(declared)],
        'observed_distribution_candidates': [{'name': n, 'version': v} for n, v in sorted(observed)],
        'additional_distribution_candidates': [{'name': n, 'version': v} for n, v in sorted(observed - declared)],
        'files': files, 'executable_archives': archives,
        'python_module_distribution_candidates': module_candidates,
        'native_files_without_record_match': [f['path'] for f in files
                                              if f['kind'] == 'native' and not f['record_digest_matches']],
        'pending': [
            'Review native subcomponents, assets and unmatched files individually.',
            'Verify exact runtime/compiler provenance and matching source/build recipes.',
            'Review all source archives for bundled submodules, patches and build inputs.',
            'Publish matching corresponding source with the release.',
            'Complete installed-package testing and Store certification.',
        ],
    }


def safe_source_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or
            parsed.hostname not in {'pypi.org', 'files.pythonhosted.org'}):
        raise ValueError('Unexpected source download host')
    return url


def fetch_source(component, output):
    name, version = component['name'], component['version']
    result = {'name': name, 'version': version, 'status': 'unresolved'}
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._\-]*', name) or '..' in name:
        result['reason'] = 'Unsafe component name'
        return result
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_\-]*', version):
        result['reason'] = 'Unsafe component version'
        return result
    url = f'https://pypi.org/pypi/{urllib.parse.quote(name, safe="")}/{urllib.parse.quote(version, safe="")}/json'
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            safe_source_url(response.url)
            release = json.load(response)
        if canonicalize_name(release['info']['name']) != canonicalize_name(name) or release['info']['version'] != version:
            raise ValueError('Source release identity mismatch')
        sdists = [item for item in release['urls'] if item['packagetype'] == 'sdist' and not item.get('yanked')]
        if not sdists:
            result['reason'] = 'Exact release has no non-yanked PyPI source archive'
            return result
        downloads = []
        for item in sorted(sdists, key=lambda value: value['filename']):
            filename = item['filename']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+\-]*', filename) or '..' in filename:
                raise ValueError('Unsafe source archive filename')
            expected = item['digests']['sha256']
            if not re.fullmatch(r'[0-9a-f]{64}', expected):
                raise ValueError('Invalid source archive digest')
            size = item['size']
            if not isinstance(size, int) or size < 0 or size > 1024 ** 3:
                raise ValueError('Source archive exceeds size limit')
            folder = output / canonicalize_name(name)
            folder.mkdir(exist_ok=True)
            destination = folder / filename
            partial = destination.with_name(filename + '.partial')
            source_url = safe_source_url(item['url'])
            downloaded = 0
            hasher = hashlib.sha256()
            with urllib.request.urlopen(source_url, timeout=60) as response, partial.open('xb') as stream:
                safe_source_url(response.url)
                while block := response.read(1024 * 1024):
                    downloaded += len(block)
                    if downloaded > size:
                        raise ValueError('Source archive exceeds advertised size')
                    hasher.update(block)
                    stream.write(block)
            if downloaded != size or hasher.hexdigest() != expected:
                raise ValueError('Source archive size or SHA256 mismatch')
            if destination.exists():
                raise ValueError('Source destination already exists')
            partial.rename(destination)
            downloads.append({'path': destination.relative_to(output).as_posix(),
                              'url': source_url, 'sha256': expected, 'size': size})
        result.update(status='sdist_downloaded_not_correspondence_verified', archives=downloads)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['reason'] = type(exc).__name__
    return result


def collect_sources(report, output):
    pairs = {(c['name'], c['version']) for key in ('declared_components', 'observed_distribution_candidates')
             for c in report.get(key, [])}
    components = [{'name': name, 'version': version} for name, version in sorted(pairs)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda component: fetch_source(component, output), components))
    return {'schema_version': 1, 'source_status': 'incomplete',
            'scope': 'Exact-version PyPI sdists checked against PyPI SHA256 and size; '
                     'not verified complete corresponding source. Python/Conda runtime, '
                     'wheel-vendored native libraries, build recipes, submodules and patches require review.',
            'app_version': report['app_version'], 'components': results}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    audit = sub.add_parser('inventory')
    audit.add_argument('--bundle', type=Path, required=True)
    audit.add_argument('--output', type=Path, required=True)
    sources = sub.add_parser('sources')
    sources.add_argument('--inventory', type=Path, required=True)
    sources.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    if any(_is_reparse(p) for p in (output, *output.parents)):
        parser.error('Output must not use reparse paths')
    if output.exists():
        parser.error('Output must be a new directory')
    if args.command == 'inventory':
        bundle = args.bundle.resolve()
        if output.resolve().is_relative_to(bundle) or bundle.is_relative_to(output.resolve()):
            parser.error('Output and bundle must not contain each other')
        report = inventory(bundle)
        output.mkdir(parents=True, exist_ok=False)
    else:
        data = json.loads(args.inventory.read_text(encoding='utf-8'))
        output.mkdir(parents=True, exist_ok=False)
        report = collect_sources(data, output)
        report['inventory_sha256'] = digest(args.inventory)
    filename = 'artifact-inventory.json' if args.command == 'inventory' else 'source-downloads.json'
    (output / filename).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{filename} written; source_status=incomplete')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
