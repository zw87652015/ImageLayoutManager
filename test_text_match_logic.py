"""Qt-light logic tests for the Match Text Size session model and helpers."""

import unittest

from src.model.data_model import Cell, Project, RasterTextRegion, SvgTextGroup
from src.utils.text_group_assign import assign_raster
from src.utils.text_match import (
    RASTER_REL_TOL, format_size, raster_summary, size_clusters, svg_summary,
)
from src.app.text_match_session import (
    SessionRecorder, capture, restore, scoped_revert)
from src.app.commands import TextMatchSessionCommand


def _region(size_px=10.0, **kw):
    kw.setdefault('text', 'label')
    kw.setdefault('font_size_px', size_px)
    return RasterTextRegion(**kw)


class FakeStack:
    """QUndoStack stand-in: records pushes, never calls redo()."""

    def __init__(self):
        self.cmds = []

    def push(self, cmd):
        self.cmds.append(cmd)

    def index(self):
        return len(self.cmds)

    def command(self, i):
        return self.cmds[i]


class FakeCmd:
    def __init__(self, before=None, after=None):
        self.before, self.after = before, after


def _project_with_cell():
    project = Project()
    cell = Cell(image_path='x.png')
    project.cells = [cell]
    return project, cell


class SizeClustersTest(unittest.TestCase):
    def test_debug_image_sizes_two_clusters(self):
        px = [27.03, 27.78] * 7 + [27.03] + [52.97, 54.05, 54.05, 56.22]
        items = [{'id': i, 'size_pt': p * 0.2, 'text': f't{i}', 'flagged': False}
                 for i, p in enumerate(px)]
        clusters = size_clusters(items, RASTER_REL_TOL)
        self.assertEqual(len(clusters), 2)
        self.assertEqual([c['count'] for c in clusters], [15, 4])
        self.assertAlmostEqual(clusters[0]['size_pt'], 27.03 * 0.2, places=5)
        self.assertAlmostEqual(clusters[1]['size_pt'], 54.05 * 0.2, places=5)

    def test_boundary_tolerance(self):
        join = [{'id': 'a', 'size_pt': 10.0, 'text': '', 'flagged': False},
                {'id': 'b', 'size_pt': 11.2, 'text': '', 'flagged': False}]
        self.assertEqual(len(size_clusters(join, 0.12)), 1)
        split = [{'id': 'a', 'size_pt': 10.0, 'text': '', 'flagged': False},
                 {'id': 'b', 'size_pt': 11.3, 'text': '', 'flagged': False}]
        self.assertEqual(len(size_clusters(split, 0.12, min_count=1)), 2)

    def test_min_count_and_limit(self):
        items = [{'id': i, 'size_pt': float(s), 'text': '', 'flagged': False}
                 for i, s in enumerate([10, 10, 10, 20, 20, 30, 40, 40, 50, 50])]
        clusters = size_clusters(items, 0.12, min_count=2, limit=3)
        self.assertEqual([c['count'] for c in clusters], [3, 2, 2])
        self.assertEqual(size_clusters(
            [{'id': 'x', 'size_pt': 5.0, 'text': '', 'flagged': False}], 0.12), [])

    def test_samples_first_three_distinct(self):
        items = [{'id': i, 'size_pt': 10.0, 'text': t, 'flagged': False}
                 for i, t in enumerate(['a', 'a', '', 'b', 'c', 'd'])]
        (cluster,) = size_clusters(items, 0.12)
        self.assertEqual(cluster['samples'], ['a', 'b', 'c'])

    def test_flagged_count(self):
        items = [{'id': i, 'size_pt': 10.0, 'text': '', 'flagged': i < 2}
                 for i in range(4)]
        (cluster,) = size_clusters(items, 0.12)
        self.assertEqual(cluster['flagged'], 2)


class FormatSizeTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(format_size(8.0), '8 pt')
        self.assertEqual(format_size(6.14), '6.1 pt')

    def test_approx(self):
        self.assertEqual(format_size(6.14, approx=True), '≈6.1 pt')

    def test_target(self):
        self.assertEqual(format_size(6.14, 8.0, approx=True), '≈6.1 → 8 pt')
        self.assertEqual(format_size(6.1, 8.0), '6.1 → 8 pt')

    def test_equal_target_hidden(self):
        self.assertEqual(format_size(8.0, 8.04), '8 pt')
        self.assertEqual(format_size(8.0, 8.0, approx=True), '≈8 pt')


