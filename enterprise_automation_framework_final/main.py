"""
CLI Entrypoint
--------------

This script allows users to import a BRD or test file, create a versioned
test set and execute the tests via the MCP router.  It accepts
optional arguments for the user story name and author.  See
`python main.py --help` for usage.
"""

import argparse
import pandas as pd
from pathlib import Path
from typing import List, Dict

from src.automation_framework.config import Config
from src.automation_framework.mcp_router import MCPRouter, TestCase
from src.automation_framework.versioning.version_manager import VersionManager
from src.automation_framework.reporting.reporter import Reporter


def read_brd(file_path: str) -> List[Dict[str, any]]:
    """Read an Excel or CSV file containing test cases.  Expected columns:

    * identifier – unique id of the test case
    * description – natural language description of the test
    * type – optional (ui, api, mobile, sql)
    * steps – JSON string representing a list of step dictionaries
    """
    path = Path(file_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    test_cases: List[Dict[str, any]] = []
    for _, row in df.iterrows():
        steps = row.get("steps")
        if isinstance(steps, str):
            try:
                import json
                parsed = json.loads(steps)
            except Exception:
                parsed = []
        else:
            parsed = steps if isinstance(steps, list) else []
        test_cases.append({
            "identifier": str(row.get("identifier")),
            "description": row.get("description"),
            "type": row.get("type"),
            "steps": parsed,
        })
    return test_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM‑native test automation framework")
    parser.add_argument("file", help="Path to BRD/test file (Excel or CSV)")
    parser.add_argument("user_story", help="Name of the user story or BRD")
    parser.add_argument("--author", default="anonymous", help="Author uploading the test set")
    args = parser.parse_args()
    # Load configuration and helper classes
    config = Config()
    version_manager = VersionManager(config)
    reporter = Reporter(config)
    router = MCPRouter(config, reporter)
    # Read test cases from file
    test_cases_data = read_brd(args.file)
    # Add version to store test cases with metadata
    metadata = version_manager.add_version(args.user_story, test_cases_data, args.author)
    print(f"Added version {metadata['version_number']} (similarity {metadata['similarity']*100:.0f}%);")
    # Convert to TestCase objects for router
    test_cases = [
        TestCase(identifier=tc["identifier"], steps=tc["steps"], type=tc.get("type"))
        for tc in test_cases_data
    ]
    # Run through MCPs
    router.run_all(test_cases)
    # Cleanup drivers
    router.close()
    version_manager.close()


if __name__ == "__main__":
    main()