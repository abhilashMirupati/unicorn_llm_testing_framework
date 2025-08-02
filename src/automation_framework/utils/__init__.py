"""
Utility subpackage for the automation framework.

This package aggregates commonly used helpers such as logging,
locator persistence, wait functions, LLM clients and alerting.
Importing from this package exposes the most frequently used names to
simplify imports in higher‑level modules.

```
from automation_framework.utils import get_logger, LocatorRepo, wait_for_element_ui
```
"""

from .logger import get_logger
from .locator_repo import LocatorRepo
from .wait_utils import (
    wait_for_page_stable,
    wait_for_element_ui,
    wait_for_element_mobile,
    add_indicator,
)

# NOTE: We intentionally do not import the llm_client module here to avoid
# circular dependencies (Config imports utils.logger, which would
# indirectly import llm_client and thus Config again).  Consumers should
# import LLMClient and related classes directly from
# ``automation_framework.utils.llm_client`` when needed.

__all__ = [
    "get_logger",
    "LocatorRepo",
    "wait_for_page_stable",
    "wait_for_element_ui",
    "wait_for_element_mobile",
    "add_indicator",
]