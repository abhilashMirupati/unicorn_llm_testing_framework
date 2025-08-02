"""
Self‑Healing Helpers
--------------------

This module centralises helper functions used by MCPs to recover
when an element cannot be interacted with via its primary locator.  The
current implementations are deliberately conservative: for UI tests
they attempt to match elements by visible text; for mobile tests they
fall back to coordinate taps.  More advanced techniques (e.g. OCR or
vision‑based recognition) can be added here in future without
changing the MCP interfaces.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# These functions are intentionally minimal.  They are referenced in
# documentation and serve as extension points for future self‑healing
# algorithms.  At present, all self‑healing logic is implemented
# directly in the MCP classes.


def recover_ui_element(step: Dict[str, Any], page: Any) -> Optional[str]:
    """Attempt to derive an alternative selector from a UI step.

    Returns a selector string if a recovery strategy is found, or
    ``None`` otherwise.  This helper examines the step definition for
    possible fallback values (e.g. text, label or value).  It does not
    interact with the DOM.  Actual clicking or filling must be handled
    by the caller.
    """
    text_candidate = step.get("text") or step.get("value") or step.get("label")
    if text_candidate:
        return f"text={text_candidate}"
    return None


def recover_mobile_coordinates(step: Dict[str, Any]) -> Optional[tuple[int, int]]:
    """Return coordinate fallback for a mobile step if provided in the step."""
    if "x" in step and "y" in step:
        return (step["x"], step["y"])
    return None


__all__ = ["recover_ui_element", "recover_mobile_coordinates"]