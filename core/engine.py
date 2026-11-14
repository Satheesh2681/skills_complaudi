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
}


def load_settings():
    settings_path = BASE / "config" / "settings.json"

    if not settings_path.is_file():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    with settings_path.open(encoding="utf-8") as f:
        settings = json.load(f)

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
                raise ValueError(f"Unknown skill configured: {module}")

            if module in seen:
                raise ValueError(f"Duplicate skill configuration: {module}")

            seen.add(module)
            ordered.append((SKILL_LABELS[module], module))

    for module, enabled in optional.items():
        if module not in SKILL_LABELS:
            raise ValueError(f"Unknown optional skill configured: {module}")

        if enabled:
            if module in seen:
                raise ValueError(f"Duplicate skill configuration: {module}")

            seen.add(module)
            ordered.append((SKILL_LABELS[module], module))

    return ordered


def write_reports(project, records, metadata, formats=None):
    out = BASE / "reports"
    out.mkdir(parents=True, exist_ok=True)

    summary = {
        "project": str(project),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "results": records,
    }

    if formats is None:
        formats = ["json", "html"]

    if "json" in formats:
        (out / "assessment-report.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

    if "html" in formats:
        rows = []

        for record in records:
            status = str(record.get("status", "WARN")).upper()

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
            print("[INFO] Working tree has local changes; they will be preserved.")

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
        print("[WARN] Directory is not a Git repository; continuing with local files.")

        checkout = {
            "skill": "Code Checkout",
            "status": "WARN",
            "summary": "No Git repository detected; assessed current local directory.",
            "findings": [],
            "details": {},
        }

    print("\n[02] BUILD & COMPILATION")

    build_command = settings.get("build_command")

    if build_command:
        try:
            command = (
                shlex.split(build_command)
                if isinstance(build_command, str)
                else build_command
            )

            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(part, str) for part in command)
            ):
                raise ValueError(
                    "Build command must be a non-empty string or list of strings."
                )

            build = run(command, project, timeout=900)

        except (ValueError, TypeError) as error:
            build = {
                "returncode": 2,
                "output": f"Invalid build command: {error}",
                "duration_seconds": 0,
                "command": [],
            }

    elif (project / "pyproject.toml").exists():
        build = run(
            [sys.executable, "-m", "compileall", "-q", "."],
            project,
            timeout=300,
        )

    else:
        build = {
            "returncode": 0,
            "output": "No recognized build command; build stage skipped.",
            "duration_seconds": 0,
            "command": [],
        }

    build_status = "PASS" if build["returncode"] == 0 else "FAIL"

    print(
        f"[{build_status}] Build: "
        f"{build['output'][-700:].strip()}"
    )

    records = [
        checkout,
        {
            "skill": "Build & Compilation",
            "status": build_status,
            "summary": (
                "Build command completed."
                if build_status == "PASS"
                else "Build failed; assessment skills will still run."
            ),
            "findings": [],
            "details": build,
        },
    ]

    print("\n[03] SKILLS EXECUTION")

    for index, (label, module) in enumerate(execution_order, 1):
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
            item.setdefault("summary", "Skill returned no summary.")
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

    print("\n[04] REPORT GENERATION")

    try:
        report_module = importlib.import_module(
            f"{PACKAGE_NAME}.skills.report_generation.skill"
        )

        report_result = report_module.execute(project)

        if not isinstance(report_result, dict):
            raise TypeError(
                "Report generation did not return a result dictionary."
            )

        report_result.setdefault("skill", "Report Generation")
        report_result.setdefault("status", "WARN")
        report_result.setdefault("summary", "Report generation completed.")
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

    formats = settings.get("report_formats", ["json", "html"])

    out = write_reports(
        project,
        records,
        {
            "checkout": "local working copy",
            "build_command": build.get("command"),
            "execution_order": [
                module for _, module in execution_order
            ],
            "configured_skill_count": len(execution_order),
        },
        formats,
    )

    counts = {
        status: sum(
            1
            for record in records
            if str(record.get("status", "")).upper() == status
        )
        for status in ("PASS", "WARN", "FAIL")
    }

    print("\n" + "=" * 48 + "\n ASSESSMENT COMPLETED\n" + "=" * 48)

    print(
        f"Audit skills: {len(execution_order)} | "
        f"Total stages: {len(records)} | "
        f"Passed: {counts['PASS']} | "
        f"Warnings: {counts['WARN']} | "
        f"Failed: {counts['FAIL']}"
    )

    print(f"Report directory: {out}")

    print(
        "Note: WARN means a check needs environment-specific setup "
        "or manual review; it is not a passed test."
    )

    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
