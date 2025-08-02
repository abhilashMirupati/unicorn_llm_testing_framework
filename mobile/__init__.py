"""
Mobile Platform Package
----------------------

The `mobile` package exposes the :class:`MobileDriver` which wraps
Appium for executing mobile tests.  When Appium is not installed the
driver falls back to a dummy implementation that logs actions but
performs no real interactions.
"""

from .mobile_driver import MobileDriver

__all__ = ["MobileDriver"]