
import json
import re
from pathlib import Path

from ...core.utils import result, text_files


TEST_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py"}

TEST_FILE_PATTERN = re.compile(
    r"(^|/)(tests?|e2e|__tests__)/|"
    r"\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$",
    re.IGNORECASE,
)

CATEGORY_PATTERNS = {
    "authentication": re.compile(
        r"\b(login|log\s*in|logout|log\s*out|sign\s*in|sign\s*up|"
        r"register|authentication|authorization)\b",
        re.IGNORECASE,
    ),
    "form_validation": re.compile(
        r"\b(form|validation|validate|required field|invalid input|"
        r"submit|error message)\b",
        re.IGNORECASE,
    ),
    "navigation": re.compile(
        r"\b(navigate|navigation|redirect|routing|route|"
        r"page navigation)\b",
        re.IGNORECASE,
    ),
    "api_integration": re.compile(
        r"\b(api|fetch\(|axios|request|response|endpoint|"
        r"status code|integration)\b",
        re.IGNORECASE,
    ),
    "error_handling": re.compile(
        r"\b(error handling|error boundary|exception|"
        r"unhandled|failure|error state)\b",
        re.IGNORECASE,
    ),
    "acceptance_criteria": re.compile(
        r"\b(acceptance criteria|user story|given when then|"
        r"expected result|should allow|should display)\b",
        re.IGNORECASE,
    ),
}

RUNNER_CONFIGS = {
    "Playwright": [
        "playwright.config.js",
        "playwright.config.ts",
        "playwright.config.mjs",
    ],
    "Cypress": [
        "cypress.config.js",
        "cypress.config.ts",
        "cypress.config.mjs",
    ],
}


def execute(root):
    root = Path(root)
    findings = []
    details = {
        "analysis_type": "Static UAT test inspection",
        "test_runners": [],
        "test_files": [],
        "category_coverage": {},
        "tests_executed": False,
    }

    package_path = root / "package.json"
    package_data = {}

    if package_path.exists():
        try:
            package_data = json.loads(
                package_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            findings.append({
                "severity": "INFO",
                "issue": "Could not parse package.json.",
            })

    scripts = package_data.get("scripts", {})
    details["available_test_scripts"] = {
        name: command
        for name, command in scripts.items()
        if any(word in name.lower() for word in ("test", "e2e", "uat"))
    }

    dependencies = {}
    dependencies.update(package_data.get("dependencies", {}))
    dependencies.update(package_data.get("devDependencies", {}))

    if "playwright" in dependencies or "playwright-core" in dependencies:
        details["test_runners"].append("Playwright")

    if "cypress" in dependencies:
        details["test_runners"].append("Cypress")

    if "jest" in dependencies:
        details["test_runners"].append("Jest")

    if "vitest" in dependencies:
        details["test_runners"].append("Vitest")

    if "mocha" in dependencies:
        details["test_runners"].append("Mocha")

    for runner, config_names in RUNNER_CONFIGS.items():
        if any((root / name).exists() for name in config_names):
            if runner not in details["test_runners"]:
                details["test_runners"].append(runner)

    category_files = {name: set() for name in CATEGORY_PATTERNS}
    test_files = []

    for path, content in text_files(root):
        relative = path.relative_to(root).as_posix()

        if path.suffix.lower() not in TEST_EXTENSIONS:
            continue

        if not TEST_FILE_PATTERN.search(relative):
            continue

        test_files.append(relative)

        for category, pattern in CATEGORY_PATTERNS.items():
            if pattern.search(content):
                category_files[category].add(relative)

    details["test_files"] = test_files[:200]
    details["total_test_files_detected"] = len(test_files)

    for category, matched_files in category_files.items():
        details["category_coverage"][category] = {
            "status": "DETECTED" if matched_files else "NOT_DETECTED",
            "matching_test_files": len(matched_files),
            "files": sorted(matched_files)[:20],
        }

    if not details["test_runners"]:
        findings.append({
            "severity": "MEDIUM",
            "issue": "No supported test runner configuration or dependency detected.",
        })

    if not test_files:
        findings.append({
            "severity": "HIGH",
            "issue": "No recognizable automated test files detected.",
        })

    for category, matched_files in category_files.items():
        if not matched_files:
            findings.append({
                "severity": "INFO",
                "issue": f"No test files with {category.replace('_', ' ')} signals detected.",
            })

    if not details["available_test_scripts"]:
        findings.append({
            "severity": "INFO",
            "issue": "No test-related npm scripts detected in package.json.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Detected {len(test_files)} test files, "
        f"{len(details['test_runners'])} test runner signals, "
        f"and {sum(bool(files) for files in category_files.values())} "
        f"of {len(CATEGORY_PATTERNS)} UAT categories with test signals. "
        "No tests were executed."
    )

    return result(
        "UAT Testing",
        status,
        summary,
        findings,
        details,
    )
