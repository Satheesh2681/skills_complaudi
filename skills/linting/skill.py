
import json
import os
import re
from pathlib import Path

from ...core.utils import run, result


SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
    "playwright-report",
    "test-results",
    "complaudi-master",
    "complaudi_full_starter",
}

LINT_CONFIGS = {
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.js",
    ".prettierrc.cjs",
    "prettier.config.js",
    "prettier.config.cjs",
    "biome.json",
    "biome.jsonc",
}

LINT_SCRIPT_PATTERN = re.compile(
    r"^(lint|lint:.*|format:check|check:format)$",
    re.IGNORECASE,
)

IGNORED_SCRIPT_PATTERN = re.compile(
    r"(typecheck|type-check|tsc|build|test)",
    re.IGNORECASE,
)


def find_package_files(root):
    packages = []

    for current, directories, filenames in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
        ]

        if "package.json" in filenames:
            packages.append(Path(current) / "package.json")

    return sorted(packages)


def find_lint_configs(root):
    configs = []

    for current, directories, filenames in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
        ]

        for filename in filenames:
            if filename in LINT_CONFIGS:
                config_path = Path(current) / filename
                configs.append(
                    str(config_path.relative_to(root))
                )

    return sorted(configs)


def inspect_packages(root):
    package_results = []

    for package_file in find_package_files(root):
        try:
            data = json.loads(
                package_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, dict):
            continue

        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            scripts = {}

        dependencies = {}

        for dependency_group in (
            data.get("dependencies", {}),
            data.get("devDependencies", {}),
        ):
            if isinstance(dependency_group, dict):
                dependencies.update(dependency_group)

        lint_scripts = {}

        for name, command in scripts.items():
            if not isinstance(name, str):
                continue

            if not LINT_SCRIPT_PATTERN.match(name):
                continue

            if IGNORED_SCRIPT_PATTERN.search(name):
                continue

            if isinstance(command, str):
                lint_scripts[name] = command

        package_results.append({
            "package_file": str(
                package_file.relative_to(root)
            ),
            "project_name": data.get(
                "name",
                package_file.parent.name
            ),
            "lint_scripts": lint_scripts,
            "eslint_dependency": "eslint" in dependencies,
            "prettier_dependency": "prettier" in dependencies,
            "biome_dependency": "@biomejs/biome" in dependencies,
        })

    return package_results


def execute_lint_script(root, package_file, script_name):
    package_dir = (root / package_file).parent

    execution = run(
        ["npm", "run", script_name],
        cwd=package_dir,
        timeout=180,
    )

    return {
        "package_file": package_file,
        "script": script_name,
        "returncode": execution["returncode"],
        "timed_out": execution["timed_out"],
        "duration_seconds": execution["duration_seconds"],
        "output": execution["output"][-3000:],
    }


def execute(root):
    root = Path(root).resolve()

    packages = inspect_packages(root)
    configs = find_lint_configs(root)

    findings = []
    executions = []
    configured_scripts = []

    for package in packages:
        for script_name in package["lint_scripts"]:
            configured_scripts.append((
                package["package_file"],
                script_name,
            ))

    for package_file, script_name in configured_scripts:
        execution = execute_lint_script(
            root,
            package_file,
            script_name,
        )

        executions.append(execution)

        if execution["timed_out"]:
            findings.append({
                "severity": "REVIEW",
                "file": package_file,
                "issue": (
                    f"Lint script '{script_name}' exceeded "
                    "the 180-second time limit."
                ),
            })

        elif execution["returncode"] != 0:
            findings.append({
                "severity": "ERROR",
                "file": package_file,
                "issue": (
                    f"Lint script '{script_name}' failed. "
                    "Review its execution output."
                ),
            })

    if not configured_scripts and not configs:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No dedicated lint scripts or recognized lint "
                "configuration files were found."
            ),
        })

    elif not configured_scripts:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "Lint configuration exists, but no dedicated "
                "lint script is configured in package.json."
            ),
        })

    if findings:
        status = "WARN"
    else:
        status = "PASS"

    summary = (
        f"Inspected {len(packages)} package files, "
        f"found {len(configs)} lint configurations, "
        f"executed {len(executions)} lint scripts, "
        f"and found {len(findings)} review items."
    )

    return result(
        "Linting",
        status,
        summary,
        findings,
        {
            "package_files_scanned": len(packages),
            "lint_configurations": configs,
            "configured_lint_scripts": [
                {
                    "package_file": package_file,
                    "script": script_name,
                }
                for package_file, script_name in configured_scripts
            ],
            "executed_lint_scripts": [
                {
                    "package_file": item["package_file"],
                    "script": item["script"],
                    "returncode": item["returncode"],
                    "timed_out": item["timed_out"],
                    "duration_seconds": item["duration_seconds"],
                }
                for item in executions
            ],
            "packages": packages,
            "typescript_checks_skipped": True,
            "note": (
                "Checks dedicated lint scripts and recognized "
                "lint configurations. Does not repeat TypeScript "
                "checks, builds, or unit tests. Missing lint "
                "configuration is a review item, not proof of "
                "source-code errors. No dependencies or "
                "application files are modified."
            ),
        },
    )
