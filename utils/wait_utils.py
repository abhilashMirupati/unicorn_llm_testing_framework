"""
Wait Utilities
--------------

Centralised waiting logic for both web and mobile contexts.  This
module wraps Playwright and Appium wait functions and augments them
with a repository of known spinners and loading indicators.  Tests
should not call ``time.sleep`` directly; instead they should rely on
the helpers provided here to synchronise with the application under
test.

The wait repository is stored in a YAML file whose location is
configured in :mod:`config.settings.yaml`.  The repository records
selectors for spinners or overlays that commonly appear in the
application; these selectors are waited upon at the end of each
interaction to ensure the UI is stable before proceeding.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


def _load_wait_repo(repo_path: str) -> Dict[str, Any]:
    """Load the wait repository from the given YAML path.

    If the file does not exist a default structure is returned.  The
    dictionary has top‑level keys ``ui`` and ``mobile`` with lists of
    ``spinners`` and ``overlays`` beneath each.
    """
    path = Path(repo_path)
    if not path.exists():
        return {"ui": {"spinners": [], "overlays": []}, "mobile": {"spinners": [], "overlays": []}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("ui", {}).setdefault("spinners", [])
        data.setdefault("ui", {}).setdefault("overlays", [])
        data.setdefault("mobile", {}).setdefault("spinners", [])
        data.setdefault("mobile", {}).setdefault("overlays", [])
        return data
    except Exception as exc:
        logger.error("Failed to load wait repository from %s: %s", repo_path, exc)
        return {"ui": {"spinners": [], "overlays": []}, "mobile": {"spinners": [], "overlays": []}}


def _save_wait_repo(repo_path: str, repo: Dict[str, Any]) -> None:
    """Persist the wait repository to disk."""
    try:
        Path(repo_path).parent.mkdir(parents=True, exist_ok=True)
        with open(repo_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(repo, f, allow_unicode=True)
    except Exception as exc:
        logger.error("Failed to save wait repository to %s: %s", repo_path, exc)


def add_indicator(context: str, indicator: str, config: Any) -> None:
    """Add a spinner or overlay selector to the repository.

    :param context: Either ``"ui"`` or ``"mobile"``.
    :param indicator: A CSS selector or Appium locator string.
    :param config: A configuration object (mapping) containing a
        ``wait_repo`` section with a ``path`` key.
    """
    repo_path = None
    try:
        repo_path = config.get("wait_repo", {}).get("path")  # type: ignore[assignment]
    except Exception:
        repo_path = None
    repo_path = repo_path or "waits_repo/wait_repo.yaml"
    repo = _load_wait_repo(repo_path)
    if context not in repo:
        repo[context] = {"spinners": [], "overlays": []}
    if indicator not in repo[context].get("spinners", []):
        repo[context]["spinners"].append(indicator)
        logger.info("Added new %s indicator to wait repo: %s", context, indicator)
        _save_wait_repo(repo_path, repo)


def wait_for_page_stable(page: Any, config: Any) -> None:
    """Wait for a Playwright page to finish loading and hide global spinners.

    The function first waits for network activity to be idle and then
    iterates over the list of known spinners and overlays from the
    repository, waiting for each to disappear.  Timeouts and missing
    selectors are quietly ignored so as not to mask primary test
    failures.
    """
    if not page:
        return
    # Wait for network idle
    try:
        page.wait_for_load_state("networkidle")
    except Exception as exc:
        logger.debug("wait_for_load_state failed: %s", exc)
    # Now wait for known UI spinners and overlays to disappear
    repo_path = None
    try:
        repo_path = config.get("wait_repo", {}).get("path")  # type: ignore[assignment]
    except Exception:
        repo_path = None
    repo_path = repo_path or "waits_repo/wait_repo.yaml"
    repo = _load_wait_repo(repo_path)
    selectors: List[str] = repo.get("ui", {}).get("spinners", []) + repo.get("ui", {}).get("overlays", [])
    for sel in selectors:
        try:
            page.wait_for_selector(sel, state="hidden", timeout=30000)
        except Exception:
            pass


def wait_for_element_ui(page: Any, selector: str, config: Any, timeout: int = 30000) -> None:
    """Wait for a UI element to become visible.

    Uses Playwright's ``wait_for_selector`` with the ``visible`` state.  A
    timeout may be specified in milliseconds.  Global spinners are
    waited upon both before and after the element wait.
    """
    if not page:
        return
    # Wait for spinners before attempting element wait
    wait_for_page_stable(page, config)
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
    except Exception as exc:
        logger.debug("wait_for_selector(%s) failed: %s", selector, exc)
        raise
    finally:
        wait_for_page_stable(page, config)


def wait_for_element_mobile(driver: Any, locator: Dict[str, str], config: Any, timeout: int = 30) -> None:
    """Wait for a mobile element to be present and enabled.

    ``locator`` is a dictionary with ``type`` and ``value`` keys.  The
    supported locator types include ``id``, ``accessibility_id``,
    ``xpath``, ``class_chain`` and ``android_uiautomator``.  If the
    Appium client is not installed this function returns immediately.
    """
    try:
        from appium.webdriver.common.mobileby import MobileBy  # type: ignore
        from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
        from selenium.webdriver.support import expected_conditions as EC  # type: ignore
    except Exception:
        return
    if not driver or not locator:
        return
    ltype = locator.get("type")
    value = locator.get("value")
    if not ltype or not value:
        return
    by_map = {
        "id": MobileBy.ID,
        "accessibility_id": MobileBy.ACCESSIBILITY_ID,
        "xpath": MobileBy.XPATH,
        "class_chain": MobileBy.IOS_CLASS_CHAIN,
        "android_uiautomator": MobileBy.ANDROID_UIAUTOMATOR,
    }
    by = by_map.get(ltype.lower())
    if by is None:
        return
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception as exc:
        logger.debug("wait_for_element_mobile(%s=%s) failed: %s", ltype, value, exc)
        raise
    finally:
        # Wait for known mobile spinners
        repo_path = None
        try:
            repo_path = config.get("wait_repo", {}).get("path")  # type: ignore[assignment]
        except Exception:
            repo_path = None
        repo_path = repo_path or "waits_repo/wait_repo.yaml"
        repo = _load_wait_repo(repo_path)
        indicators = repo.get("mobile", {}).get("spinners", []) + repo.get("mobile", {}).get("overlays", [])
        for indicator in indicators:
            try:
                # Interpret indicator prefixes: id=, accessibility_id=, xpath=, etc.
                by_ind = None
                val_ind = None
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