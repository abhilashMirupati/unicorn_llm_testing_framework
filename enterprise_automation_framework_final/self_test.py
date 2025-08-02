"""
Self‑Test Script
----------------

This script exercises the entire automation pipeline with sample data.
It creates a versioned test set from the provided sample BRD, routes
each test case to the appropriate MCP, and produces an Allure report.
Run it after installing dependencies to verify that the framework is
functioning correctly.
"""

import json
from pathlib import Path

from src.automation_framework.config import Config
from src.automation_framework.mcp_router import MCPRouter, TestCase
from src.automation_framework.versioning.version_manager import VersionManager
from src.automation_framework.reporting.reporter import Reporter


def load_sample_cases() -> list[dict[str, any]]:
    sample_file = Path(__file__).parent / "tests" / "sample_brd.xlsx"
    import pandas as pd
    df = pd.read_excel(sample_file)
    cases = []
    for _, row in df.iterrows():
        steps = row.get("steps")
        if isinstance(steps, str):
            try:
                parsed = json.loads(steps)
            except Exception:
                parsed = []
        else:
            parsed = steps if isinstance(steps, list) else []
        cases.append({
            "identifier": row.get("identifier"),
            "description": row.get("description"),
            "type": row.get("type"),
            "steps": parsed,
        })
    return cases


def run_self_test() -> None:
    config = Config()
    version_manager = VersionManager(config)
    reporter = Reporter(config)
    router = MCPRouter(config, reporter)
    # Load sample test cases and add as new version
    test_cases_data = load_sample_cases()
    metadata = version_manager.add_version("sample_user_story", test_cases_data, "self_test")
    print(f"Created version {metadata['version_number']} for sample_user_story (similarity {metadata['similarity']*100:.0f}% )")
    test_cases = [
        TestCase(identifier=tc["identifier"], steps=tc["steps"], type=tc.get("type"))
        for tc in test_cases_data
    ]
    router.run_all(test_cases)
    router.close()
    version_manager.close()
    print("Self test completed. Allure results saved to", config.get("allure.results_dir"))


if __name__ == "__main__":
    run_self_test()