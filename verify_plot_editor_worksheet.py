"""Non-UI checks for the Plot Editor worksheet model (no Qt)."""

import unittest

from src.plot_editor import worksheet as wsmod
from src.plot_editor.worksheet import (Column, Worksheet,
                                       WorksheetLimitError, column_letters,
                                       format_cell, parse_cell, parse_tsv,
                                       to_tsv)


def snapshot(ws):
    return [(c.designation, c.long_name, c.units, c.comments,
             list(c.values)) for c in ws.columns]


class LetterAndCellTests(unittest.TestCase):

    def test_column_letters(self):
        self.assertEqual(column_letters(0), 'A')
        self.assertEqual(column_letters(25), 'Z')
        self.assertEqual(column_letters(26), 'AA')
        self.assertEqual(column_letters(701), 'ZZ')
        self.assertEqual(column_letters(702), 'AAA')

    def test_parse_cell(self):
        self.assertEqual(parse_cell(''), None)
        self.assertEqual(parse_cell('   '), None)
        self.assertEqual(parse_cell('3'), 3.0)
        self.assertEqual(parse_cell('  -2.5e-3  '), -0.0025)
        self.assertEqual(parse_cell('.5'), 0.5)
        self.assertEqual(parse_cell('1e999'), '1e999')
        self.assertEqual(parse_cell('nan'), 'nan')
        self.assertEqual(parse_cell('inf'), 'inf')
        self.assertEqual(parse_cell('1_000'), '1_000')
        self.assertEqual(parse_cell('0x10'), '0x10')
        self.assertEqual(parse_cell('abc'), 'abc')
        self.assertEqual(parse_cell('  abc  '), '  abc  ')

    def test_format_cell_roundtrip(self):
        for v in (0.1, 1 / 3, -2.5e-300, 42.0):
            self.assertEqual(float(format_cell(v)), v)
        self.assertEqual(format_cell(2.0), '2')
        self.assertEqual(format_cell(1e16), repr(1e16))
        self.assertEqual(format_cell(None), '')
        self.assertEqual(format_cell('x'), 'x')


class TsvTests(unittest.TestCase):

    def test_roundtrip(self):
        rows = [['a', '1', ''], ['x\ty', 'q"q', 'line\nbreak']]
        self.assertEqual(parse_tsv(to_tsv(rows)), rows)

    def test_ragged_padded(self):
        self.assertEqual(parse_tsv('a\tb\nc'), [['a', 'b'], ['c', '']])

    def test_crlf_and_trailing_newline(self):
        self.assertEqual(parse_tsv('a\r\nb\n'), [['a'], ['b']])
        self.assertEqual(parse_tsv('a\rb'), [['a'], ['b']])

    def test_empty(self):
        self.assertEqual(parse_tsv(''), [])


