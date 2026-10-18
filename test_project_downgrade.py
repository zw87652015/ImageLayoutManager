"""Tests for src/model/downgrade.py (Save Copy for Older ILM)."""

import copy
import json
import os
import tempfile
import unittest

from src.model.migrations import (
    PROJECT_SCHEMA_VERSION,
    SCHEMA_FIRST_RELEASE,
    SCHEMA_MIGRATIONS,
    migrate_project_data,
    read_project_meta,
)
from src.model.downgrade import (
    DOWNGRADE_TARGETS,
    DOWNGRADES,
    downgrade_project_data,
)


def _rich_dict() -> dict:
    """A schema-8 dict exercising every feature a downgrade can drop,
    including a nested child cell."""
    from src.model.data_model import (
        Cell, Mark, Project, RasterTextRegion, SvgTextGroup,
        SvgTextMember, TextItem,
    )
    rotated = RasterTextRegion(
        id="r1", x=1.0, y=2.0, w=30.0, h=8.0, text="tilted",
        font_size_px=9.0, group_id="g1", angle=35.0,
    )
    normal = RasterTextRegion(
        id="r2", x=1.0, y=12.0, w=30.0, h=8.0, text="flat",
        font_size_px=9.0, group_id="g2", angle=0.0,
    )
    leaf = Cell(
        id="leaf1", image_path="panel.ilmplot.svg", plot_reflow=False,
        raster_text_regions=[rotated, normal],
    )
    nested_leaf = Cell(
        id="leaf2", image_path="b.png", plot_reflow=True,
        raster_text_regions=[
            RasterTextRegion(
                id="r3", x=0.0, y=0.0, w=5.0, h=2.0, text="n",
                font_size_px=8.0, angle=-20.0,
            ),
        ],
    )
    parent = Cell(id="container", children=[nested_leaf])
    p = Project()
    p.cells = [leaf, parent]
    p.text_items = [
        TextItem(
            id="t1", text="main", subtype="strip",
            sub_labels=["a", "b"], sub_label_splits=[0.5],
        ),
        TextItem(id="t2", text="plain"),
    ]
    p.marks = [
        Mark(id="m1", kind="line", points=[[0.0, 0.0], [10.0, 10.0]],
             arrow_end="triangle"),
    ]
    p.svg_text_groups = [
        SvgTextGroup(id="g1", name="axis", font_size_pt=9.0,
                     members=[SvgTextMember(svg_path="a.svg",
                                            element_key="k1")]),
    ]
    return p.to_dict()


def _all_cells(data):
    stack = list(data.get("cells", []))
    while stack:
        c = stack.pop()
        yield c
        stack.extend(c.get("children") or [])


