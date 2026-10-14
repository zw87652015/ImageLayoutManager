"""Intrinsic aspect ratio for PiP insets, from source dimensions on disk.

Uses plot_alignment.get_source_size (cached by path+mtime+size), so vector
sources (.svg/.pdf/.eps) report their real aspect instead of falling back to
the square 1.0 that PIL-only probing produced.
"""

from src.utils.plot_alignment import get_source_size


def pip_source_aspect(pip, parent_image_path=None):
    """W/H of what an inset shows: its external image, or the cropped parent
    image for zoom insets. None if unknown."""
    if pip.pip_type == "external":
        size = get_source_size(pip.image_path) if pip.image_path else None
    elif pip.pip_type == "zoom" and parent_image_path:
        size = get_source_size(parent_image_path)
        if size:
            size = (size[0] * max(0.001, pip.crop_right - pip.crop_left),
                    size[1] * max(0.001, pip.crop_bottom - pip.crop_top))
    else:
        size = None
    return size[0] / size[1] if size else None