class SummariesTest(unittest.TestCase):
    def test_raster_summary(self):
        regions = [
            _region(group_id='g', enabled=True, id='a'),
            _region(warning='touching', id='b'),
            _region(group_id='g', enabled=True, id='c'),
            _region(id='d'),
        ]
        report = {'a': 'applied', 'c': 'skipped_collision'}
        out = raster_summary(regions, report)
        self.assertEqual(out, {'total': 4, 'resizing': 1, 'review': 2,
                               'ungrouped': 2})

    def test_svg_summary(self):
        rows = [{'key': 'a'}, {'key': 'b'}, {'key': 'c'}]
        out = svg_summary(rows, {'a': ('g', 'G'), 'c': ('g', 'G')})
        self.assertEqual(out, {'total': 3, 'grouped': 2})


class AssignRasterTest(unittest.TestCase):
    def test_enable_flagged_false_keeps_flagged_unticked(self):
        flagged = _region(warning='touching', enabled=False)
        clean = _region(enabled=False)
        assign_raster([flagged, clean], 'g', enable_flagged=False)
        self.assertEqual((flagged.group_id, flagged.enabled), ('g', False))
        self.assertEqual((clean.group_id, clean.enabled), ('g', True))

    def test_enable_flagged_default_enables_all(self):
        flagged = _region(warning='touching', enabled=False)
        assign_raster([flagged], 'g')
        self.assertTrue(flagged.enabled)


class CaptureRestoreTest(unittest.TestCase):
    def test_capture_restore_roundtrip(self):
        project, cell = _project_with_cell()
        project.svg_text_groups = [SvgTextGroup(name='A', font_size_pt=9.0)]
        cell.raster_text_regions = [_region(id='r1')]
        state = capture(project, cell)
        project.svg_text_groups = [SvgTextGroup(name='B', font_size_pt=5.0)]
        cell.raster_text_regions = [_region(id='r2')]
        restore(project, cell.id, state)
        self.assertEqual(project.svg_text_groups[0].name, 'A')
        self.assertEqual(cell.raster_text_regions[0].id, 'r1')

    def test_restore_missing_cell_keeps_groups(self):
        project, cell = _project_with_cell()
        project.svg_text_groups = [SvgTextGroup(name='A')]
        state = capture(project, cell)
        project.cells = []
        project.svg_text_groups = []
        restore(project, cell.id, state)
        self.assertEqual(len(project.svg_text_groups), 1)


class SessionRecorderTest(unittest.TestCase):
    def _recorder(self, project, cell, stack):
        return SessionRecorder(
            project, cell.id, stack,
            lambda before, after: FakeCmd(before=before, after=after))

    def test_first_record_pushes_then_merges(self):
        project, cell = _project_with_cell()
        stack = FakeStack()
        rec = self._recorder(project, cell, stack)
        project.svg_text_groups = [SvgTextGroup(name='A')]
        rec.record()
        self.assertEqual(len(stack.cmds), 1)
        cmd = stack.cmds[0]
        self.assertEqual(cmd.before, rec.open_state)
        self.assertEqual(cmd.after, capture(project, cell))
        project.svg_text_groups[0].font_size_pt = 7.0
        rec.record()
        self.assertEqual(len(stack.cmds), 1)
        self.assertEqual(cmd.after, capture(project, cell))

    def test_foreign_command_starts_new(self):
        project, cell = _project_with_cell()
        stack = FakeStack()
        rec = self._recorder(project, cell, stack)
        project.svg_text_groups = [SvgTextGroup(name='A')]
        rec.record()
        stack.push(FakeCmd())  # foreign command on top
        project.svg_text_groups[0].font_size_pt = 7.0
        rec.record()
        self.assertEqual(len(stack.cmds), 3)

    def test_no_change_does_nothing(self):
        project, cell = _project_with_cell()
        stack = FakeStack()
        rec = self._recorder(project, cell, stack)
        rec.record()
        self.assertEqual(stack.cmds, [])

    def test_no_stack(self):
        project, cell = _project_with_cell()
        rec = self._recorder(project, cell, None)
        project.svg_text_groups = [SvgTextGroup(name='A')]
        rec.record()
        self.assertTrue(rec.changed())

    def test_rebase_prevents_recording_external(self):
        project, cell = _project_with_cell()
        stack = FakeStack()
        rec = self._recorder(project, cell, stack)
        project.svg_text_groups = [SvgTextGroup(name='A')]  # external edit
        rec.rebase()
        rec.record()
        self.assertEqual(stack.cmds, [])
        self.assertTrue(rec.changed())

    def test_changed(self):
        project, cell = _project_with_cell()
        rec = self._recorder(project, cell, None)
        self.assertFalse(rec.changed())
        cell.raster_text_regions = [_region()]
        self.assertTrue(rec.changed())

    def test_open_state_override(self):
        project, cell = _project_with_cell()
        rec = self._recorder(project, cell, None)
        given = {"groups": [{"id": "x", "name": "X", "font_size_pt": 9.0,
                             "members": []}], "regions": []}
        rec2 = SessionRecorder(project, cell.id, None,
                               self._recorder(project, cell, None)._make_command,
                               open_state=given)
        self.assertEqual(rec2.open_state, given)
        self.assertIsNot(rec2.open_state, given)
        self.assertTrue(rec2.changed())
        self.assertFalse(rec.changed())


