### User Input

See @[afl-macos-mockup.html] and @[afl-windows-mockup.html] . Learn from their UI design. (Only the UI design, not the real functions) Then revise the current design of my app to make it more beautiful, more elegant, and more consistent. Pay attention to the following things:
1. canvas background
2. Null cell placeholder has dashed border lines
3. The color contrast between selected and unselected things is significant
4.  Layers Pannel is well organized, with collapsable arrows.
5. Layers pannel's items has beautiful highlight effect.
6. Layers pannel's items has a thumbnail to tell the user what it is or is empty.
7. Buttons in the Toolbar are elegantly designed using pure-line icons and consistently aligned positions with the text.
8. The Tab title box has consistent accent color with the whole program.
9. Rounded corners.
10. Functional areas and pannels have beautiful borders.
11. Dark/Light switch and the Export button has a perfect place and design.
12. Adjustment pannel (the right pannel) is well-designed and organized.
13. The status bar is concise.
14. Behavious and animations when switched between light/dark modes.
Bottom line: The code should produce adapted but still consistent UI and UX on MacOS and Windows. Differences are tolarable, but they should be due to the platform issues, not the design issues in the code.

### Planner Response

This is a major redesign. Let me first understand the target aesthetic by reading both mockups, then the current theming code, then propose a phased plan before making sweeping changes.

