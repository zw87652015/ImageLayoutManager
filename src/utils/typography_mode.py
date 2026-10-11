def uses_points(project):
    return getattr(project, 'typography_mode', 'legacy') == 'points'
