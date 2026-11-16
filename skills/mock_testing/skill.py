import json
from pathlib import Path

from ...core.utils import result


SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv",
    "dist", "build", "coverage", ".next",
    "__pycache__", ".pytest_cache"
}

TEST_FILE_PATTERNS = (
    "*.test.js", "*.test.jsx", "*.test.ts", "*.test.tsx",
    "*.spec.js", "*.spec.jsx", "*.spec.ts", "*.spec.tsx",
    "test_*.py", "*_test.py"
)

MOCK_PACKAGES = {
    "jest",
    "vitest",
    "sinon",
    "jest-mock",
    "pytest-mock",
    "unittest.mock"
}


def execute(root):
    root = Path(root).resolve()
    findings = []
    test_files = []
    mock_signals = set()
    config_files = []

    for pattern in TEST_FILE_PATTERNS:
        for path in root.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            test_files.append(path)

    package_files = [
        root / "package.json",
        root / "web" / "package.json"
    ]

    for package_file in package_files:
        if not package_file.is_file():
            continue

        try:
            data = json.loads(package_file.read_text(encoding="utf-8"))
            dependencies = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {})
            }

            for package in MOCK_PACKAGES:
                if package in dependencies:
                    mock_signals.add(package)

            if data.get("scripts", {}).get("test"):
                config_files.append(str(package_file.relative_to(root)))

        except (OSError, json.JSONDecodeError):
            findings.append({
                "severity": "LOW",
                "file": str(package_file.relative_to(root)),
                "issue": "Could not read package.json"
            })

    python_test_dirs = [
        root / "tests",
        root / "test"
    ]

    for directory in python_test_dirs:
        if directory.is_dir():
            for path in directory.rglob("*.py"):
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                if path.name.startswith("test_") or path.name.endswith("_test.py"):
                    test_files.append(path)

    unique_tests = sorted(set(test_files))

    if not unique_tests:
        findings.append({
            "severity": "MEDIUM",
            "issue": "No recognizable test files found."
        })

    if not mock_signals:
        findings.append({
            "severity": "LOW",
            "issue": "No recognized mock testing library found in package dependencies."
        })

    status = "PASS" if unique_tests and mock_signals else "WARN"

    return result(
        "Mock Testing",
        status,
        (
            f"Static inspection found {len(unique_tests)} test files "
            f"and {len(mock_signals)} recognized mock libraries. "
            "Tests were not executed. No project files were modified."
        ),
        details={
            "test_files_found": len(unique_tests),
            "mock_libraries": sorted(mock_signals),
            "test_scripts_found": config_files,
            "findings": findings,
            "execution_performed": False
        }
    )