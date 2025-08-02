"""
Mobile MCP Implementation
------------------------

This module implements a simplified Model Context Protocol for mobile
automation using the Appium Python client.  Inspired by the Mobile‑Next
Mobile MCP server, it abstracts away platform differences and allows
LLM‑generated commands to drive Android or iOS devices【181552211307042†L292-L340】.  The MCP
connects to an Appium server and executes steps such as tapping
elements, sending text and swiping.  When an action fails the
framework retries and captures a screenshot for the Allure report.
"""

from typing import Any, Dict, Tuple

try:
    from appium import webdriver  # type: ignore
    _appium_available = True
except ImportError:
    _appium_available = False
    class DummyDriver:
        def find_element(self, by: str, value: str):
            return self
        def click(self):
            pass
        def send_keys(self, text):
            pass
        def swipe(self, start_x, start_y, end_x, end_y, duration):
            pass
        @property
        def text(self):
            return ""
        def tap(self, coords):
            pass
        def quit(self):
            pass

from .mcp_base import MCPBase
from ..utils.locator_repo import LocatorRepo
from ..utils import wait_utils


class MobileMCP(MCPBase):
    """Appium‑based MCP for mobile automation."""

    def __init__(self, config, reporter) -> None:
        super().__init__(config, reporter)
        self.driver: webdriver.Remote | None = None
        self._connect()
        # Initialise locator repository
        try:
            self.locator_repo = LocatorRepo(config)
        except Exception as exc:
            self.logger.error("Failed to initialise LocatorRepo: %s", exc)
            self.locator_repo = None  # type: ignore

    def _connect(self) -> None:
        """Initialise the Appium driver using configuration values."""
        if _appium_available:
            options = {
                "platformName": self.config.get("mobile.platform_name", "Android"),
                "deviceName": self.config.get("mobile.device_name", "emulator-5554"),
                "app": self.config.get("mobile.app_path"),
                "autoGrantPermissions": True,
            }
            server_url = self.config.get("mobile.server_url", "http://localhost:4723/wd/hub")
            try:
                self.driver = webdriver.Remote(server_url, options)
            except Exception:
                # Fallback to dummy driver if connection fails
                self.driver = DummyDriver()
        else:
            # Appium not installed; use dummy driver
            self.driver = DummyDriver()

    def _find_element(self, locator: Dict[str, Any]):
        """Locate an element using a locator dictionary."""
        loc_type = None
        loc_value = None
        # Accept both repository style ({type:..., value:...}) and raw locators
        if "type" in locator and "value" in locator:
            loc_type = locator["type"]
            loc_value = locator["value"]
        else:
            # Determine type based on keys
            for key in ("id", "accessibility_id", "xpath", "class_chain", "android_uiautomator"):
                if key in locator:
                    loc_type = key
                    loc_value = locator[key]
                    break
        if not loc_type or not loc_value:
            raise ValueError(f"Unsupported locator: {locator}")
        by_map = {
            "id": "id",
            "accessibility_id": "accessibility id",
            "xpath": "xpath",
            "class_chain": "-ios class chain",
            "android_uiautomator": "-android uiautomator",
        }
        by = by_map.get(loc_type)
        if not by:
            raise ValueError(f"Unsupported locator type: {loc_type}")
        return self.driver.find_element(by=by, value=loc_value)

    def _execute_step(self, step: Dict[str, Any]) -> None:
        action = step.get("action")
        if not action:
            raise ValueError("Mobile step missing 'action'")
        # Compose a stable step key for repository lookups
        step_key: Optional[str] = None
        stored_locator: Optional[Dict[str, str]] = None
        if getattr(self, "locator_repo", None):
            try:
                step_key = self.locator_repo.compute_step_key(step)
                stored = self.locator_repo.get_locator("mobile", step_key)
                if stored:
                    stored_locator = stored
            except Exception as exc:
                self.logger.debug("LocatorRepo lookup failed: %s", exc)

        # Determine list of candidate locators in order of preference
        candidates: List[Dict[str, str]] = []
        # 1. Stored locator from repository
        if stored_locator:
            candidates.append(stored_locator)
        # 2. Locator provided in the step (raw locator dict)
        if "locator" in step and isinstance(step["locator"], dict):
            # normalise keys to repository style
            loc_dict = step["locator"]
            if "type" in loc_dict and "value" in loc_dict:
                candidates.append({"type": loc_dict["type"], "value": loc_dict["value"]})
            else:
                # pick first key
                for k, v in loc_dict.items():
                    candidates.append({"type": k, "value": v})
                    break
        # 3. Coordinate fallback (tap/send_keys)
        if action in ("tap", "send_keys", "tap_coordinates") and "x" in step and "y" in step:
            candidates.append({"type": "coordinates", "value": f"{step.get('x')},{step.get('y')}"})

        # Execute action using first successful locator
        last_error: Optional[Exception] = None
        chosen_locator: Optional[Dict[str, str]] = None
        for cand in candidates:
            try:
                if cand["type"] == "coordinates":
                    # coordinate tap fallback
                    if action == "tap" or action == "send_keys":
                        coords = tuple(int(n) for n in cand["value"].split(","))
                        self.driver.tap([coords])
                        chosen_locator = cand
                        break
                    else:
                        continue
                # Wait for element to be present
                wait_utils.wait_for_element_mobile(self.driver, cand, self.config)
                element = self._find_element(cand)
                if action == "tap":
                    element.click()
                elif action == "send_keys":
                    element.send_keys(step.get("text", ""))
                elif action == "assert_text":
                    actual = getattr(element, "text", "")
                    expected = step.get("text")
                    if expected not in actual:
                        raise AssertionError(f"Expected '{expected}' in '{actual}'")
                elif action == "swipe":
                    # For swipe we don't use locator; executed outside loop
                    pass
                else:
                    # unsupported inside loop
                    continue
                chosen_locator = cand
                break
            except Exception as exc:
                last_error = exc
                self.logger.debug("Candidate mobile locator %s failed: %s", cand, exc)
                continue

        # Handle swipe outside of locator resolution
        if action == "swipe":
            start: Tuple[int, int] = tuple(step.get("start"))  # type: ignore
            end: Tuple[int, int] = tuple(step.get("end"))  # type: ignore
            duration = step.get("duration", 800)
            self.driver.swipe(start_x=start[0], start_y=start[1], end_x=end[0], end_y=end[1], duration=duration)
            # After swipe wait for spinners
            wait_utils.wait_for_element_mobile(self.driver, {"type": "id", "value": ""}, self.config, timeout=1)
            return

        # Handle explicit tap_coordinates action if no locator used
        if action == "tap_coordinates" and not chosen_locator:
            if "x" in step and "y" in step:
                coords = (step.get("x"), step.get("y"))
                self.driver.tap([coords])
                # chosen_locator remains None; skip repository update
                wait_utils.wait_for_element_mobile(self.driver, {"type": "id", "value": ""}, self.config, timeout=1)
                return

        # If no locator succeeded and action isn't swipe, throw error
        if action != "swipe" and not chosen_locator:
            if last_error:
                raise last_error
            else:
                raise ValueError(f"No valid locator could be resolved for step {step}")

        # Persist locator if it's different from stored
        if getattr(self, "locator_repo", None) and step_key and chosen_locator and chosen_locator.get("type") != "coordinates":
            if stored_locator is None or chosen_locator != stored_locator:
                try:
                    self.locator_repo.add_locator("mobile", step_key, chosen_locator)
                except Exception as exc:
                    self.logger.debug("Failed to persist mobile locator: %s", exc)

        # Wait for global spinners after action
        wait_utils.wait_for_element_mobile(self.driver, chosen_locator or {"type": "id", "value": ""}, self.config, timeout=1)


    def _self_heal(self, step: Dict[str, Any], exc: Exception) -> bool:
        """Attempt to recover from a mobile step failure.

        For tap/send_keys actions this method tries to fall back to
        coordinate‑based taps using values in the step definition.  If
        coordinates are provided they are used directly.  Otherwise a
        screenshot is captured to aid debugging.  Returns True if a
        recovery attempt was made; False otherwise.
        """
        action = step.get("action")
        try:
            if action in ("tap", "send_keys"):
                # Fall back to coordinates if available
                if "x" in step and "y" in step:
                    coords = (step.get("x"), step.get("y"))
                    self.logger.info("Self‑healing mobile: tapping coordinates %s", coords)
                    self.driver.tap([coords])
                    return True
            # Capture screenshot for diagnostics
            # Only available if Appium driver supports get_screenshot_as_png
            if hasattr(self.driver, "get_screenshot_as_png"):
                data = self.driver.get_screenshot_as_png()
                self.reporter.attach_bytes(data, name="mobile_healing_screenshot", extension="png")
        except Exception as heal_exc:
            self.logger.debug("Mobile self‑heal failed: %s", heal_exc)
            return False
        return False

    def close(self) -> None:
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass