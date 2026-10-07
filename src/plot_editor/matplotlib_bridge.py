"""Compatibility alias — moved to ilmplot.bridge."""
import sys
import ilmplot.bridge as _module
sys.modules[__name__] = _module
