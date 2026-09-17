import hashlib
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from src.model.data_model import PlotArea, PlotAlignmentGroup
from src.model.layout_engine import LayoutEngine


_EPS = 1e-9
_MAX_SVG_BYTES = 64 * 1024 * 1024


def _signature(path):
    realpath = os.path.normcase(os.path.realpath(os.fspath(path)))
    stat = os.stat(realpath)
    return realpath, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=256)
def _source_size_cached(path, mtime_ns, byte_size):
    try:
        extension = os.path.splitext(path)[1].lower()
        if extension == '.svg':
            from PyQt6.QtCore import QByteArray
            from PyQt6.QtSvg import QSvgRenderer
            from src.utils.svg_utils import sanitize_svg_bytes
            if byte_size > _MAX_SVG_BYTES:
                return None
            with open(path, 'rb') as source:
                data = source.read(_MAX_SVG_BYTES + 1)
            if len(data) > _MAX_SVG_BYTES:
                return None
            renderer = QSvgRenderer(QByteArray(sanitize_svg_bytes(data)))
            if not renderer.isValid():
                return None
            size = renderer.defaultSize()
            width, height = float(size.width()), float(size.height())
        elif extension in ('.pdf', '.eps'):
            import fitz
            with fitz.open(path) as document:
                if not document.page_count:
                    return None
                rect = document[0].rect
                width, height = float(rect.width), float(rect.height)
        else:
            from PIL import Image
            with Image.open(path) as image:
                width, height = map(float, image.size)
        if not all(math.isfinite(value) and value > _EPS for value in (width, height)):
            return None
        return width, height
    except Exception:
        return None


def get_source_size(path) -> tuple[float, float] | None:
    try:
        return _source_size_cached(*_signature(path))
    except (OSError, TypeError, ValueError):
        return None


@lru_cache(maxsize=512)
def _source_digest_cached(path, mtime_ns, byte_size):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(path) -> str:
    return _source_digest_cached(*_signature(path))


def rotate_box(box: tuple, rotation: int) -> tuple:
    left, top, right, bottom = box
    if type(rotation) is not int or rotation % 90:
        raise ValueError('Rotation must be a multiple of 90 degrees.')
    rotation %= 360
    if rotation == 90:
        return 1 - bottom, left, 1 - top, right
    if rotation == 180:
        return 1 - right, 1 - bottom, 1 - left, 1 - top
    if rotation == 270:
        return top, 1 - right, bottom, 1 - left
    return left, top, right, bottom


def content_rect(cell, rect: tuple, layout_mode: str) -> tuple:
    x, y, width, height = rect
    if layout_mode == 'freeform':
        return x, y, width, height
    return (x + cell.padding_left, y + cell.padding_top,
            width - cell.padding_left - cell.padding_right,
            height - cell.padding_top - cell.padding_bottom)


@dataclass(frozen=True)
class ImagePlacement:
    rect: tuple[float, float, float, float]
    clip_rect: tuple[float, float, float, float]
    crop: tuple[float, float, float, float]
    rotation: int


@dataclass(frozen=True)
class AlignmentIssue:
    code: str
    cell_id: str = ''
    group_id: str = ''
    detail: str = ''


@dataclass
class PlacementResult:
    placements: dict[str, ImagePlacement] = field(default_factory=dict)
    plot_rects: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    issues: list[AlignmentIssue] = field(default_factory=list)
    #: Informational only (never blocks export): e.g. an exact-reference
    #: group that had to shrink so no member is clipped.
    notices: list[AlignmentIssue] = field(default_factory=list)
    group_heights: dict[str, float] = field(default_factory=dict)


class PlotAlignmentError(ValueError):
    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__('; '.join(f'{issue.code}: {issue.detail}' for issue in self.issues))


def _valid_box(box):
    return (len(box) == 4
            and all(type(value) in (float, int) and 0 <= value <= 1
                    and math.isfinite(value) for value in box)
            and box[2] - box[0] > _EPS and box[3] - box[1] > _EPS)


def _valid_rect(rect):
    return (len(rect) == 4
            and all(type(value) in (float, int) and math.isfinite(value) for value in rect)
            and rect[2] > _EPS and rect[3] > _EPS)


