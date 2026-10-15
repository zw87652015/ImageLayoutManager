"""Qt-free tests for the MSIX AppData-virtualization alias in
``_resolve_resource_paths`` (package_manager).

An MSIX/MS Store build redirects ``%APPDATA%`` writes to
``…\\AppData\\<Local|Roaming>\\Packages\\<pkg>\\LocalCache\\<Local|Roaming>\\…``,
so a bundle packed by the packaged build stores virtualized
``original_source_path`` values while cells keep plain paths (or vice
versa). The resolver must still bind them to the embedded asset.
"""

import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from src.utils.figpack.errors import BundleError
from src.utils.figpack.package_manager import (
    PROJECT_JSON,
    RESOURCE_PREFIX,
    _msix_key,
    _resolve_path_key,
    _resolve_resource_paths,
    _transform_project_dict,
    pack_project,
    unpack_project,
)

_PLAIN = (r"C:\Users\17406\AppData\Local\ImageLayoutManager"
          r"\figpack_cache\pasted_images\pasted-1.png")
_VIRT = (r"C:\Users\17406\AppData\Local\Packages"
         r"\RiverQuasar.ImageLayoutManager_gpjxzdcrcgza4\LocalCache\Local"
         r"\ImageLayoutManager\figpack_cache\pasted_images\pasted-1.png")
_VIRT2 = (r"C:\Users\17406\AppData\Local\Packages"
          r"\Other.Package_abcdef\LocalCache\Local"
          r"\ImageLayoutManager\figpack_cache\pasted_images\pasted-1.png")
_UNRELATED = r"D:\unrelated\other\pasted-9.png"


def _manifest(osp, rid="res_1"):
    return {rid: {
        "status": "ok",
        "archive_path": "assets/pasted-1.png",
        "original_source_path": osp,
    }}


def _project(image_path, osp=None):
    cell = {"image_path": image_path}
    if osp is not None:
        cell["original_source_path"] = osp
    return {"cells": [cell]}


class TestMsixKey(unittest.TestCase):
    def test_folds_virtualized_path(self):
        self.assertEqual(
            _msix_key(_VIRT),
            _msix_key(_PLAIN),
        )

    def test_plain_path_unchanged(self):
        self.assertNotIn("packages", _msix_key(_PLAIN))

    def test_unrelated_path_unchanged(self):
        self.assertEqual(_msix_key(_UNRELATED), _resolve_path_key(_UNRELATED))


class TestResolveMsixAlias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = self._tmp.name
        self.dest = os.path.join(
            os.path.realpath(self.target), "assets", "pasted-1.png")
        self.names = {"assets/pasted-1.png"}

    def _resolve(self, project, manifest):
        return _resolve_resource_paths(
            project, manifest, self.target, extracted_names=self.names)

    def test_virtualized_manifest_plain_cell(self):
        project = _project(_PLAIN)
        missing = self._resolve(project, _manifest(_VIRT))
        self.assertEqual(missing, 0)
        self.assertEqual(project["cells"][0]["image_path"], self.dest)
        self.assertEqual(
            project["cells"][0]["original_source_path"], _VIRT)

    def test_plain_manifest_virtualized_cell(self):
        project = _project(_VIRT)
        missing = self._resolve(project, _manifest(_PLAIN))
        self.assertEqual(missing, 0)
        self.assertEqual(project["cells"][0]["image_path"], self.dest)

    def test_cell_osp_used_as_msix_key(self):
        project = _project(None, osp=_PLAIN)
        # image_path None → pick() returns None early; use a stale ip
        project["cells"][0]["image_path"] = r"D:\gone\pasted-1.png"
        missing = self._resolve(project, _manifest(_VIRT))
        self.assertEqual(missing, 0)
        self.assertEqual(project["cells"][0]["image_path"], self.dest)

    def test_unrelated_paths_stay_unmatched(self):
        project = _project(_UNRELATED)
        missing = self._resolve(project, _manifest(_VIRT))
        self.assertEqual(missing, 0)
        self.assertEqual(project["cells"][0]["image_path"], _UNRELATED)

    def test_ambiguous_msix_matches_raise(self):
        manifest = _manifest(_VIRT, "res_1")
        manifest["res_2"] = {
            "status": "ok",
            "archive_path": "assets/pasted-2.png",
            "original_source_path": _VIRT2,
        }
        with self.assertRaises(BundleError) as ctx:
            self._resolve(_project(_PLAIN), manifest)
        self.assertEqual(ctx.exception.code, "ambiguous_resource")


