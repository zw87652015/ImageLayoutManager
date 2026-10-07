"""Compatibility alias — moved to ilmplot.stats."""
import sys
import ilmplot.stats as _module
sys.modules[__name__] = _module