def _g(gid, name='G', pt=10.0, members=None):
    return {"id": gid, "name": name, "font_size_pt": pt,
            "members": members or []}


def _m(svg_path, key):
    return {"svg_path": svg_path, "element_key": key}


def _r(rid, group_id=None, warning=None):
    r = _region(group_id=group_id, warning=warning)
    r.id = rid
    return r.to_dict()


RASTER_IMG = {"kind": "raster", "cell_id": "c1"}
SVG_IMG = {"kind": "svg", "svg_path": "me.svg"}


class ScopedRevertRasterTest(unittest.TestCase):
    def test_regions_restored(self):
        baseline = {"groups": [], "regions": [_r('r1', group_id='g1')]}
        current = {"groups": [], "regions": [_r('r2')]}
        new, _ = scoped_revert(current, baseline, RASTER_IMG, set())
        self.assertEqual([r['id'] for r in new['regions']], ['r1'])

    def test_new_group_used_only_by_me_dropped(self):
        baseline = {"groups": [], "regions": [_r('r1')]}
        current = {"groups": [_g('new', members=[])],
                   "regions": [_r('r1', group_id='new')]}
        # After revert the region returns to baseline (ungrouped) — 'new' unused.
        new, _ = scoped_revert(current, baseline, RASTER_IMG, set())
        self.assertEqual([g['id'] for g in new['groups']], [])

    def test_new_group_used_by_other_image_kept(self):
        baseline = {"groups": [], "regions": [_r('r1')]}
        current = {"groups": [_g('new')], "regions": [_r('r1')]}
        new, _ = scoped_revert(current, baseline, RASTER_IMG, {'new'})
        self.assertEqual([g['id'] for g in new['groups']], ['new'])

    def test_unshared_group_size_restored(self):
        baseline = {"groups": [_g('g1', name='Old', pt=9.0)],
                    "regions": [_r('r1', group_id='g1')]}
        current = {"groups": [_g('g1', name='New', pt=14.0)],
                   "regions": [_r('r1', group_id='g1')]}
        new, kept = scoped_revert(current, baseline, RASTER_IMG, set())
        self.assertEqual((new['groups'][0]['name'],
                          new['groups'][0]['font_size_pt']), ('Old', 9.0))
        self.assertEqual(kept, [])

    def test_shared_group_size_kept_via_members(self):
        baseline = {"groups": [_g('g1', pt=9.0)], "regions": [_r('r1', group_id='g1')]}
        current = {"groups": [_g('g1', pt=14.0, members=[_m('other.svg', 'k')])],
                   "regions": [_r('r1', group_id='g1')]}
        new, kept = scoped_revert(current, baseline, RASTER_IMG, set())
        self.assertEqual(new['groups'][0]['font_size_pt'], 14.0)
        self.assertEqual(kept, ['G'])

    def test_shared_group_size_kept_via_other_refs(self):
        baseline = {"groups": [_g('g1', pt=9.0)], "regions": [_r('r1', group_id='g1')]}
        current = {"groups": [_g('g1', name='Big', pt=14.0)],
                   "regions": [_r('r1', group_id='g1')]}
        new, kept = scoped_revert(current, baseline, RASTER_IMG, {'g1'})
        self.assertEqual(new['groups'][0]['font_size_pt'], 14.0)
        self.assertEqual(kept, ['Big'])

    def test_deleted_baseline_group_recreated(self):
        baseline = {"groups": [_g('g1', name='Old', pt=9.0)],
                    "regions": [_r('r1', group_id='g1')]}
        current = {"groups": [], "regions": [_r('r2')]}
        new, _ = scoped_revert(current, baseline, RASTER_IMG, set())
        self.assertEqual(len(new['groups']), 1)
        self.assertEqual(new['groups'][0]['id'], 'g1')
        self.assertEqual(new['groups'][0]['members'], [])