class _MsixRedirect:
    """Patches ``os.path.realpath`` inside package_manager so a plain
    AppData path resolves to a divergent "virtualized" path — the same
    divergence MSIX AppData redirection (or a symlink/junction/subst)
    produces on the pack side."""

    def __init__(self, mapping):
        self._real = os.path.realpath
        self._map = {os.path.normpath(k): v for k, v in mapping.items()}

    def fake(self, p):
        return self._map.get(os.path.normpath(p), self._real(p))

    def patch(self):
        return mock.patch(
            "src.utils.figpack.package_manager.os.path.realpath",
            self.fake,
        )


class _FakeCell:
    def __init__(self, image_path, original_source_path=None):
        self.image_path = image_path
        self.original_source_path = original_source_path


class _FakeProject:
    def __init__(self, leaf_cells, project_dict):
        self._leaf_cells = leaf_cells
        self._dict = project_dict
        self.name = "msix-test"
        self.figure_number = ""
        self.figure_title = ""

    def get_all_leaf_cells(self):
        return list(self._leaf_cells)

    def to_dict(self):
        return json.loads(json.dumps(self._dict))


class TestTransformCanonicalKey(unittest.TestCase):
    """``_transform_project_dict`` must look cells up by the same
    canonical key ``_build_manifest`` used, with the abspath form as a
    fallback."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        self.plain = os.path.join(
            root, "AppData", "Local", "ILM", "pasted-1.png")
        self.virt = os.path.join(
            root, "AppData", "Local", "Packages", "Pkg_abc",
            "LocalCache", "Local", "ILM", "pasted-1.png")
        self.unknown = os.path.join(root, "elsewhere", "x.png")
        self.redirect = _MsixRedirect({self.plain: self.virt})
        canon_virt = os.path.normpath(self.virt)
        self.path_to_id = {canon_virt: "res_1"}

    def test_top_level_and_nested_cells(self):
        project = {"cells": [
            {"image_path": self.plain},
            {"image_path": None, "children": [
                {"image_path": self.plain},
                {"image_path": self.unknown},
            ]},
        ]}
        with self.redirect.patch():
            out = _transform_project_dict(project, self.path_to_id)
        self.assertEqual(
            out["cells"][0]["image_path"], f"{RESOURCE_PREFIX}res_1")
        self.assertEqual(
            out["cells"][1]["children"][0]["image_path"],
            f"{RESOURCE_PREFIX}res_1")
        self.assertEqual(
            out["cells"][1]["children"][1]["image_path"], self.unknown)

    def test_abspath_fallback(self):
        # path_to_id keyed by the unresolved abspath (old fast-path map)
        key = os.path.normpath(os.path.abspath(self.plain))
        project = {"cells": [{"image_path": self.plain}]}
        with self.redirect.patch():
            out = _transform_project_dict(project, {key: "res_7"})
        self.assertEqual(
            out["cells"][0]["image_path"], f"{RESOURCE_PREFIX}res_7")


class TestPackUnpackMsixRoundTrip(unittest.TestCase):
    """End-to-end: with realpath diverging, pack must still write
    ``figpack:res_N`` markers into project.json and unpack must yield
    zero missing resources."""

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            plain = os.path.join(
                root, "AppData", "Local", "ILM", "pasted-1.png")
            virt = os.path.join(
                root, "AppData", "Local", "Packages", "Pkg_abc",
                "LocalCache", "Local", "ILM", "pasted-1.png")
            os.makedirs(os.path.dirname(virt))
            with open(virt, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\nfake-bytes")

            cell = _FakeCell(plain)
            project = _FakeProject(
                [cell], {"cells": [{"image_path": plain}]})
            pack_path = os.path.join(root, "out.figpack")

            with _MsixRedirect({plain: virt}).patch():
                result = pack_project(project, pack_path)
            self.assertEqual(result.missing_count, 0)
            self.assertEqual(result.asset_count, 1)

            with zipfile.ZipFile(pack_path) as zf:
                packed = json.loads(zf.read(PROJECT_JSON))
            self.assertEqual(
                packed["cells"][0]["image_path"],
                f"{RESOURCE_PREFIX}res_1")

            target = os.path.join(root, "unpacked")
            ur = unpack_project(pack_path, target)
            self.assertEqual(ur.missing_count, 0)
            unpacked_ip = ur.project_data["cells"][0]["image_path"]
            self.assertTrue(os.path.isfile(unpacked_ip))
            with open(unpacked_ip, "rb") as f:
                self.assertEqual(f.read(), b"\x89PNG\r\n\x1a\nfake-bytes")


if __name__ == "__main__":
    unittest.main()
