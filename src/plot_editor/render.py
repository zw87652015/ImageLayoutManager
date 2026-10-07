"""Compatibility alias — moved to ilmplot.render."""
import sys
import ilmplot.render as _module
sys.modules[__name__] = _module
