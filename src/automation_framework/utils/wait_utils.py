"""
Wait Utilities
--------------

This module centralises all wait logic used by the framework.  It
provides high‑level functions for waiting on elements, pages and
global loading indicators across web (Playwright) and mobile (Appium)
contexts.  No test step should include ``time.sleep`` calls or
arbitrary delays; instead, callers should use these functions to
explicitly wait for the desired conditions.  When new spinners or
loading overlays are detected during a run they can be added to the
wait repository (see :mod:`wait_repo`) via :func:`add_indicator`.

The wait repository is stored in a YAML file whose path can be
configured.  The structure contains separate sections for web and
mobile spinners/overlays.  See ``wait_repo.yaml`` for an example.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .logger import get_logger


logger = get_logger(__name__)


def _load_wait_repo(path: str) -> Dict[str, Any]:
    """Load the wait repository from the given YAML path.

    If the file does not exist, a default structure is returned.  The
    returned dictionary has keys ``ui`` and ``mobile``, each mapping
    to sub‑dictionaries with lists of ``spinners`` and ``overlays``.
    """
    repo_path = Path(path)
    if not repo_path.exists():
        # Return default structure
        return {"ui": {"spinners": [], "overlays": []}, "mobile": {"spinners": [], "overlays": []}}
    try:
        with open(repo_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Ensure structure exists
        data.setdefault("ui", {}).setdefault("spinners", [])
        data.setdefault("ui", {}).setdefault("overlays", [])
        data.setdefault("mobile", {}).setdefault("spinners", [])
        data.setdefault("mobile", {}).setdefault("overlays", [])
        return data
    except Exception as exc:
        logger.error("Failed to load wait repository from %s: %s", path, exc)
        return {"ui": {"spinners": [], "overlays": []}, "mobile": {"spinners": [], "overlays": []}}


def _save_wait_repo(path: str, repo: Dict[str, Any]) -> None:
    """Persist the wait repository to YAML."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(repo, f, allow_unicode=True)
    except Exception as exc:
        logger.error("Failed to save wait repository to %s: %s", path, exc)


def add_indicator(context: str, indicator: str, config: Any) -> None:
    """Add a new spinner or overlay indicator to the wait repository.

    ``context`` must be either ``"ui"`` or ``"mobile"``.  The indicator
    should be a CSS selector (for web) or an Appium locator string (for
    mobile).  If the indicator already exists it is ignored.
    """
    repo_path = config.get("wait_repo.path", "./wait_repo.yaml") if hasattr(config, "get") else "./wait_repo.yaml"
    repo = _load_wait_repo(repo_path)
    ctx = repo.setdefault(context, {}).setdefault("spinners", [])
    if indicator not in ctx:
        ctx.append(indicator)
        logger.info("Added new %s indicator to wait repo: %s", context, indicator)
        _save_wait_repo(repo_path, repo)


def wait_for_page_stable(page: Any, config: Any) -> None:
    """Wait for a Playwright page to finish loading and hide global spinners.

    This helper calls ``wait_for_load_state('networkidle')`` to ensure
    network activity is idle, then iterates over known spinner and
    overlay selectors from the wait repository and waits for each to
    disappear.  Any exceptions are logged but not raised to avoid
    masking the original test failure.
    """
    if not page:
        return
    # Wait for network idle
    try:
        page.wait_for_load_state("networkidle")
    except Exception as exc:
        logger.debug("wait_for_load_state failed: %s", exc)
    # Wait for global indicators to disappear
    repo_path = config.get("wait_repo.path", "./wait_repo.yaml") if hasattr(config, "get") else "./wait_repo.yaml"
    repo = _load_wait_repo(repo_path)
    selectors: List[str] = repo.get("ui", {}).get("spinners", []) + repo.get("ui", {}).get("overlays", [])
    for sel in selectors:
        try:
            page.wait_for_selector(sel, state="hidden", timeout=30000)
        except Exception:
            # Do not raise; spinners may not always be present
            pass


def wait_for_element_ui(page: Any, selector: str, config: Any, timeout: int = 30000) -> None:
    """Wait for a UI element to be visible and enabled before interacting.

    Uses Playwright's ``wait_for_selector`` with the ``visible`` state.
    A timeout can be specified in milliseconds.  Global spinners are
    also waited on before returning.
    """
    if not page:
        return
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
    except Exception as exc:
        logger.debug("wait_for_selector(%s) failed: %s", selector, exc)
        # Let the caller handle failures; self‑healing will be invoked
        raise
    finally:
        # Regardless of success/failure, wait for any global spinners
        wait_for_page_stable(page, config)


def wait_for_element_mobile(driver: Any, locator: Dict[str, str], config: Any, timeout: int = 30) -> None:
    """Wait for a mobile element to be present and enabled.

    ``locator`` is a dictionary returned from the locator repository
    (with keys ``type`` and ``value``) or a raw locator definition.  If
    the driver does not provide explicit wait utilities (e.g. dummy
    drivers) this function returns immediately.  Supported locator
    types include ``id``, ``accessibility_id``, ``xpath`` and
    ``class_chain``.
    """
    # Only attempt waits if the driver exposes WebDriverWait and EC
    try:
        from appium.webdriver.common.mobileby import MobileBy  # type: ignore
        from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
        from selenium.webdriver.support import expected_conditions as EC  # type: ignore
    except Exception:
        return
    if not driver:
        return
    loc_type = locator.get("type")
    value = locator.get("value")
    if not loc_type or not value:
        return
    by_map = {
        "id": MobileBy.ID,
        "accessibility_id": MobileBy.ACCESSIBILITY_ID,
        "xpath": MobileBy.XPATH,
        "class_chain": MobileBy.IOS_CLASS_CHAIN,
        "android_uiautomator": MobileBy.ANDROID_UIAUTOMATOR,
    }
    by = by_map.get(loc_type.lower())
    if by is None:
        return
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception as exc:
        logger.debug("wait_for_element_mobile(%s=%s) failed: %s", loc_type, value, exc)
        raise
    finally:
        # Wait for global mobile spinners to disappear
        repo_path = config.get("wait_repo.path", "./wait_repo.yaml") if hasattr(config, "get") else "./wait_repo.yaml"
        repo = _load_wait_repo(repo_path)
        indicators: List[str] = repo.get("mobile", {}).get("spinners", []) + repo.get("mobile", {}).get("overlays", [])
        for indicator in indicators:
            try:
                # indicator may be an id, accessibility id or xpath; detect prefix
                if indicator.startswith("//"):
                    by_ind = MobileBy.XPATH
                    val_ind = indicator
                elif indicator.startswith("id="):
                    by_ind = MobileBy.ID
                    val_ind = indicator[len("id="):]
                elif indicator.startswith("accessibility_id="):
                    by_ind = MobileBy.ACCESSIBILITY_ID
                    val_ind = indicator[len("accessibility_id="):]
                else:
                    # treat as id
                    by_ind = MobileBy.ID
                    val_ind = indicator
                WebDriverWait(driver, 1).until_not(EC.presence_of_element_located((by_ind, val_ind)))
            except Exception:
                pass


__all__ = [
    "wait_for_page_stable",
    "wait_for_element_ui",
    "wait_for_element_mobile",
    "add_indicator",
]