
from __future__ import annotations

import argparse
import html
import importlib
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

from .utils import run

BASE = Path(__file__).resolve().parents[1]
PACKAGE_NAME = __package__.rsplit(".", 1)[0]

SKILL_LABELS = {
    "security_checker": "Security Checker",
    "env_validation": "Environment Validation",
    "security_testing": "Security Testing",
    "api_testing": "API Testing",
    "linting": "Linting",
    "typescript_quality": "TypeScript Quality",
    "code_coverage": "Code Coverage / Unit Testing",
    "accessibility": "Accessibility",
    "mobile": "Mobile Compatibility",
    "ios": "iOS",
    "android": "Android",
    "pwa_compliance": "PWA Compliance",
    "seo": "SEO",
    "dependency_health": "Dependency Health",
    "bundle_analysis": "Bundle Analysis",
    "performance": "Performance Testing",
    "uat": "UAT Testing",
    "mock_testing": "Mock Testing",
    "release_notes": "Release Notes",
    "feature_versioning": "Feature Versioning",
    "error_handling": "Error Handling",
    "database_safety": "Database Safety",
    "cross_browser": "Cross Browser",
    "documentation": "Documentation",
    "git_hygiene": "Git Hygiene",
    "ci_cd": "CI/CD",
}


def load_settings():
    settings_path = BASE / "config" / "settings.json"

    if not settings_path.is_file():
        raise FileNotFoundError(
            f"Settings file not found: {settings_path}"
        )

    with settings_path.open(encoding="utf-8") as file:
        settings = json.load(file)

    if not isinstance(settings, dict):
        raise ValueError("Settings must contain a JSON object.")

    return settings


def build_execution_order(settings):
    ordered = []
    seen = set()

    categories = settings.get("skill_categories", [])
    optional = settings.get("optional_skills", {})

    if not isinstance(categories, list):
        raise ValueError("'skill_categories' must be a list.")

    if not isinstance(optional, dict):
        raise ValueError("'optional_skills' must be an object.")

    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("Each skill category must be an object.")

        if not category.get("enabled", False):
            continue

        skills = category.get("skills", [])

        if not isinstance(skills, list):
            raise ValueError(
                f"Skills in category "
                f"'{category.get('name', 'Unknown')}' must be a list."
            )

        for module in skills:
            if module not in SKILL_LABELS:
                raise ValueError(
                    f"Unknown skill configured: {module}"
                )

            if module in seen:
                raise ValueError(
                    f"Duplicate skill configuration: {module}"
                )

            seen.add(module)
            ordered.append((SKILL_LABELS[module], module))

    for module, enabled in optional.items():
        if module not in SKILL_LABELS:
            raise ValueError(
                f"Unknown optional skill configured: {module}"
            )

        if enabled:
            if module in seen:
                raise ValueError(
                    f"Duplicate skill configuration: {module}"
                )

            seen.add(module)
            ordered.append((SKILL_LABELS[module], module))

    return ordered


def parse_command(command, setting_name):
    """Validate and convert a configured command into a list."""
    if isinstance(command, str):
        command = shlex.split(command)

    if (
        not isinstance(command, list)
        or not command
        or not all(
            isinstance(part, str) and part.strip()
            for part in command
        )
    ):
        raise ValueError(
            f"{setting_name} must be a non-empty string "
            "or a list of strings."
        )

    return command


def execute_configured_command(
    name,
    configured_command,
    project,
    timeout,
):
    """Execute a configured project command and return a stage record."""
    try:
        command = parse_command(
            configured_command,
            name,
        )

        execution = run(
            command,
            project,
            timeout=timeout,
        )

        if execution["returncode"] == 0:
            status = "PASS"
            summary = f"{name} command completed successfully."
        else:
            status = "FAIL"

            if execution.get("timed_out"):
                summary = (
                    f"{name} command exceeded the "
                    f"{timeout}-second timeout."
                )
            else:
                summary = (
                    f"{name} command failed with exit code "
                    f"{execution['returncode']}."
                )

        return {
            "skill": name,
            "status": status,
            "summary": summary,
            "findings": [],
            "details": execution,
        }

    except (ValueError, TypeError) as error:
        return {
            "skill": name,
            "status": "FAIL",
            "summary": f"Invalid command configuration: {error}",
            "findings": [],
            "details": {
                "command": configured_command,
            },
        }


