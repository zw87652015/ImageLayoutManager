"""Compatibility alias — moved to ilmplot.document."""
import sys
import ilmplot.document as _module
sys.modules[__name__] = _module