class TestDowngradeSteps(unittest.TestCase):
    def setUp(self):
        self.data = _rich_dict()

    def test_8_to_7(self):
        out, issues = DOWNGRADES[8](self.data)
        self.assertEqual(out["schema_version"], 7)
        self.assertEqual(issues, [("rotated_text_removed", 2)])
        ids = [
            r["id"]
            for c in _all_cells(out)
            for r in c.get("raster_text_regions") or []
        ]
        self.assertEqual(ids, ["r2"])
        for c in _all_cells(out):
            for r in c.get("raster_text_regions") or []:
                self.assertNotIn("angle", r)

    def test_7_to_6(self):
        d7, _ = DOWNGRADES[8](self.data)
        out, issues = DOWNGRADES[7](d7)
        self.assertEqual(out["schema_version"], 6)
        self.assertEqual(issues, [("split_labels_merged", 1)])
        for item in out["text_items"]:
            self.assertNotIn("sub_labels", item)
            self.assertNotIn("sub_label_splits", item)

    def test_6_to_5(self):
        d6, _ = downgrade_project_data(self.data, 6)
        out, issues = DOWNGRADES[6](d6)
        self.assertEqual(out["schema_version"], 5)
        self.assertEqual(issues, [("marks_removed", 1)])
        self.assertNotIn("marks", out)

    def test_5_to_4(self):
        d5, _ = downgrade_project_data(self.data, 5)
        out, issues = DOWNGRADES[5](d5)
        self.assertEqual(out["schema_version"], 4)
        self.assertEqual(issues, [("plot_reflow_lost", 1)])
        for c in _all_cells(out):
            self.assertNotIn("plot_reflow", c)

    def test_full_chain_to_4(self):
        out, issues = downgrade_project_data(self.data, 4)
        self.assertEqual(out["schema_version"], 4)
        self.assertEqual(
            dict(issues),
            {
                "rotated_text_removed": 2,
                "split_labels_merged": 1,
                "marks_removed": 1,
                "plot_reflow_lost": 1,
            },
        )
        self.assertEqual(out["file_version"], self.data["file_version"])

    def test_input_not_mutated(self):
        snapshot = copy.deepcopy(self.data)
        downgrade_project_data(self.data, 4)
        self.assertEqual(self.data, snapshot)

    def test_zero_count_issues_omitted(self):
        # A project with nothing droppable yields an empty issue list.
        p = _plain_dict()
        out, issues = downgrade_project_data(p, 4)
        self.assertEqual(issues, [])
        self.assertEqual(out["schema_version"], 4)

    def test_roundtrip_through_migrations(self):
        for target, _label in DOWNGRADE_TARGETS:
            down, _issues = downgrade_project_data(self.data, target)
            re_up = migrate_project_data(down)
            self.assertEqual(re_up["schema_version"],
                             PROJECT_SCHEMA_VERSION)
            # Dropped features come back only as empty defaults.
            if target <= 5:
                self.assertEqual(re_up.get("marks") or [], [])
            else:
                self.assertTrue(re_up.get("marks"))
            if target <= 6:
                for item in re_up["text_items"]:
                    self.assertFalse(item.get("sub_labels"))
                    self.assertFalse(item.get("sub_label_splits"))
            if target <= 4:
                for c in _all_cells(re_up):
                    self.assertTrue(c.get("plot_reflow", True))
            region_ids = [
                r["id"]
                for c in _all_cells(re_up)
                for r in c.get("raster_text_regions") or []
            ]
            self.assertEqual(region_ids, ["r2"])
            for c in _all_cells(re_up):
                for r in c.get("raster_text_regions") or []:
                    self.assertEqual(r.get("angle"), 0.0)
            # Untouched data survives the down/up round trip.
            for key in ("name", "page_width_mm", "dpi",
                        "plot_alignment_groups", "size_groups",
                        "svg_text_groups", "group_labels"):
                self.assertEqual(
                    re_up[key],
                    migrate_project_data(self.data)[key],
                )


def _plain_dict() -> dict:
    from src.model.data_model import Cell, Project
    p = Project()
    p.cells = [Cell(id="only", image_path="x.png")]
    return p.to_dict()


class TestGuards(unittest.TestCase):
    def test_every_released_step_has_a_downgrade(self):
        min_target = min(schema for schema, _ in DOWNGRADE_TARGETS)
        for s in range(min_target + 1, PROJECT_SCHEMA_VERSION + 1):
            if (s - 1) in SCHEMA_MIGRATIONS:
                self.assertIn(s, DOWNGRADES,
                              f"missing downgrade step for schema {s}")

    def test_targets_and_current_have_first_releases(self):
        for schema, _label in DOWNGRADE_TARGETS:
            self.assertIn(schema, SCHEMA_FIRST_RELEASE)
        self.assertIn(PROJECT_SCHEMA_VERSION, SCHEMA_FIRST_RELEASE)

    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            downgrade_project_data(_plain_dict(), PROJECT_SCHEMA_VERSION)
        with self.assertRaises(ValueError):
            downgrade_project_data(_plain_dict(), 3)


class TestReadProjectMeta(unittest.TestCase):
    def test_reads_schema_and_writer(self):
        data = _plain_dict()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.figlayout")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            schema, writer = read_project_meta(path)
        self.assertEqual(schema, data["schema_version"])
        self.assertEqual(writer, data["file_version"])

    def test_unreadable_returns_nones(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.figlayout")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not json")
            self.assertEqual(read_project_meta(path), (None, None))
            missing = os.path.join(tmp, "none.figlayout")
            self.assertEqual(read_project_meta(missing), (None, None))


if __name__ == "__main__":
    unittest.main()