*Viewed [afl-macos-mockup.html](file:///e:/Documents/Codes/ImageLayoutManager/afl-macos-mockup.html) *

*Listed directory [app](file:///e:/Documents/Codes/ImageLayoutManager/src/app) *

*Viewed [theme.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py) *

### Planner Response

This is a large, multi-surface redesign spanning [theme.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:0:0-0:0), [layers_panel.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/layers_panel.py:0:0-0:0), [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:0:0-0:0) (toolbar), [inspector.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/inspector.py:0:0-0:0), [canvas_view.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/canvas_view.py:0:0-0:0), [cell_item.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/cell_item.py:0:0-0:0), and new SVG assets. If I try everything in one edit pass I'll almost certainly break the app.

Let me propose a **phased plan** mapped to your 14 items, then confirm where to start. Each phase is independently runnable — you can verify after each.

## Proposed phases

### Phase 1 — Design tokens (foundation)
Rewrite `@/Users/.../src/app/theme.py` to expose a **full token set** (matching the mockup CSS variables): `chrome`, `panel`, `panel-alt`, `canvas-bg`, `surface`, `border`, `border-strong`, `divider`, `text/sec/tert`, `label-caps`, `hover`, `active`, `accent` (#0891B2 light / #22D3EE dark), `accent-tint`, `accent-ring`, `danger`, plus radii (6/4/3) and shadow presets. All later phases read from this single source. Covers items **#3, #9, #14** (crossfade animation via `QGraphicsOpacityEffect` on a top overlay during theme swap).

### Phase 2 — Toolbar + theme segmented + export button
Items **#7, #8, #11**. Switch toolbar to **pure-line SVG icons** (ship 12 new monoline SVGs in `assets/icons/`), consistent 30 px button height, baseline-aligned text. Add a **segmented Light/Dark control** (custom widget) on the right, then a primary-styled **Export** button.

### Phase 3 — Canvas background, placeholders, selection
Items **#1, #2, #3**. Dot-grid QGraphicsScene background (radial-gradient dots 20 px pitch using `drawBackground`), dashed-border placeholder styling in [cell_item.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/cell_item.py:0:0-0:0), stronger selection contrast (accent ring + 3 px glow, matching `--accent-ring`).

### Phase 4 — Layers panel overhaul
Items **#4, #5, #6**. Replace `QTreeWidget` styling with a custom `QStyledItemDelegate` that renders:
- row/group collapsible headers with animated chevron
- thumbnail (22×22): dashed-border if empty, mini-preview pixmap if filled
- selection: accent-tint background + 2 px left accent bar
- hover action buttons (visibility toggle)

### Phase 5 — Inspector redesign
Item **#12**. Collapsible sections with uppercase caps headers and rotating chevrons, 72 px label column + input column grid, unit suffix spans, consistent 24 px input height, focus ring using `--accent-ring`.

### Phase 6 — Status bar + misc polish
Item **#13**. Compact 24 px status bar, monospaced numerics, thin dividers; plus rounded corners (#9) on main panels (`QFrame` containers with stylesheet `border-radius`). Rounded window corners on macOS come free; on Windows 11 they come from OS.

### Phase 7 — Theme switch animation
Item **#14**. Fade overlay `QWidget` with `QPropertyAnimation` on opacity during theme swap, plus CSS `transition`-equivalent via `QVariantAnimation` for accent color properties on key widgets.

## Clarifying questions before I start

*Asked user a question*

### Planner Response

Phase 1 only — rewriting [theme.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:0:0-0:0) with the mockup's full token system, preserving existing public API ([build_palette](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:301:0-306:18), [get_stylesheet](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:309:0-316:82), [get_layers_tree_stylesheet](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:319:0-320:69)) and adding `get_tokens(theme)` so later phases (canvas grid, placeholder dashes, layer thumbnails) can read token colors programmatically.

*Edited relevant file*

### User Input

I'm interrupting you because I realized that the only thing you shouldn't change is the main plotting area. They should remain rectanglular, no rounded corners. And since it is coordinates-sensitive, the core things for creating an academic figure shouldn't be touched. Continue

### Planner Response

Understood — noted. **Plotting area cells stay rectangular and geometry-exact**; I'll only touch the *canvas background* (dot grid colour, scene bg) and non-coordinate visuals (dashed stroke colour on empty cells via the existing `border_pen`). No radii on cells, no layout math changes.

Continuing Phase 1 — replacing the rest of [theme.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:0:0-0:0):

*Edited relevant file*

### Planner Response

Verify the app still launches with the new theme:

*User accepted the command `& D:/anaconda3/envs/imagelayout/python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt6.QtWidgets import QApplication; app=QApplication([]); from src.app.theme import build_palette, get_stylesheet, get_layers_tree_stylesheet, get_tokens, LIGHT, DARK; app.setPalette(build_palette(LIGHT)); app.setStyleSheet(get_stylesheet(LIGHT)); _ = get_layers_tree_stylesheet(DARK); t=get_tokens(LIGHT); assert t['accent']=='#0891B2'; from src.app.main_window import MainWindow; w=MainWindow(); print('OK, accent=', t['accent'])"`*

### Planner Response

Phase 1 complete. The app launches cleanly with the new tokenised theme, light/dark palettes, and accent `#0891B2` (light) / `#22D3EE` (dark).

## What changed (Phase 1)

- **`@/Users/.../src/app/theme.py:34-105`** — `_TOKENS_LIGHT` / `_TOKENS_DARK`: full mockup token set (surfaces, borders, text, accent ramp, hover/active rgba, placeholder, grid_line, radii). Names match the mockup CSS variables 1:1.
- **`@/Users/.../src/app/theme.py:108-126`** — [_palette_tokens_to_roles()](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:108:0-125:5) maps tokens → `QPalette` roles.
- **`@/Users/.../src/app/theme.py:134-360`** — single `_QSS_TEMPLATE` using `%(name)s` substitution. New additions over the old stylesheet:
  - `QToolBar QToolButton:checked` → accent-tinted (for toggleable actions)
  - `QToolBar::separator` (needed for Phase 2 toolbar groups)
  - `QPushButton[accent="true"]` → primary/export button styling (Phase 2 consumers will set this property)
  - `QTabWidget` / `QTabBar` → accent-tinted selected tab (item #8)
  - Refined `QMenu`, `QComboBox QAbstractItemView`, `QToolTip`, scrollbar radii
- **`@/Users/.../src/app/theme.py:362-382`** — layer tree template keyed on accent_tint (item #5 preview).
- **`@/Users/.../src/app/theme.py:387-415`** — public API unchanged + new [get_tokens(theme)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:386:0-392:65).

## Preserved (per your constraint)
- Public API signatures: [build_palette](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:395:0-402:18), [get_stylesheet](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:405:0-410:41), [get_layers_tree_stylesheet](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:413:0-414:52) — no call sites need updating.
- **No touches to [cell_item.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/cell_item.py:0:0-0:0), [canvas_view.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/canvas_view.py:0:0-0:0), [canvas_scene.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/canvas_scene.py:0:0-0:0), or layout engine.** The plotting area cells remain geometry-exact and coordinate-sensitive.

## What you'll see right now
Relaunching the app gives you:
- New cyan accent (`#0891B2` light, `#22D3EE` dark) across all selections, focus rings, tabs, toolbar-pressed states, menu highlights
- Softer panel/chrome/divider greyscale matching macOS/Windows 11 aesthetic
- Rounded 4–6 px corners on inputs, buttons, menus, tabs, scrollbar thumbs (panels only — **not on canvas cells**)
- Hover/active as translucent rgba overlays (composing correctly over any surface)

## Pending phases
Phase 2 (toolbar line-icons + segmented theme switch + Export primary button), Phase 4 (layers panel thumbnails & custom delegate), Phase 5 (inspector collapsible sections), Phase 6 (status bar & rounded panel frames), Phase 7 (theme-switch crossfade) — awaiting your go-ahead per the sequential plan.

📜 Log Entry
- Date: 2026-04-20
- Type: design-discuss
- Module: src/app/theme.py
- Summary: Rewrote theme as token-based system matching redesign mockups; added get_tokens() for programmatic access
- Reason: Replace ad-hoc hex values spread across QSS with a single source-of-truth token dict to enable systematic phased UI refresh
- Alternatives: Keep duplicated light/dark QSS strings (rejected: impossible to keep in sync during 7-phase redesign)
- Risk/Follow-up: Later phases (toolbar icons, layers delegate, canvas grid) will consume get_tokens(); constraint: never restyle canvas cell geometry
- Breaking: no
- Tests Needed: no

*Edited relevant file*

*Viewed [main.py](file:///e:/Documents/Codes/ImageLayoutManager/main.py) *

*User accepted the command `& D:/anaconda3/envs/imagelayout/python.exe e:/Documents/Codes/ImageLayoutManager/main.py`*

*User accepted the command `& D:/anaconda3/envs/imagelayout/python.exe e:/Documents/Codes/ImageLayoutManager/main.py`*

### User Input

Noticed a bug. I opened a .figlayout and closed it. Then when I was opening the same file again, there will be multiple tabs occuring with the number of times I opened that file + 1. Fix the bug first 

*Found code context*

*Grep searched codebase*

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

*Grep searched codebase*

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

*Grep searched codebase*

*Grep searched codebase*

*Grep searched codebase*

*Grep searched codebase*

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

### Planner Response

## Root cause

[_remove_tab](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:761:4-778:35) deletes the tab via `QTabWidget.removeTab(idx)`. Qt internally picks a new current tab and **synchronously emits `currentChanged`**, which runs [_on_tab_changed](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:691:4-697:31) → [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) and **connects all per-tab signals** on the remaining tab. Then [_remove_tab](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:761:4-778:35) continues and calls [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) *again* explicitly — which connects **every per-tab signal a second time**.

After that, `scene.project_file_dropped` is connected to [_on_project_file_dropped](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:2196:4-2205:78) **twice**, so dropping a `.figlayout` creates **2 new tabs** per drop. Closing and re-dropping again makes it 3, then 4… matching "number of times I opened that file + 1".

## Fix

Block `QTabWidget` signals around `removeTab()` so the duplicate cascade doesn't fire; the explicit [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) below remains the single source of activation.

*Edited relevant file*

### Planner Response

## Summary

### Root cause
In `@/Users/.../src/app/main_window.py:_remove_tab`, `QTabWidget.removeTab()` synchronously emits `currentChanged`, which fires [_on_tab_changed](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:691:4-697:31) → [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) and connects all per-tab scene/view/undo signals. [_remove_tab](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:761:4-788:35) then explicitly calls [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) again, connecting the exact same signals a **second** time. Each subsequent close-and-reopen cycle adds another connection, so `scene.project_file_dropped` ends up triggering [_on_project_file_dropped](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:2564:4-2572:78) N+1 times and spawning N+1 tabs per drop — precisely the "number of times I opened that file + 1" symptom.

### Fix
`@/Users/.../src/app/main_window.py:762-789` — wrap `self.tab_widget.removeTab(idx)` in `blockSignals(True/False)`. The explicit [_activate_tab(new_idx)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:640:4-689:47) below remains the single point of (re)activation and signal connection.

### Notes
- Minimal upstream fix (single new statement pair), no behaviour change for drag-drop, open-project, close, new-tab flows other than eliminating the duplicate connection.
- No test added — reproducing this requires Qt signal/drop plumbing; the comment block in [_remove_tab](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:761:4-788:35) documents why the `blockSignals` is required so the next maintainer won't remove it.

📜 Log Entry
- Date: 2026-04-20
- Type: tech-debt
- Module: src/app/main_window.py
- Summary: Fix duplicate tab spawn on reopen: block QTabWidget.currentChanged during removeTab to prevent double signal connection
- Reason: Qt removeTab synchronously emits currentChanged which re-activated the new current tab before the explicit _activate_tab call, doubling every per-tab signal connection per close/reopen cycle
- Alternatives: Make _activate_tab idempotent via disconnect-before-connect on the SAME tab (rejected: more code, easier to get wrong); let Qt's cascade handle activation and drop explicit call (rejected: relies on Qt emitting currentChanged even when no tabs remain, edge-cases)
- Risk/Follow-up: If future code relies on currentChanged during removeTab, the block may hide it — search removeTab call sites before similar patterns
- Breaking: no
- Tests Needed: no

*User accepted the command `& D:/anaconda3/envs/imagelayout/python.exe e:/Documents/Codes/ImageLayoutManager/main.py`*

### User Input

Continue to phase 2

### Planner Response

Let me survey the current toolbar construction and existing icon assets first.

*Grep searched codebase*

*Listed directory [assets](file:///e:/Documents/Codes/ImageLayoutManager/assets) *

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

*Grep searched codebase*

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

### User Input

continue.

### Planner Response

Continuing Phase 2. I'll build 4 things: icon library, segmented control widget, theme QSS hooks, and wire it all into the toolbar.

### Step 1 — Icon library (`src/app/icons.py`)

*Edited relevant file*

### Planner Response

### Step 2 — `ThemeSegmented` widget

*Edited relevant file*

### Planner Response

### Step 3 — Theme QSS hooks (primary QToolButton + segmented styling)

*Edited relevant file*

### Planner Response

### Step 4 — Wire into [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:0:0-0:0)

*Viewed [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py) *

*Edited relevant file*

### Planner Response

Now initialise the `_themed_actions` map before [_setup_ui](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:216:4-544:58) runs:

*Edited relevant file*

### Planner Response

Now swap the toolbar icon assignments to use themed icons (undo/redo/new/open/save):

*Edited relevant file*

*Edited relevant file*

### Planner Response

Now the auto-layout group, plus the toolbar-right area (export + segmented):

*Edited relevant file*

### Planner Response

Now the right-side of the toolbar — replace the old export button + theme action with a stretch spacer, segmented control, and primary export:

*Edited relevant file*

### Planner Response

Fix the ugly `QSizePolicy.Policy` workaround:

*Edited relevant file*

*Edited relevant file*

### Planner Response

Now add `_register_themed_action` + `_refresh_toolbar_icons`, wire into [_apply_theme](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:799:4-806:35), and clean up [_update_theme_labels](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:836:4-842:71):

*Edited relevant file*

### Planner Response

Now verify: [retranslate_ui](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:921:4-969:42) likely also references `_theme_toolbar_action` — let's check:

*Grep searched codebase*

### Planner Response

All stale references cleaned. Launch test:

*User accepted the command `& D:/anaconda3/envs/imagelayout/python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt6.QtWidgets import QApplication; app=QApplication([]); from src.app.main_window import MainWindow; w=MainWindow(); w._apply_theme('dark'); w._apply_theme('light'); print('OK')"`*

### Planner Response

App launches cleanly, toggles light↔dark ↔ light without errors. Phase 2 complete.

## Summary — Phase 2 delivered

### New files
- **`@/Users/.../src/app/icons.py`** — 11 pure-line SVG icons (undo/redo/new/open/save/cell_labels/row_labels/auto_layout/export/sun/moon) ported from the mockup. [make_icon(name, color, size, dpr=2)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/icons.py:85:0-105:20) renders a crisp HiDPI `QIcon` with any stroke colour.
- **`@/Users/.../src/app/theme_segmented.py`** — [ThemeSegmented](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme_segmented.py:19:0-91:37) pill widget with sun/moon glyphs; emits `themeChanged("light"/"dark")`. Exposes [set_theme()](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme_segmented.py:54:4-61:42) (silent update) and [refresh_icons(active, inactive)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme_segmented.py:63:4-74:68).

### [theme.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:0:0-0:0)
Added two new QSS blocks keyed on Qt properties so no programmatic styling is needed:
- `QToolButton[primary="true"]` — solid-accent pill for the toolbar Export button, with hover / press / checked states.
- `QFrame#themeSegmented` + `QToolButton[segmentedButton="true"]` — the pill background + inner buttons, with the active one using `surface` + `accent` text per the mockup.

### [main_window.py](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:0:0-0:0)
- **Themed icon registry**: `self._themed_actions: dict[QAction, str]`. Helper [_register_themed_action(action, name)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:849:4-858:60) replaces every old `standardIcon(...)` call. [_refresh_toolbar_icons()](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:860:4-874:85) recolours all of them + the export glyph + the segmented glyphs on every theme switch.
- **Toolbar layout** (left → right) now matches the mockup `.tb-group` structure:
  `undo redo | new open save | cell_labels row_labels auto_layout | « stretch » | [☀ Light · 🌙 Dark] | Export▾`
- **Export button** is now a QToolButton with `property("primary", True)` → solid cyan accent pill, white glyph + text, dropdown menu preserved (PDF / TIFF / JPG).
- **`_theme_toolbar_action` removed** (replaced by the segmented). The View-menu `_theme_action` + Ctrl+Shift+T shortcut still work and stay in sync via [_theme_segmented.set_theme(theme)](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme_segmented.py:54:4-61:42) inside [_apply_theme](file:///e:/Documents/Codes/ImageLayoutManager/src/app/main_window.py:818:4-825:35).

### What you'll see on launch
- All toolbar buttons carry clean 1.5 px-stroke line icons at crisp HiDPI resolution.
- Icons recolour instantly when the segmented pill flips — no need to restart.
- Export button is the only accent-coloured element, drawing the eye naturally to the primary action (matches mockup item #11).
- Clicking the sun/moon pill, the menu toggle, or Ctrl+Shift+T — any of the three — keeps all three in sync.

### Constraint honoured
No touches to [cell_item.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/cell_item.py:0:0-0:0), `canvas_view.py`, [canvas_scene.py](file:///e:/Documents/Codes/ImageLayoutManager/src/canvas/canvas_scene.py:0:0-0:0), or anything under `src/model/`. Plotting area is untouched.

## Pending
Phase 3 (canvas background grid + dashed placeholders, tokens already exposed via [get_tokens](file:///e:/Documents/Codes/ImageLayoutManager/src/app/theme.py:386:0-392:65)), Phase 4 (layers panel delegate + thumbnails), Phase 5 (inspector sections), Phase 6 (status bar polish), Phase 7 (theme-switch crossfade). Waiting on your signal to continue.

📜 Log Entry
- Date: 2026-04-20
- Type: design-discuss
- Module: src/app/icons.py, src/app/theme_segmented.py, src/app/theme.py, src/app/main_window.py
- Summary: Phase 2 redesign: themed line-icon toolbar + segmented light/dark pill + primary accent Export button
- Reason: Match redesign mockups (items #7/#8/#11); previous toolbar used Qt standardIcon (inconsistent) and a single theme-toggle text action (no visual accent)
- Alternatives: Ship per-theme SVG files on disk (rejected: 22+ files vs 1 Python module); use QIconEngine subclass (rejected: overkill for static re-render on theme change)
- Risk/Follow-up: QSvgRenderer adds ~1ms per icon render; 11 icons × 2 renders (light+dark) is negligible. Future icons should go in icons._ICONS dict.
- Breaking: no (public theme API unchanged; removed private _theme_toolbar_action attribute)
- Tests Needed: no