"""
Web Platform Package
--------------------

The `web` package exposes the :class:`WebDriver` which is responsible
for executing UI test cases using Playwright or a dummy fallback.  It
should be imported by client code rather than instantiating the
driver via the module path.
"""

from .web_driver import WebDriver

__all__ = ["WebDriver"]