def write_reports(project, records, metadata, formats=None):
    """Generate assessment reports inside the audited project."""
    out = Path(project).resolve() / "reports"
    out.mkdir(parents=True, exist_ok=True)

    summary = {
        "project": str(project),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "results": records,
    }

    if formats is None:
        formats = ["json", "html"]

    if not isinstance(formats, list):
        raise ValueError("report_formats must be a list.")

    if "json" in formats:
        (out / "assessment-report.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

    if "html" in formats:
        rows = []

        for record in records:
            status = str(
                record.get("status", "WARN")
            ).upper()

            rows.append(
                f"<tr><td>{html.escape(str(record.get('skill', 'Unknown')))}</td>"
                f"<td class='{status.lower()}'>{html.escape(status)}</td>"
                f"<td>{html.escape(str(record.get('summary', '')))}</td></tr>"
            )

        doc = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Complaudi Assessment</title>"
            "<style>body{font:15px system-ui;margin:36px;color:#172033}"
            "table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ddd;padding:10px;text-align:left}"
            ".pass{color:#087443}.warn{color:#9a6700}"
            ".fail{color:#b42318}</style></head><body>"
            "<h1>Complaudi Assessment Report</h1>"
            f"<p>Project: <code>{html.escape(str(project))}</code></p>"
            f"<p>Generated: {html.escape(summary['generated_at'])}</p>"
            "<table><thead><tr><th>Stage</th><th>Status</th>"
            "<th>Summary</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table><h2>Findings</h2>"
        )

        for record in records:
            findings = record.get("findings", [])

            if findings:
                doc += (
                    f"<h3>{html.escape(str(record.get('skill', 'Unknown')))}</h3><ul>"
                    + "".join(
                        f"<li>{html.escape(str(finding))}</li>"
                        for finding in findings
                    )
                    + "</ul>"
                )

        doc += "</body></html>"

        (out / "assessment-report.html").write_text(
            doc,
            encoding="utf-8",
        )

    return out


