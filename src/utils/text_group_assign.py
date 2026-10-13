"""Text group membership changes for the SVG and raster Match Text Size windows (Qt-free).

These helpers hold the mutations that the windows used to perform inline, so the
chip UI and the tests share one definition. Semantics match the previous
SvgTextInspectorWindow._on_assign / _on_ungroup / TextGroupsWidget and
RasterTextInspectorWindow._on_assign / _on_ungroup exactly.
"""

from src.model.data_model import SvgTextGroup, SvgTextMember


def assign_svg(project, svg_path, keys, group_id):
    """Move the SVG elements *keys* of *svg_path* into the group *group_id*.

    Each element is first removed from every group, then appended to the target
    group. Returns False (no change) when there are no keys or no such group.
    """
    if not keys or not group_id:
        return False
    group = next((g for g in project.svg_text_groups if g.id == group_id), None)
    if group is None:
        return False
    for g in project.svg_text_groups:
        g.members = [m for m in g.members if not (m.svg_path == svg_path and m.element_key in keys)]
    for key in keys:
        group.members.append(SvgTextMember(svg_path=svg_path, element_key=key))
    return True


def ungroup_svg(project, svg_path, keys):
    """Remove the SVG elements *keys* of *svg_path* from every group."""
    if not keys:
        return False
    for g in project.svg_text_groups:
        g.members = [m for m in g.members if not (m.svg_path == svg_path and m.element_key in keys)]
    return True


def new_svg_group(project, name, font_size_pt):
    """Append a group named *name* (made unique) at *font_size_pt* and return its id."""
    taken = {x.name for x in project.svg_text_groups}
    base, n = name, 2
    while name in taken:
        name = f"{base} {n}"
        n += 1
    group = SvgTextGroup(name=name, font_size_pt=font_size_pt)
    project.svg_text_groups.append(group)
    return group.id


def delete_svg_group(project, group_id):
    """Drop the group *group_id* from the project."""
    project.svg_text_groups = [x for x in project.svg_text_groups if x.id != group_id]


def assign_raster(regions, group_id):
    """Put the raster *regions* into *group_id* and enable them. No-op without a group or regions."""
    if not group_id or not regions:
        return False
    for region in regions:
        region.group_id = group_id
        region.enabled = True
    return True


def ungroup_raster(regions):
    """Clear the group of the raster *regions* (their enabled state is unchanged)."""
    for region in regions:
        region.group_id = None
    return True
