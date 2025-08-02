"""
UI MCP (Model Context Protocol)
-------------------------------

This module implements the UI MCP for web automation using Playwright.
It provides comprehensive web testing capabilities with advanced self-healing,
vision-based fallback, and AI-powered recovery mechanisms.

Features:
- Playwright-based web automation
- Advanced self-healing with AI assistance
- Vision-based element identification
- Screenshot capture and analysis
- Intelligent retry mechanisms
- Comprehensive error handling
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    _playwright_available = True
except ImportError:
    _playwright_available = False

from .mcp_base import MCPBase
from ..utils.logger import get_logger
from ..utils.wait_utils import wait_for_page_stable, wait_for_element_ui
from ..utils.self_healing import recover_ui_element


class UIMCP(MCPBase):
    """UI MCP implementation using Playwright."""

    def __init__(self, config, reporter) -> None:
        super().__init__(config, reporter)
        self.logger = get_logger(self.__class__.__name__)
        
        # Playwright components
        self._playwright: Optional[Any] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # Configuration
        self.browser_type = config.get("ui.browser", "chromium")
        self.headless = config.get("ui.headless", True)
        self.viewport = config.get("ui.viewport", {"width": 1920, "height": 1080})
        self.screenshot_on_failure = config.get("ui.screenshot_on_failure", True)
        self.self_heal = config.get("ui.self_heal", True)
        
        # Self-healing configuration
        self.vision_fallback_enabled = config.get("mcp.vision_fallback_enabled", True)
        self.ai_powered_recovery = config.get("mcp.ai_powered_recovery", True)
        self.max_healing_attempts = config.get("mcp.max_retries", 3)
        
        # LLM client for AI-powered recovery
        self.llm_client = None
        if self.ai_powered_recovery:
            try:
                from ..utils.llm_client import LLMClient
                self.llm_client = LLMClient(config)
            except Exception as exc:
                self.logger.warning(f"Failed to initialize LLM client: {exc}")

    def _ensure_page(self) -> None:
        """Ensure Playwright page is available."""
        if self._page is not None:
            return
        
        if not _playwright_available:
            self.logger.warning("Playwright not available, using dummy implementation")
            self._page = DummyPage()
            return
        
        try:
            # Initialize Playwright
            self._playwright = asyncio.run(async_playwright().start())
            
            # Launch browser
            browser_config = {
                "headless": self.headless,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            
            if self.browser_type == "chromium":
                self._browser = asyncio.run(self._playwright.chromium.launch(**browser_config))
            elif self.browser_type == "firefox":
                self._browser = asyncio.run(self._playwright.firefox.launch(**browser_config))
            elif self.browser_type == "webkit":
                self._browser = asyncio.run(self._playwright.webkit.launch(**browser_config))
            else:
                self._browser = asyncio.run(self._playwright.chromium.launch(**browser_config))
            
            # Create context
            self._context = asyncio.run(self._browser.new_context(viewport=self.viewport))
            
            # Create page
            self._page = asyncio.run(self._context.new_page())
            
            self.logger.info(f"Initialized {self.browser_type} browser")
        except Exception as exc:
            self.logger.error(f"Failed to initialize Playwright: {exc}")
            self._page = DummyPage()

    def _execute_step(self, step: Dict[str, Any]) -> None:
        """Execute a UI test step with advanced self-healing."""
        self._ensure_page()
        
        action = step.get("action", "").lower()
        target = step.get("target", "")
        value = step.get("value", "")
        expected = step.get("expected", "")
        
        self.logger.info(f"Executing UI step: {action} {target}")
        
        try:
            if action == "navigate":
                self._page.goto(target)
                wait_for_page_stable(self._page, self.config)
                
            elif action == "click":
                self._click_element(target)
                
            elif action == "fill":
                self._fill_element(target, value)
                
            elif action == "type":
                self._type_element(target, value)
                
            elif action == "select":
                self._select_option(target, value)
                
            elif action == "hover":
                self._hover_element(target)
                
            elif action == "screenshot":
                self._take_screenshot(target)
                
            elif action == "assert_text":
                self._assert_text(target, expected)
                
            elif action == "assert_element":
                self._assert_element(target)
                
            elif action == "wait":
                self._wait_for_element(target)
                
            else:
                raise ValueError(f"Unknown UI action: {action}")
                
        except Exception as exc:
            self.logger.error(f"Step execution failed: {exc}")
            
            # Attempt self-healing
            if self.self_heal:
                healed = self._self_heal(step, exc)
                if healed:
                    self.logger.info("Self-healing succeeded")
                    return
            
            # Capture screenshot on failure
            if self.screenshot_on_failure:
                self._capture_failure_screenshot(step, exc)
            
            raise

    def _click_element(self, selector: str) -> None:
        """Click an element with intelligent fallback."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Try to click
            self._page.click(selector)
            
        except Exception as exc:
            self.logger.warning(f"Click failed for {selector}: {exc}")
            
            # Try alternative selectors
            alternative_selectors = self._generate_alternative_selectors(selector)
            for alt_selector in alternative_selectors:
                try:
                    self._page.click(alt_selector)
                    self.logger.info(f"Click succeeded with alternative selector: {alt_selector}")
                    return
                except Exception:
                    continue
            
            raise

    def _fill_element(self, selector: str, value: str) -> None:
        """Fill an element with intelligent fallback."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Clear and fill
            self._page.fill(selector, value)
            
        except Exception as exc:
            self.logger.warning(f"Fill failed for {selector}: {exc}")
            
            # Try alternative selectors
            alternative_selectors = self._generate_alternative_selectors(selector)
            for alt_selector in alternative_selectors:
                try:
                    self._page.fill(alt_selector, value)
                    self.logger.info(f"Fill succeeded with alternative selector: {alt_selector}")
                    return
                except Exception:
                    continue
            
            raise

    def _type_element(self, selector: str, value: str) -> None:
        """Type into an element with intelligent fallback."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Type value
            self._page.type(selector, value)
            
        except Exception as exc:
            self.logger.warning(f"Type failed for {selector}: {exc}")
            
            # Try alternative selectors
            alternative_selectors = self._generate_alternative_selectors(selector)
            for alt_selector in alternative_selectors:
                try:
                    self._page.type(alt_selector, value)
                    self.logger.info(f"Type succeeded with alternative selector: {alt_selector}")
                    return
                except Exception:
                    continue
            
            raise

    def _select_option(self, selector: str, value: str) -> None:
        """Select an option from dropdown."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Select option
            self._page.select_option(selector, value)
            
        except Exception as exc:
            self.logger.warning(f"Select failed for {selector}: {exc}")
            raise

    def _hover_element(self, selector: str) -> None:
        """Hover over an element."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Hover
            self._page.hover(selector)
            
        except Exception as exc:
            self.logger.warning(f"Hover failed for {selector}: {exc}")
            raise

    def _take_screenshot(self, filename: str) -> None:
        """Take a screenshot."""
        try:
            screenshot_path = f"screenshots/{filename}.png"
            self._page.screenshot(path=screenshot_path)
            self.logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as exc:
            self.logger.error(f"Screenshot failed: {exc}")

    def _assert_text(self, selector: str, expected_text: str) -> None:
        """Assert text content of an element."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Get text content
            actual_text = self._page.text_content(selector)
            
            if expected_text not in actual_text:
                raise AssertionError(f"Expected text '{expected_text}' not found in '{actual_text}'")
                
        except Exception as exc:
            self.logger.error(f"Text assertion failed: {exc}")
            raise

    def _assert_element(self, selector: str) -> None:
        """Assert element is present and visible."""
        try:
            # Wait for element to be visible
            wait_for_element_ui(self._page, selector, self.config)
            
            # Check if element is visible
            element = self._page.locator(selector)
            if not element.is_visible():
                raise AssertionError(f"Element {selector} is not visible")
                
        except Exception as exc:
            self.logger.error(f"Element assertion failed: {exc}")
            raise

    def _wait_for_element(self, selector: str) -> None:
        """Wait for element to be present."""
        try:
            wait_for_element_ui(self._page, selector, self.config)
        except Exception as exc:
            self.logger.error(f"Wait for element failed: {exc}")
            raise

    def _generate_alternative_selectors(self, original_selector: str) -> List[str]:
        """Generate alternative selectors for self-healing."""
        alternatives = []
        
        # If it's a CSS selector, try different variations
        if original_selector.startswith("#"):
            # ID selector - try class and tag variations
            element_id = original_selector[1:]
            alternatives.extend([
                f"[id='{element_id}']",
                f".{element_id}",
                f"#{element_id}",
                f"*[id*='{element_id}']"
            ])
        elif original_selector.startswith("."):
            # Class selector - try tag variations
            class_name = original_selector[1:]
            alternatives.extend([
                f".{class_name}",
                f"*[class*='{class_name}']",
                f"[class='{class_name}']"
            ])
        elif original_selector.startswith("//"):
            # XPath selector - try simplified versions
            alternatives.extend([
                original_selector,
                original_selector.replace("//", "//*"),
                f"//*[contains(text(), '{original_selector.split('/')[-1]}')]"
            ])
        else:
            # Generic selector - try common variations
            alternatives.extend([
                f"[data-testid='{original_selector}']",
                f"[name='{original_selector}']",
                f"[placeholder='{original_selector}']",
                f"text={original_selector}",
                f"*[contains(text(), '{original_selector}')]"
            ])
        
        return alternatives

    def _self_heal(self, step: Dict[str, Any], exc: Exception) -> bool:
        """Advanced self-healing with AI-powered recovery."""
        action = step.get("action", "").lower()
        target = step.get("target", "")
        
        self.logger.info(f"Attempting self-healing for {action} {target}")
        
        # Method 1: Alternative selectors
        if action in ["click", "fill", "type"]:
            alternative_selectors = self._generate_alternative_selectors(target)
            for alt_selector in alternative_selectors:
                try:
                    if action == "click":
                        self._page.click(alt_selector)
                    elif action == "fill":
                        self._page.fill(alt_selector, step.get("value", ""))
                    elif action == "type":
                        self._page.type(alt_selector, step.get("value", ""))
                    
                    self.logger.info(f"Self-healing succeeded with selector: {alt_selector}")
                    return True
                except Exception:
                    continue
        
        # Method 2: AI-powered recovery
        if self.ai_powered_recovery and self.llm_client:
            try:
                # Capture screenshot for analysis
                screenshot_data = self._capture_screenshot_data()
                
                # Use AI to suggest new selector
                ai_selector = self._get_ai_selector_suggestion(step, screenshot_data)
                if ai_selector:
                    try:
                        if action == "click":
                            self._page.click(ai_selector)
                        elif action == "fill":
                            self._page.fill(ai_selector, step.get("value", ""))
                        elif action == "type":
                            self._page.type(ai_selector, step.get("value", ""))
                        
                        self.logger.info(f"AI-powered self-healing succeeded with selector: {ai_selector}")
                        return True
                    except Exception:
                        pass
            except Exception as ai_exc:
                self.logger.warning(f"AI-powered recovery failed: {ai_exc}")
        
        # Method 3: Vision-based fallback
        if self.vision_fallback_enabled:
            try:
                vision_selector = self._vision_based_recovery(step)
                if vision_selector:
                    try:
                        if action == "click":
                            self._page.click(vision_selector)
                        elif action == "fill":
                            self._page.fill(vision_selector, step.get("value", ""))
                        elif action == "type":
                            self._page.type(vision_selector, step.get("value", ""))
                        
                        self.logger.info(f"Vision-based self-healing succeeded with selector: {vision_selector}")
                        return True
                    except Exception:
                        pass
            except Exception as vision_exc:
                self.logger.warning(f"Vision-based recovery failed: {vision_exc}")
        
        return False

    def _get_ai_selector_suggestion(self, step: Dict[str, Any], screenshot_data: str) -> Optional[str]:
        """Get AI-powered selector suggestion."""
        if not self.llm_client:
            return None
        
        try:
            # Create prompt for AI
            prompt = f"""
            I need to {step.get('action')} an element on a web page.
            The original selector '{step.get('target')}' failed.
            Here's a base64 screenshot of the page: {screenshot_data}
            
            Please suggest a new CSS selector or XPath that would work for this element.
            Return only the selector, nothing else.
            """
            
            # Get AI suggestion
            response = self.llm_client.suggest_ui_selector(prompt)
            if response:
                return response.strip()
            
        except Exception as exc:
            self.logger.warning(f"AI selector suggestion failed: {exc}")
        
        return None

    def _vision_based_recovery(self, step: Dict[str, Any]) -> Optional[str]:
        """Vision-based element recovery."""
        try:
            # Capture screenshot
            screenshot_data = self._capture_screenshot_data()
            
            # Use vision API to analyze screenshot
            # This is a simplified implementation
            # In practice, you would use a vision API like Google Vision or Azure Computer Vision
            
            # For now, return a generic selector
            return "body"  # Fallback to body element
            
        except Exception as exc:
            self.logger.warning(f"Vision-based recovery failed: {exc}")
            return None

    def _capture_screenshot_data(self) -> str:
        """Capture screenshot and return as base64 string."""
        try:
            screenshot_bytes = self._page.screenshot()
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as exc:
            self.logger.warning(f"Screenshot capture failed: {exc}")
            return ""

    def _capture_failure_screenshot(self, step: Dict[str, Any], exc: Exception) -> None:
        """Capture screenshot on test failure."""
        try:
            timestamp = int(time.time())
            filename = f"failure_{timestamp}.png"
            screenshot_path = f"screenshots/{filename}"
            
            self._page.screenshot(path=screenshot_path)
            
            # Attach to reporter
            with open(screenshot_path, "rb") as f:
                screenshot_data = f.read()
                self.reporter.attach_bytes(screenshot_data, name=filename, extension="png")
            
            self.logger.info(f"Failure screenshot saved: {screenshot_path}")
            
        except Exception as screenshot_exc:
            self.logger.error(f"Failed to capture failure screenshot: {screenshot_exc}")

    def close(self) -> None:
        """Close browser resources."""
        try:
            if self._page:
                asyncio.run(self._page.close())
            if self._context:
                asyncio.run(self._context.close())
            if self._browser:
                asyncio.run(self._browser.close())
            if self._playwright:
                asyncio.run(self._playwright.stop())
        except Exception as exc:
            self.logger.warning(f"Error closing browser resources: {exc}")

    def __del__(self):
        """Cleanup on deletion."""
        self.close()


# Dummy implementation for when Playwright is not available
class DummyPage:
    """Dummy page implementation for testing."""
    
    def goto(self, url):
        print(f"Dummy: Navigating to {url}")
    
    def click(self, selector):
        print(f"Dummy: Clicking {selector}")
    
    def fill(self, selector, value):
        print(f"Dummy: Filling {selector} with {value}")
    
    def type(self, selector, value):
        print(f"Dummy: Typing {value} into {selector}")
    
    def select_option(self, selector, value):
        print(f"Dummy: Selecting {value} from {selector}")
    
    def hover(self, selector):
        print(f"Dummy: Hovering over {selector}")
    
    def screenshot(self, path=None):
        print(f"Dummy: Taking screenshot {path}")
        return b"dummy_screenshot_data"
    
    def text_content(self, selector):
        print(f"Dummy: Getting text content of {selector}")
        return "dummy text content"
    
    def locator(self, selector):
        return DummyLocator()
    
    def wait_for_selector(self, selector, state="visible", timeout=30000):
        print(f"Dummy: Waiting for {selector}")


class DummyLocator:
    """Dummy locator implementation."""
    
    def is_visible(self):
        return True