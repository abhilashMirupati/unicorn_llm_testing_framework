"""
WebView Utilities
-----------------

This module collects helpers that relate to hybrid applications where
native mobile views embed web content via a WebView.  In such cases
tests may need to wait for the WebView to finish initialising before
interacting with elements or to switch contexts correctly.  The
functions provided here delegate to :mod:`utils.wait_utils` and avoid
direct sleeps or arbitrary delays.

The current implementation is intentionally minimal.  It exposes a
single function :func:`stabilise_webview` which calls
:func:`wait_for_page_stable` on the underlying Playwright page.  In
future this module can be expanded to handle context switching and
deep integration with Appium's webview support.
"""

from __future__ import annotations

from typing import Any

from .wait_utils import wait_for_page_stable


def stabilise_webview(page: Any, config: Any) -> None:
    """Wait for a WebView to finish loading.

    This function simply proxies to :func:`wait_for_page_stable`.  It
    exists as a separate helper to signal intent when working with
    hybrid apps and to provide a hook for future enhancements.
    """
    wait_for_page_stable(page, config)


__all__ = ["stabilise_webview"]