def main():
    parser = argparse.ArgumentParser(
        description="Complaudi sequential project assessment engine"
    )

    parser.add_argument(
        "--project",
        default=".",
        help="Local project directory to assess",
    )

    args = parser.parse_args()
    project = Path(args.project).resolve()

    if not project.is_dir():
        print(f"[ERROR] Project directory not found: {project}")
        return 2

    try:
        settings = load_settings()
        execution_order = build_execution_order(settings)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[ERROR] Configuration error: {error}")
        return 2

    try:
        performance_timeout = int(
            settings.get("performance_budget_seconds", 180)
        )

        if performance_timeout <= 0:
            raise ValueError

    except (TypeError, ValueError):
        print(
            "[ERROR] performance_budget_seconds must be "
            "a positive integer."
        )
        return 2

    print("=" * 48 + "\n COMPLAUDI SKILLS ENGINE\n" + "=" * 48)

    print("\n[01] CODE CHECKOUT")

    git = run(
        ["git", "rev-parse", "--show-toplevel"],
        project,
        timeout=20,
    )

    if git["returncode"] == 0:
        branch = run(
            ["git", "branch", "--show-current"],
            project,
            timeout=20,
        )

        dirty = run(
            ["git", "status", "--short"],
            project,
            timeout=20,
        )

        print(
            f"[PASS] Local repository: {git['output'].strip()} | "
            f"branch: {branch['output'].strip() or '(detached)'}"
        )

        if dirty["output"].strip():
            print(
                "[INFO] Working tree has local changes; "
                "they will be preserved."
            )

        checkout = {
            "skill": "Code Checkout",
            "status": "PASS",
            "summary": (
                "Validated current local Git working copy; "
                "no checkout/reset/stash performed."
            ),
            "findings": [],
            "details": {
                "branch": branch["output"].strip(),
                "working_tree": dirty["output"][:4000],
            },
        }

    else:
        print(
            "[WARN] Directory is not a Git repository; "
            "continuing with local files."
        )

        checkout = {
            "skill": "Code Checkout",
            "status": "WARN",
            "summary": (
                "No Git repository detected; "
                "assessed current local directory."
            ),
            "findings": [],
            "details": {},
        }

    print("\n[02] BUILD & COMPILATION")

    build_command = settings.get("build_command")

    if build_command:
        build_record = execute_configured_command(
            "Build & Compilation",
            build_command,
            project,
            timeout=900,
        )

    elif (project / "pyproject.toml").exists():
        build_record = execute_configured_command(
            "Build & Compilation",
            [sys.executable, "-m", "compileall", "-q", "."],
            project,
            timeout=300,
        )

    else:
        build_record = {
            "skill": "Build & Compilation",
            "status": "PASS",
            "summary": (
                "No recognized build command; build stage skipped."
            ),
            "findings": [],
            "details": {
                "command": [],
                "returncode": 0,
                "output": "Build stage skipped.",
                "duration_seconds": 0,
                "timed_out": False,
            },
        }

    print(
        f"[{build_record['status']}] Build: "
        f"{build_record['summary']}"
    )

    records = [
        checkout,
        build_record,
    ]

    print("\n[03] UNIT TESTS")

    unit_test_command = settings.get("unit_test_command")

    if unit_test_command:
        test_record = execute_configured_command(
            "Unit Tests",
            unit_test_command,
            project,
            timeout=performance_timeout,
        )
    else:
        test_record = {
            "skill": "Unit Tests",
            "status": "WARN",
            "summary": (
                "No unit_test_command configured; "
                "unit tests were skipped."
            ),
            "findings": [],
            "details": {},
        }

    records.append(test_record)
    print(
        f"[{test_record['status']}] "
        f"{test_record['summary']}"
    )

    print("\n[04] COVERAGE COMMAND")

    coverage_command = settings.get("coverage_command")

    if coverage_command:
        coverage_record = execute_configured_command(
            "Coverage Command",
            coverage_command,
            project,
            timeout=performance_timeout,
        )
    else:
        coverage_record = {
            "skill": "Coverage Command",
            "status": "WARN",
            "summary": (
                "No separate coverage_command configured. "
                "Coverage may be generated by the unit-test command, "
                "but it is not independently verified here."
            ),
            "findings": [],
            "details": {
                "coverage_in_unit_test_command": (
                    "--coverage"
                    in str(unit_test_command or "").lower()
                ),
            },
        }

    records.append(coverage_record)
    print(
        f"[{coverage_record['status']}] "
        f"{coverage_record['summary']}"
    )

    print("\n[05] SKILLS EXECUTION")

    for index, (label, module) in enumerate(
        execution_order,
        1,
    ):
        print(
            f"  [{index:02d}/{len(execution_order):02d}] "
            f"{label} ...",
            end=" ",
            flush=True,
        )

        try:
            skill_module = importlib.import_module(
                f"{PACKAGE_NAME}.skills.{module}.skill"
            )

            item = skill_module.execute(project)

            if not isinstance(item, dict):
                raise TypeError(
                    "Skill did not return a result dictionary."
                )

            item.setdefault("skill", label)
            item.setdefault("status", "WARN")
            item.setdefault(
                "summary",
                "Skill returned no summary.",
            )
            item.setdefault("findings", [])
            item.setdefault("details", {})

        except Exception as error:
            item = {
                "skill": label,
                "status": "FAIL",
                "summary": (
                    f"Skill crashed safely: "
                    f"{type(error).__name__}: {error}"
                ),
                "findings": [],
                "details": {},
            }

        records.append(item)
        print(item["status"])

    print("\n[06] REPORT GENERATION")

    try:
        report_module = importlib.import_module(
            f"{PACKAGE_NAME}.skills.report_generation.skill"
        )

        report_result = report_module.execute(project)

        if not isinstance(report_result, dict):
            raise TypeError(
                "Report generation did not return a result dictionary."
            )

        report_result.setdefault(
            "skill",
            "Report Generation",
        )
        report_result.setdefault("status", "WARN")
        report_result.setdefault(
            "summary",
            "Report generation completed.",
        )
        report_result.setdefault("findings", [])
        report_result.setdefault("details", {})

        records.append(report_result)

    except Exception as error:
        records.append({
            "skill": "Report Generation",
            "status": "FAIL",
            "summary": (
                f"Report generation skill failed: "
                f"{type(error).__name__}: {error}"
            ),
            "findings": [],
            "details": {},
        })

    formats = settings.get(
        "report_formats",
        ["json", "html"],
    )

    try:
        out = write_reports(
            project,
            records,
            {
                "checkout": "local working copy",
                "build_command": build_record["details"].get(
                    "command"
                ),
                "unit_test_command": unit_test_command,
                "coverage_command": coverage_command,
                "performance_budget_seconds": performance_timeout,
                "execution_order": [
                    module for _, module in execution_order
                ],
                "configured_skill_count": len(execution_order),
            },
            formats,
        )

        print(f"Reports saved: {out}")

    except Exception as error:
        records.append({
            "skill": "Report Writing",
            "status": "FAIL",
            "summary": (
                f"Could not write reports: "
                f"{type(error).__name__}: {error}"
            ),
            "findings": [],
            "details": {},
        })

        print(
            f"[FAIL] Report writing: "
            f"{type(error).__name__}: {error}"
        )

    counts = {
        status: sum(
            1
            for record in records
            if str(
                record.get("status", "")
            ).upper() == status
        )
        for status in ("PASS", "WARN", "FAIL")
    }

    print(
        "\n" + "=" * 48
        + "\n ASSESSMENT COMPLETED\n"
        + "=" * 48
    )

    print(
        f"Audit skills: {len(execution_order)} | "
        f"Total stages: {len(records)} | "
        f"Passed: {counts['PASS']} | "
        f"Warnings: {counts['WARN']} | "
        f"Failed: {counts['FAIL']}"
    )

    print(
        "Note: WARN means a check needs environment-specific setup "
        "or manual review; it is not a passed test."
    )

    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