class ScopedRevertSvgTest(unittest.TestCase):
    def test_only_this_path_memberships_reset(self):
        baseline = {"groups": [_g('g1', members=[_m('me.svg', 'a')])],
                    "regions": None}
        current = {"groups": [_g('g1', members=[_m('me.svg', 'b'),
                                              _m('other.svg', 'o')])],
                   "regions": None}
        new, _ = scoped_revert(current, baseline, SVG_IMG, set())
        members = new['groups'][0]['members']
        self.assertEqual({(m['svg_path'], m['element_key']) for m in members},
                         {('me.svg', 'a'), ('other.svg', 'o')})

    def test_new_group_only_this_path_dropped(self):
        baseline = {"groups": [], "regions": None}
        current = {"groups": [_g('new', members=[_m('me.svg', 'a')])],
                   "regions": None}
        new, _ = scoped_revert(current, baseline, SVG_IMG, set())
        self.assertEqual(new['groups'], [])

    def test_new_group_also_other_path_kept(self):
        baseline = {"groups": [], "regions": None}
        current = {"groups": [_g('new', members=[_m('me.svg', 'a'),
                                               _m('other.svg', 'o')])],
                   "regions": None}
        new, _ = scoped_revert(current, baseline, SVG_IMG, set())
        self.assertEqual(len(new['groups']), 1)
        self.assertEqual([m['element_key'] for m in new['groups'][0]['members']],
                         ['o'])  # this path's membership removed, rest kept

    def test_deleted_group_recreated_with_only_my_members(self):
        baseline = {"groups": [_g('g1', members=[_m('me.svg', 'a'),
                                               _m('other.svg', 'o')])],
                    "regions": None}
        current = {"groups": [], "regions": None}
        new, _ = scoped_revert(current, baseline, SVG_IMG, set())
        self.assertEqual(len(new['groups']), 1)
        self.assertEqual([m['element_key'] for m in new['groups'][0]['members']],
                         ['a'])

    def test_svg_regions_pass_through(self):
        state = {"groups": [], "regions": [_r('r1')]}
        new, _ = scoped_revert(state, {"groups": [], "regions": []},
                               SVG_IMG, set())
        self.assertEqual(new['regions'], state['regions'])


class ScopedRevertIdentityTest(unittest.TestCase):
    def test_identity(self):
        state = {"groups": [_g('g1', members=[_m('me.svg', 'a')])],
                 "regions": [_r('r1', group_id='g1')]}
        self.assertEqual(scoped_revert(state, state, SVG_IMG, set())[0], state)
        self.assertEqual(scoped_revert(state, state, RASTER_IMG, set())[0],
                         state)

    def test_inputs_not_mutated(self):
        import copy as _copy
        current = {"groups": [_g('g1', members=[_m('me.svg', 'b'),
                                              _m('other.svg', 'o')])],
                   "regions": [_r('r1')]}
        baseline = {"groups": [_g('g1', members=[_m('me.svg', 'a')])],
                    "regions": [_r('r2', group_id='g1')]}
        snapshot_c, snapshot_b = _copy.deepcopy(current), _copy.deepcopy(baseline)
        scoped_revert(current, baseline, SVG_IMG, {'g1'})
        scoped_revert(current, baseline, RASTER_IMG, {'g1'})
        self.assertEqual(current, snapshot_c)
        self.assertEqual(baseline, snapshot_b)


class SessionCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtCore import QCoreApplication
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_undo_redo_cycle(self):
        from PyQt6.QtGui import QUndoStack
        project, cell = _project_with_cell()
        calls = []
        rec = SessionRecorder(
            project, cell.id, None,
            lambda before, after: TextMatchSessionCommand(
                project, cell.id, before, after, calls.append))
        open_state = rec.open_state
        project.svg_text_groups = [SvgTextGroup(name='A', font_size_pt=9.0)]
        cell.raster_text_regions = [_region(id='r1')]
        after = capture(project, cell)
        stack = QUndoStack()
        stack.push(TextMatchSessionCommand(project, cell.id, open_state, after,
                                           calls.append))
        # First redo was a no-op: live state is still `after`.
        self.assertEqual(project.svg_text_groups[0].name, 'A')
        self.assertEqual(calls, [])
        stack.undo()
        self.assertEqual(project.svg_text_groups, [])
        self.assertEqual(cell.raster_text_regions, [])
        self.assertEqual(len(calls), 1)
        stack.redo()
        self.assertEqual(project.svg_text_groups[0].name, 'A')
        self.assertEqual(cell.raster_text_regions[0].id, 'r1')
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
