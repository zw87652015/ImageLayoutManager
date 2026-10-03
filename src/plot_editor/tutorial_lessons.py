"""Qt-free lesson model for the Plot Editor guided tutorials.

``Step.ready`` predicates receive ``(tab, ctx)`` — *tab* is the live
``PlotTab`` (or any object exposing the same ``worksheet`` / ``plot`` /
``overrides`` / ``path`` / ``dirty`` attributes in tests) and *ctx* is a
plain dict the controller keeps per lesson for lazy before/after
baselines. Everything here is import- and test-safe without a
QApplication.

i18n keys are written out literally so the unused-key scan in
``verify_plot_editor_i18n`` sees them.
"""

import math
from dataclasses import dataclass
from typing import Callable, Optional

from .worksheet import Column, Worksheet

Ready = Callable[[object, dict], bool]


@dataclass(frozen=True)
class Step:
    key: str
    title_key: str
    body_key: str
    target: str = ''          # resolved by the UI layer; '' = no highlight
    action: str = ''          # guided-action key; '' = no action button
    ready: Optional[Ready] = None  # None = always ready


@dataclass(frozen=True)
class Lesson:
    key: str
    title_key: str
    summary_key: str
    steps: tuple
    setup: str = 'empty'      # 'empty' tab | 'plotted' sample tab


def fill_sample_data(ws: Worksheet) -> None:
    """Undoably fill the sheet with the tutorial's three-column sample:
    A = X (0–5), B and C = Y series with Long Name/Units metadata."""
    ws.replace_all([
        Column('X', 'Time', 's', '', [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        Column('Y', 'Signal A', 'mV', '',
               [0.0, 1.1, 1.9, 3.2, 4.1, 4.9]),
        Column('Y', 'Signal B', 'mV', '',
               [0.4, 0.8, 1.6, 2.4, 3.0, 3.6]),
    ], label='Edit')


STYLING_Y_COUNT = 8


def fill_styling_sample(ws: Worksheet) -> None:
    """Undoably fill the sheet for the styling lesson: one X column
    (0-10) and eight Y series so every colour theme shows its full
    palette on screen."""
    xs = [float(i) for i in range(11)]
    columns = [Column('X', 'Time', 's', '', xs)]
    for k in range(1, STYLING_Y_COUNT + 1):
        values = [round(0.8 * (k - 1) + 0.5 * math.sin(
            0.6 * x + 0.7 * (k - 1)), 2) for x in xs]
        columns.append(Column('Y', f'Signal {k}', 'mV', '', values))
    ws.replace_all(columns, label='Edit')


# ── ready predicates (Qt-free) ────────────────────────────────────────────

def _numeric_count(column) -> int:
    return sum(1 for v in column.values
               if isinstance(v, (int, float)) and not isinstance(v, bool))


def _has_xy_data(tab, ctx) -> bool:
    """At least one X and one Y column carrying ≥3 numeric values."""
    xs = [c for c in tab.worksheet.columns
          if c.designation == 'X' and _numeric_count(c) >= 3]
    ys = [c for c in tab.worksheet.columns
          if c.designation == 'Y' and _numeric_count(c) >= 3]
    return bool(xs) and bool(ys)


def _has_plot(tab, ctx) -> bool:
    return tab.plot is not None


def _formatting_changed(tab, ctx) -> bool:
    return not tab.overrides.is_empty()


def _has_title(tab, ctx) -> bool:
    return bool(getattr(tab, 'plot_title', '').strip())


def _is_saved(tab, ctx) -> bool:
    return tab.path is not None and not tab.dirty


def _theme_changed(tab, ctx) -> bool:
    """Lazy baseline: the first poll records the palette; ready once the
    current choice differs (a user pick without the guided path counts)."""
    if 'palette0' not in ctx:
        ctx['palette0'] = tab.overrides.palette
        return False
    return tab.overrides.palette != ctx['palette0']


def _reset_after_edit(tab, ctx) -> bool:
    """Formatting is pristine again AND was non-pristine earlier in this
    lesson — a fresh-from-setup tab must not satisfy the step."""
    if not tab.overrides.is_empty():
        ctx['formatting_was_dirty'] = True
        return False
    return bool(ctx.get('formatting_was_dirty'))


LESSONS = (
    Lesson('first_plot',
           'tut_lessons_first_plot_title',
           'tut_lessons_first_plot_summary',
           (
               Step('intro', 'tut_fp_intro_title', 'tut_fp_intro_body'),
               Step('enter_data', 'tut_fp_enter_data_title',
                    'tut_fp_enter_data_body', target='worksheet',
                    action='fill_sample', ready=_has_xy_data),
               Step('roles', 'tut_fp_roles_title', 'tut_fp_roles_body',
                    target='worksheet_header', ready=_has_xy_data),
               Step('plot', 'tut_fp_plot_title', 'tut_fp_plot_body',
                    target='plot_button', action='plot_sample',
                    ready=_has_plot),
               Step('edit_in_place', 'tut_fp_edit_in_place_title',
                    'tut_fp_edit_in_place_body', target='canvas',
                    ready=_formatting_changed),
               Step('title', 'tut_fp_title_title', 'tut_fp_title_body',
                    target='title_field', ready=_has_title),
               Step('save', 'tut_fp_save_title', 'tut_fp_save_body',
                    target='action_save', ready=_is_saved),
               Step('finish', 'tut_fp_finish_title',
                    'tut_fp_finish_body'),
           ),
           setup='empty'),
    Lesson('styling',
           'tut_lessons_styling_title',
           'tut_lessons_styling_summary',
           (
               Step('intro', 'tut_sty_intro_title', 'tut_sty_intro_body'),
               Step('theme', 'tut_sty_theme_title', 'tut_sty_theme_body',
                    target='canvas', ready=_theme_changed),
               Step('presets', 'tut_sty_presets_title',
                    'tut_sty_presets_body', target='style_presets'),
               Step('manager', 'tut_sty_manager_title',
                    'tut_sty_manager_body', target='action_style'),
               Step('restore', 'tut_sty_restore_title',
                    'tut_sty_restore_body', target='canvas'),
               Step('reset', 'tut_sty_reset_title', 'tut_sty_reset_body',
                    target='reset_all', ready=_reset_after_edit),
               Step('finish', 'tut_sty_finish_title',
                    'tut_sty_finish_body'),
           ),
           setup='plotted'),
)

LESSON_ORDER = tuple(lesson.key for lesson in LESSONS)
LESSONS = {lesson.key: lesson for lesson in LESSONS}
