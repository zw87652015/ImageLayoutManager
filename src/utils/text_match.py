"""Qt-free helpers for the Match Text Size windows.

``size_clusters`` finds groups of texts sharing a similar size (the batch
"Suggested groups" rows); ``format_size`` renders current/target sizes;
``raster_summary``/``svg_summary`` feed the summary line above each list.
"""

from statistics import median

from src.utils.svg_text_utils import format_text_size

# OCR size estimates are noisy; SVG sizes are exact.
RASTER_REL_TOL = 0.12
SVG_REL_TOL = 0.02


def size_clusters(items, rel_tol, min_count=2, limit=4):
    """Cluster *items* (dicts {id, size_pt, text, flagged}) by similar size.

    Items are sorted by ``size_pt``; a new cluster starts when an item's
    size exceeds ``cluster_min * (1 + rel_tol)``.  Clusters with fewer than
    ``min_count`` members are dropped.  Each cluster is
    ``{ids, size_pt (median), count, samples, flagged}`` — ``ids`` in input
    order, ``samples`` the first three distinct non-empty texts in input
    order, ``flagged`` the count of flagged members.  Result is sorted by
    (-count, -size_pt) and capped at *limit*.
    """
    ordered = sorted(items, key=lambda it: it["size_pt"])
    clusters = []
    current = None
    for it in ordered:
        if current is None or it["size_pt"] > current["min"] * (1 + rel_tol):
            current = {"min": it["size_pt"], "members": []}
            clusters.append(current)
        current["members"].append(it)
    out = []
    for cluster in clusters:
        members = cluster["members"]
        if len(members) < min_count:
            continue
        seen = []
        for m in members:
            if m["text"] and m["text"] not in seen:
                seen.append(m["text"])
            if len(seen) >= 3:
                break
        out.append({
            "ids": [m["id"] for m in members],
            "size_pt": median(m["size_pt"] for m in members),
            "count": len(members),
            "samples": seen,
            "flagged": sum(1 for m in members if m["flagged"]),
        })
    out.sort(key=lambda c: (-c["count"], -c["size_pt"]))
    return out[:limit]


def format_size(current_pt, target_pt=None, approx=False) -> str:
    """"8 pt" / "6.1 → 8 pt", with a "≈" prefix when *approx*.  The target
    is shown only when given and differs from current by more than 0.05."""
    current = format_text_size(round(current_pt, 1))
    text = f"{current} pt"
    if target_pt is not None and abs(target_pt - current_pt) > 0.05:
        text = f"{current} → {format_text_size(round(target_pt, 1))} pt"
    return ("≈" if approx else "") + text


def raster_summary(regions, report) -> dict:
    """Counts for the summary line: ``resizing`` = enabled, grouped and the
    last apply actually resized it; ``review`` = safety warning or a skipped
    apply; ``ungrouped`` = no group assigned."""
    resizing = review = ungrouped = 0
    for r in regions:
        if not r.group_id:
            ungrouped += 1
        status = report.get(r.id)
        if r.warning or status not in (None, "applied"):
            review += 1
        if r.enabled and r.group_id and status == "applied":
            resizing += 1
    return {"total": len(regions), "resizing": resizing,
            "review": review, "ungrouped": ungrouped}


def svg_summary(rows, group_of_key) -> dict:
    """``{total, grouped}`` over the element rows of one SVG."""
    grouped = sum(1 for r in rows if r["key"] in group_of_key)
    return {"total": len(rows), "grouped": grouped}