def _anchor(cell, clip, width, height):
    x, y, available_w, available_h = clip
    horizontal = 'center' if cell.fit_mode == 'cover' else cell.align_h
    vertical = 'center' if cell.fit_mode == 'cover' else cell.align_v
    x += (available_w - width) * {'left': 0, 'right': 1}.get(horizontal, 0.5)
    y += (available_h - height) * {'top': 0, 'bottom': 1}.get(vertical, 0.5)
    return x, y


def _map_plot(placement, plot):
    crop = rotate_box(placement.crop, placement.rotation)
    x, y, width, height = placement.rect
    sx = width / (crop[2] - crop[0])
    sy = height / (crop[3] - crop[1])
    return (x + sx * (plot[0] - crop[0]), y + sy * (plot[1] - crop[1]),
            sx * (plot[2] - plot[0]), sy * (plot[3] - plot[1]))


def resolve_image_placements(project, layout_result=None, *, strict=False) -> PlacementResult:
    if layout_result is None:
        layout_result = LayoutEngine.calculate_layout(project)
    result = PlacementResult()
    leaves = {cell.id: cell for cell in project.get_all_leaf_cells()}
    rows = LayoutEngine._row_by_cell_id(project)
    sizes = {}
    plots = {}
    failures = {}
    marker_failures = {}
    outside_crop = set()
    for cid, cell in leaves.items():
        size = get_source_size(cell.image_path) if cell.image_path else None
        crop = (cell.crop_left, cell.crop_top, cell.crop_right, cell.crop_bottom)
        rect = layout_result.cell_rects.get(cid)
        rotation = cell.rotation
        if size is None:
            failures[cid] = ('missing_source', 'Restore or replace the source image.')
        elif not _valid_box(crop) or type(rotation) is not int or rotation % 90:
            failures[cid] = ('invalid_area', 'Use a valid crop and a right-angle rotation.')
        elif rect is None:
            failures[cid] = ('no_space', 'Give this cell a visible layout rectangle.')
        else:
            clip = content_rect(cell, rect, project.layout_mode)
            if not _valid_rect(clip):
                failures[cid] = ('no_space', 'Increase the available cell area or reduce padding.')
            else:
                rotated_crop = rotate_box(crop, rotation)
                width, height = size[::-1] if rotation % 180 else size
                sizes[cid] = width, height
                crop_w = width * (rotated_crop[2] - rotated_crop[0])
                crop_h = height * (rotated_crop[3] - rotated_crop[1])
                scale = (max if cell.fit_mode == 'cover' else min)(clip[2] / crop_w, clip[3] / crop_h)
                image_w, image_h = crop_w * scale, crop_h * scale
                x, y = _anchor(cell, clip, image_w, image_h)
                result.placements[cid] = ImagePlacement((x, y, image_w, image_h), clip, crop, rotation)
        area = cell.plot_area
        if area is None:
            continue
        try:
            if not isinstance(area, PlotArea):
                raise ValueError
            area.to_dict()
            box = (area.left, area.top, area.right, area.bottom)
            if not _valid_box(box):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            marker_failures[cid] = ('invalid_area', 'Mark a valid plot rectangle again.')
            continue
        if cid in failures:
            marker_failures[cid] = failures[cid]
            continue
        if area.source_digest:
            try:
                current_digest = source_digest(cell.image_path)
            except OSError:
                marker_failures[cid] = ('missing_source', 'Restore or replace the source image.')
                continue
            if current_digest.lower() != area.source_digest.lower():
                marker_failures[cid] = ('source_changed', 'The source changed; mark its plot area again.')
                continue
        plot = rotate_box(box, rotation)
        plots[cid] = plot
        result.plot_rects[cid] = _map_plot(result.placements[cid], plot)
        rotated_crop = rotate_box(crop, rotation)
        if (plot[0] < rotated_crop[0] - _EPS or plot[1] < rotated_crop[1] - _EPS
                or plot[2] > rotated_crop[2] + _EPS or plot[3] > rotated_crop[3] + _EPS):
            outside_crop.add(cid)

    normal = dict(result.placements)
    normal_plots = dict(result.plot_rects)
    groups = project.plot_alignment_groups
    active_issues = []
    if not isinstance(groups, list):
        issue = AlignmentIssue('invalid_area', detail='Restore the alignment group list.')
        result.issues.append(issue)
        if strict:
            raise PlotAlignmentError([issue])
        return result
    memberships = Counter()
    group_ids = Counter()
    for group in groups:
        if isinstance(group, PlotAlignmentGroup):
            if isinstance(group.id, str):
                group_ids[group.id] += 1
            if isinstance(group.cell_ids, list):
                memberships.update(cid for cid in group.cell_ids if isinstance(cid, str))
    for cid, (code, detail) in marker_failures.items():
        if cid not in memberships:
            result.issues.append(AlignmentIssue(code, cid, detail=detail))

    for group in groups:
        gid = group.id if isinstance(group, PlotAlignmentGroup) and isinstance(group.id, str) else ''

        def issue(code, cid='', detail=''):
            item = AlignmentIssue(code, cid, gid, detail)
            result.issues.append(item)
            active_issues.append(item)

        start = len(active_issues)
        if not isinstance(group, PlotAlignmentGroup):
            issue('invalid_area', detail='Restore a valid alignment group.')
            continue
        members = group.cell_ids
        if isinstance(members, list):
            for cid in dict.fromkeys(cid for cid in members if isinstance(cid, str)):
                if memberships[cid] > 1:
                    issue('duplicate_member', cid, 'Keep each cell in only one alignment group.')
        if group_ids[gid] > 1:
            issue('duplicate_member', detail='Give each alignment group a unique ID.')
        if (not isinstance(group.reference_id, str) or not isinstance(members, list)
                or group.reference_id not in members or group.reference_id not in leaves):
            issue('missing_reference', detail='Select an existing member as the reference.')
        try:
            group.to_dict()
        except (ValueError, TypeError, AttributeError):
            if len(active_issues) == start:
                issue('invalid_area', detail='Check the alignment members, modes and row assignments.')
            continue
        for cid in members:
            if cid not in leaves:
                if cid != group.reference_id:
                    issue('missing_member', cid, 'Restore the missing cell or update group membership.')
                continue
            problem = failures.get(cid) or marker_failures.get(cid)
            if problem:
                issue(problem[0], cid, problem[1])
            elif cid not in plots:
                issue('invalid_area', cid, 'Mark this cell plot area before aligning.')
            elif cid in outside_crop:
                issue('cropped_area', cid, 'Expand the crop to include the entire marked plot.')
        if len(active_issues) != start:
            continue
        reference = group.reference_id
        href = normal_plots[reference][3]
        refbottom = normal_plots[reference][1] + href
        params = {}
        baselines = {}
        for cid in members:
            crop = rotate_box(normal[cid].crop, normal[cid].rotation)
            plot = plots[cid]
            plot_h = plot[3] - plot[1]
            width, height = sizes[cid]
            a = (plot[3] - crop[1]) / plot_h
            b = (crop[3] - plot[3]) / plot_h
            w = width * (crop[2] - crop[0]) / (height * plot_h)
            params[cid] = a, b, w
            row = (0 if group.baseline_mode == 'single' else
                   group.row_groups[cid] if group.baseline_mode == 'custom' else rows[cid])
            baselines.setdefault(row, []).append(cid)
        def fit_target():
            target = href
            for cid in members:
                target = min(target, normal[cid].clip_rect[2] / params[cid][2])
            for row_members in baselines.values():
                for cid in row_members:
                    top = normal[cid].clip_rect[1]
                    for other in row_members:
                        other_clip = normal[other].clip_rect
                        denominator = params[cid][0] + params[other][1]
                        if denominator > _EPS:
                            target = min(target, (other_clip[1] + other_clip[3] - top) / denominator)
            return target

        def solve(mode, target):
            """Baseline per row plus every overflow that *mode* would produce
            at *target*; the caller decides whether that is a blocker or a
            reason to shrink."""
            rows_out, overflows = {}, []
            for row, row_members in baselines.items():
                lower = max(normal[cid].clip_rect[1] + target * params[cid][0] for cid in row_members)
                upper = min(normal[cid].clip_rect[1] + normal[cid].clip_rect[3]
                            - target * params[cid][1] for cid in row_members)
                preferred = (refbottom if reference in row_members else
                             sum(normal_plots[cid][1] + normal_plots[cid][3] for cid in row_members) / len(row_members))
                fixed = mode == 'reference' and reference in row_members
                baseline = (preferred if fixed or lower > upper + _EPS else
                            min(max(preferred, lower), max(lower, upper)))
                if lower > upper + _EPS:
                    overflows.append(('', 'Choose fit sizing or enlarge the cells in this baseline row.'))
                elif baseline < lower - _EPS or baseline > upper + _EPS:
                    overflows.append((reference, 'Choose fit sizing or make room around the reference baseline.'))
                for cid in row_members:
                    if mode == 'reference' and cid == reference:
                        continue
                    if target * params[cid][2] > normal[cid].clip_rect[2] + _EPS:
                        overflows.append((cid, 'Choose fit sizing or increase the available width.'))
                rows_out[row] = baseline
            return rows_out, overflows

        mode = group.sizing_mode
        target = href if mode == 'reference' else fit_target()
        if mode == 'fit' and (not math.isfinite(target) or target <= _EPS):
            issue('no_space', detail='Separate disjoint baseline rows or enlarge their available area.')
            continue
        row_baselines, overflows = solve(mode, target)
        if mode == 'reference' and overflows:
            # The exact reference size would clip a member (typically its
            # title or labels above/below the plot). Content must never be
            # cut, so shrink the whole group to the largest size that still
            # fits — same relationships, smaller plots — and say so.
            reduced = fit_target()
            if math.isfinite(reduced) and reduced > _EPS:
                reduced_rows, reduced_overflows = solve('fit', reduced)
                if not reduced_overflows:
                    mode, target, row_baselines = 'fit', reduced, reduced_rows
                    result.notices.append(AlignmentIssue(
                        'reduced_to_fit', '', gid,
                        f'Plots reduced to {reduced:.2f} mm so every panel stays fully visible; '
                        'enlarge the cells to restore the exact reference size.'))
                    overflows = []
        for cid, detail in overflows:
            issue('overflow', cid, detail)
        result.group_heights[gid] = target
        for row, row_members in baselines.items():
            baseline = row_baselines[row]
            for cid in row_members:
                a, b, w = params[cid]
                placement = normal[cid]
                width, height = target * w, target * (a + b)
                x, _ = _anchor(leaves[cid], placement.clip_rect, width, height)
                rect = (x, baseline - target * a, width, height)
                if mode == 'reference' and cid == reference:
                    rect = placement.rect
                proposed = ImagePlacement(rect, placement.clip_rect, placement.crop, placement.rotation)
                result.placements[cid] = proposed
                result.plot_rects[cid] = _map_plot(proposed, plots[cid])
    if strict and active_issues:
        raise PlotAlignmentError(active_issues)
    return result


def clipped_source(placement) -> tuple[tuple, tuple] | None:
    rect, clip = placement.rect, placement.clip_rect
    if not _valid_rect(rect) or not _valid_rect(clip) or not _valid_box(placement.crop):
        return None
    x, y = max(rect[0], clip[0]), max(rect[1], clip[1])
    right = min(rect[0] + rect[2], clip[0] + clip[2])
    bottom = min(rect[1] + rect[3], clip[1] + clip[3])
    if right - x <= _EPS or bottom - y <= _EPS:
        return None
    try:
        crop = rotate_box(placement.crop, placement.rotation)
        width, height = crop[2] - crop[0], crop[3] - crop[1]
        adjusted = (crop[0] + width * (x - rect[0]) / rect[2],
                    crop[1] + height * (y - rect[1]) / rect[3],
                    crop[0] + width * (right - rect[0]) / rect[2],
                    crop[1] + height * (bottom - rect[1]) / rect[3])
        original = rotate_box(adjusted, -placement.rotation)
    except (ValueError, TypeError):
        return None
    return (x, y, right - x, bottom - y), original