class WorksheetTests(unittest.TestCase):

    def test_defaults(self):
        ws = Worksheet()
        self.assertEqual([ws.header_label(i) for i in range(2)],
                         ['A(X)', 'B(Y)'])
        self.assertEqual([c.designation for c in ws.columns], ['X', 'Y'])
        self.assertEqual(ws.column_count, 2)
        self.assertEqual(ws.row_count, 0)
        self.assertEqual(ws.display_rows(),
                         wsmod.META_ROWS + wsmod.MIN_DATA_ROWS)
        self.assertEqual(ws.header_label(0), 'A(X)')
        self.assertEqual(ws.header_label(1), 'B(Y)')
        self.assertEqual(ws.grid_text(0, 0), '')

    def test_set_block_meta_and_data(self):
        ws = Worksheet()
        rect = ws.set_block(0, 0,
                            [['Speed', 'm/s'], ['Time', 's'], ['1', '2']])
        self.assertEqual(rect, (0, 0, 1, 2))
        self.assertEqual(ws.columns[0].long_name, 'Speed')
        self.assertEqual(ws.columns[1].units, 's')
        self.assertEqual(ws.value(0, 0), None)
        self.assertEqual(ws.grid_text(0, 3), '')

    def test_set_block_data_rows(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1', 'x'], ['2.5', '3']])
        self.assertEqual(ws.value(0, 0), 1.0)
        self.assertEqual(ws.value(1, 0), 'x')
        self.assertEqual(ws.value(1, 1), 3.0)
        self.assertEqual(ws.row_count, 2)
        self.assertEqual(ws.grid_text(0, 3), '1')

    def test_set_block_appends_columns(self):
        ws = Worksheet()
        ws.set_block(2, 3, [['9'], ['8']])
        self.assertEqual(ws.column_count, 3)
        self.assertEqual(ws.columns[2].designation, 'Y')
        self.assertEqual(ws.header_label(2), 'C(Y)')
        self.assertEqual(ws.value(2, 0), 9.0)

    def test_column_names_are_positional(self):
        ws = Worksheet()
        ws.insert_columns(0, 1)
        self.assertEqual([ws.header_label(i) for i in range(3)],
                         ['A(Y)', 'B(X)', 'C(Y)'])
        ws.set_block(2, 3, [['9']])
        self.assertEqual(ws.value(2, 0), 9.0)
        self.assertEqual(ws.columns[1].designation, 'X')
        ws.remove_columns([0])
        self.assertEqual([ws.header_label(i) for i in range(2)],
                         ['A(X)', 'B(Y)'])
        self.assertEqual(ws.value(1, 0), 9.0)
        ws.undo()
        self.assertEqual([ws.header_label(i) for i in range(3)],
                         ['A(Y)', 'B(X)', 'C(Y)'])

    def test_fill_and_clear(self):
        ws = Worksheet()
        ws.fill((0, 3, 1, 5), '7')
        self.assertEqual([ws.value(0, r) for r in range(3)],
                         [7.0] * 3)
        self.assertEqual(ws.value(1, 2), 7.0)
        ws.clear([(0, 3, 0, 4)])
        self.assertEqual(ws.value(0, 0), None)
        self.assertEqual(ws.value(0, 2), 7.0)

    def test_insert_remove_rows_undo(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1'], ['2'], ['3']])
        before = snapshot(ws)
        ws.insert_rows(1, 2)
        self.assertEqual([ws.value(0, r) for r in range(5)],
                         [1.0, None, None, 2.0, 3.0])
        ws.undo()
        self.assertEqual(snapshot(ws), before)
        ws.redo()
        self.assertEqual(ws.value(0, 2), None)
        ws.remove_rows(0, 4)
        self.assertEqual([ws.value(0, r) for r in range(3)],
                         [3.0, None, None])
        self.assertEqual(ws.row_count, 1)
        ws.undo()
        self.assertEqual(ws.row_count, 5)

    def test_remove_rows_trims_tail(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1'], [''], ['3']])
        self.assertEqual(ws.row_count, 3)
        before = snapshot(ws)
        ws.remove_rows(2, 1)
        self.assertEqual([ws.value(0, r) for r in range(3)],
                         [1.0, None, None])
        self.assertEqual(ws.row_count, 1)
        ws.undo()
        self.assertEqual(snapshot(ws), before)

    def test_insert_remove_columns_undo(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1', '2']])
        before = snapshot(ws)
        ws.insert_columns(1, 2)
        self.assertEqual(ws.column_count, 4)
        self.assertEqual([c.designation for c in ws.columns[1:3]],
                         ['Y', 'Y'])
        ws.undo()
        self.assertEqual(snapshot(ws), before)
        ws.redo()
        ws.remove_columns([1, 2])
        self.assertEqual(snapshot(ws), before)
        ws.undo()
        self.assertEqual(ws.column_count, 4)

    def test_remove_all_columns_guard(self):
        ws = Worksheet()
        before = snapshot(ws)
        with self.assertRaises(ValueError):
            ws.remove_columns([0, 1])
        self.assertEqual(snapshot(ws), before)
        self.assertFalse(ws.can_undo)

    def test_set_designation(self):
        ws = Worksheet()
        ws.set_designation([1], 'xErr')
        self.assertEqual(ws.columns[1].designation, 'xErr')
        self.assertEqual(ws.header_label(1), 'B(xEr±)')
        ws.set_designation([1], 'Disregard')
        self.assertEqual(ws.header_label(1), 'B')
        with self.assertRaises(ValueError):
            ws.set_designation([0], 'bogus')
        ws.undo()
        ws.undo()
        self.assertEqual(ws.columns[1].designation, 'Y')

    def test_limits_leave_state_unchanged(self):
        ws = Worksheet()
        before = snapshot(ws)
        with self.assertRaises(WorksheetLimitError):
            ws.set_block(0, 0, [['x'] * 100] * (wsmod.MAX_PASTE_CELLS // 50))
        with self.assertRaises(WorksheetLimitError):
            ws.insert_columns(0, wsmod.MAX_COLUMNS)
        self.assertEqual(snapshot(ws), before)
        self.assertFalse(ws.can_undo)

    def test_noop_records_no_history(self):
        ws = Worksheet()
        self.assertIsNone(ws.set_block(0, 3, [['']]))
        self.assertIsNone(ws.fill((0, 3, 0, 3), ''))
        self.assertIsNone(ws.clear([(0, 3, 0, 3)]))
        self.assertIsNone(ws.insert_rows(0, 2))
        self.assertIsNone(ws.remove_rows(0, 2))
        self.assertIsNone(ws.remove_columns([]))
        self.assertFalse(ws.can_undo)

    def test_redo_cleared_by_new_edit(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1']])
        ws.undo()
        self.assertTrue(ws.can_redo)
        ws.set_block(0, 3, [['2']])
        self.assertFalse(ws.can_redo)

    def test_history_limit(self):
        ws = Worksheet()
        for i in range(wsmod.HISTORY_LIMIT + 10):
            ws.set_block(0, 3 + i, [[str(i)]])
        n = 0
        while ws.can_undo:
            ws.undo()
            n += 1
        self.assertEqual(n, wsmod.HISTORY_LIMIT)

    def test_listener_events(self):
        ws = Worksheet()
        events = []
        ws.add_listener(events.append)
        ws.set_block(0, 3, [['1']])
        self.assertEqual(events[-2][0], 'cells')
        self.assertEqual(events[-1], ('history',))
        events.clear()
        ws.insert_columns(2, 1)
        self.assertEqual(events, [('columns_inserted', 2, 1, True),
                                  ('history',)])
        events.clear()
        ws.undo()
        self.assertEqual(events, [('columns_removed', 2, 1),
                                  ('history',)])
        events.clear()
        ws.redo()
        self.assertEqual(events, [('columns_inserted', 2, 1, True),
                                  ('history',)])

    def test_no_reset_events_ever(self):
        ws = Worksheet()
        events = []
        ws.add_listener(events.append)
        ws.set_block(0, 3, [['1', '2']])
        ws.set_block(5, 3, [['x']])
        ws.insert_rows(0, 1)
        ws.remove_rows(0, 1)
        ws.insert_columns(1, 1)
        ws.remove_columns([0])
        ws.set_designation([0], 'Label')
        for _ in range(6):
            ws.undo()
        for _ in range(6):
            ws.redo()
        self.assertNotIn('reset', [e[0] for e in events])

    def test_row_events_undo_redo(self):
        ws = Worksheet()
        ws.set_block(0, 3, [['1'], ['2']])
        events = []
        ws.add_listener(events.append)
        ws.insert_rows(1, 2)
        self.assertEqual(events, [('rows_inserted', 1, 2), ('history',)])
        events.clear()
        ws.undo()
        self.assertEqual(events, [('rows_removed', 1, 2), ('history',)])
        events.clear()
        ws.remove_rows(0, 1)
        self.assertEqual(events, [('rows_removed', 0, 1), ('history',)])
        events.clear()
        ws.undo()
        self.assertEqual(events, [('rows_inserted', 0, 1), ('history',)])

    def test_column_remove_runs_events(self):
        ws = Worksheet()
        ws.insert_columns(2, 2)
        self.assertEqual(ws.column_count, 4)
        events = []
        ws.add_listener(events.append)
        ws.remove_columns([0, 2])
        self.assertEqual(events, [('columns_removed', 2, 1),
                                  ('columns_removed', 0, 1),
                                  ('history',)])
        events.clear()
        ws.undo()
        self.assertEqual(events, [('columns_inserted', 0, 1, True),
                                  ('columns_inserted', 2, 1, True),
                                  ('history',)])

    def test_paste_append_events_not_animated(self):
        ws = Worksheet()
        events = []
        ws.add_listener(events.append)
        ws.set_block(3, 3, [['1']])
        self.assertEqual(events, [('columns_inserted', 2, 2, False),
                                  ('cells', 3, 3, 3, 3), ('history',)])
        events.clear()
        ws.undo()
        self.assertEqual(events, [('columns_removed', 2, 2),
                                  ('history',)])

    def test_header_event(self):
        ws = Worksheet()
        ws.set_designation([0], 'Label')
        events = []
        ws.add_listener(events.append)
        ws.set_designation([0], 'Y')
        ws.undo()
        self.assertEqual(events, [('header', 0, 0), ('history',),
                                  ('header', 0, 0), ('history',)])

    def test_cells_event_rect(self):
        ws = Worksheet()
        events = []
        ws.add_listener(events.append)
        ws.set_block(0, 3, [['1', '2']])
        self.assertEqual(events[0], ('cells', 0, 3, 1, 3))

    def test_undo_restores_exact_state(self):
        ws = Worksheet()
        ws.set_block(0, 0, [['Ln', 'U']])
        ws.set_block(0, 3, [['1', 'a'], ['2', 'b']])
        ws.set_designation([0], 'Label')
        ws.insert_columns(2, 1)
        ws.remove_rows(0, 1)
        before = snapshot(ws)
        for _ in range(3):
            ws.undo()
        self.assertNotEqual(snapshot(ws), before)
        for _ in range(3):
            ws.redo()
        self.assertEqual(snapshot(ws), before)
        for _ in range(5):
            ws.undo()
        self.assertEqual(snapshot(ws), snapshot(Worksheet()))

    def test_labels_and_meta_labels(self):
        self.assertEqual(wsmod.META_LABELS,
                         ('Long Name', 'Units', 'Comments'))


if __name__ == '__main__':
    unittest.main()
