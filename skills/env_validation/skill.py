
import os
import re
from pathlib import Path

from ...core.utils import result


SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "playwright-report",
    "test-results",
    "__pycache__",
    ".cache",
}

ENV_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
}

SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    (?<![\w.$])
    ["']?
    ([A-Za-z_][A-Za-z0-9_-]*(?:api[_-]?key|secret|password|passwd|token|
       private[_-]?key|access[_-]?key|webhook[_-]?secret))
    ["']?
    \s*[:=]\s*
    (["'])
    ([^"'\\\r\n]{4,})
    \2
    """
)

PLACEHOLDER_VALUES = {
    "your_password",
    "your_secret",
    "your_api_key",
    "your_token",
    "changeme",
    "change_me",
    "example",
    "placeholder",
    "test",
    "dummy",
    "none",
    "null",
    "undefined",
}


def is_skipped(path, root):
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True

    return any(part in SKIP_DIRS for part in parts)


def is_env_filename(path):
    name = path.name.lower()
    return name in ENV_NAMES or name.startswith(".env.")


def walk_files(root):
    for current, dirs, filenames in os.walk(root):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in SKIP_DIRS
            and directory != "complaudi-master"
        ]

        for filename in filenames:
            path = Path(current) / filename

            if not is_skipped(path, root):
                yield path


def get_git_tracked_env_files(root):
    import subprocess

    try:
        check = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if check.returncode != 0:
            return None, "NOT_CHECKED"

        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if tracked.returncode != 0:
            return None, "NOT_CHECKED"

        env_files = [
            line.strip()
            for line in tracked.stdout.splitlines()
            if is_env_filename(Path(line.strip()))
        ]

        return env_files, "AVAILABLE"

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "NOT_CHECKED"


def check_gitignore(root):
    gitignore = root / ".gitignore"

    if not gitignore.is_file():
        return False

    try:
        content = gitignore.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return False

    patterns = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    return any(
        pattern in {".env", ".env.*", "*.env"}
        or pattern.startswith(".env")
        for pattern in patterns
    )


def is_test_file(relative_path):
    path_lower = relative_path.lower().replace("\\", "/")
    parts = path_lower.split("/")

    return (
        any(
            part in {"test", "tests", "__tests__"}
            for part in parts
        )
        or ".test." in path_lower
        or ".spec." in path_lower
    )


def scan_source_secrets(root, source_files):
    findings = []

    for path in source_files:
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            continue

        relative = str(path.relative_to(root))
        test_file = is_test_file(relative)

        for line_number, line in enumerate(content.splitlines(), 1):
            for match in SECRET_ASSIGNMENT_PATTERN.finditer(line):
                value = match.group(3).strip()

                if not value:
                    continue

                if value.lower() in PLACEHOLDER_VALUES:
                    continue

                if value.lower().startswith(
                    (
                        "your_",
                        "replace_",
                        "example_",
                        "test_",
                        "dummy_",
                    )
                ):
                    continue

                if value.startswith(("$", "{", "`")):
                    continue

                if test_file:
                    findings.append({
                        "severity": "INFO",
                        "file": relative,
                        "line": line_number,
                        "issue": (
                            "Credential-like value found in a test file. "
                            "Verify that it is synthetic and not a live "
                            "secret. Value is hidden."
                        ),
                    })
                else:
                    findings.append({
                        "severity": "REVIEW",
                        "file": relative,
                        "line": line_number,
                        "issue": (
                            "Possible hardcoded credential literal. "
                            "Value is hidden."
                        ),
                    })

    return findings


def execute(root):
    root = Path(root).resolve()

    all_files = list(walk_files(root))

    environment_files = [
        str(path.relative_to(root))
        for path in all_files
        if is_env_filename(path)
    ]

    environment_templates = []

    for path in all_files:
        if path.name.lower() in {
            ".env.example",
            ".env.sample",
            ".env.template",
        }:
            try:
                content = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

                variables = []

                for line in content.splitlines():
                    line = line.strip()

                    if (
                        not line
                        or line.startswith("#")
                        or "=" not in line
                    ):
                        continue

                    key = line.split("=", 1)[0].strip()

                    if key:
                        variables.append(key)

                environment_templates.append({
                    "file": str(path.relative_to(root)),
                    "variable_count": len(variables),
                    "variables": variables,
                })

            except OSError:
                pass

    source_files = [
        path
        for path in all_files
        if path.suffix.lower() in {
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".mjs",
            ".cjs",
            ".py",
            ".html",
            ".sh",
        }
    ]

    findings = scan_source_secrets(root, source_files)

    tracked_env_files, git_status = get_git_tracked_env_files(root)

    if git_status == "NOT_CHECKED":
        findings.insert(0, {
            "severity": "REVIEW",
            "issue": (
                "Git repository status could not be verified. "
                "Tracked environment files are NOT_CHECKED."
            ),
        })

    elif tracked_env_files:
        for filename in tracked_env_files:
            findings.append({
                "severity": "REVIEW",
                "file": filename,
                "issue": "Environment file is tracked by Git.",
            })

    gitignore_protects_env = check_gitignore(root)

    if environment_files and not gitignore_protects_env:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "Environment files exist, but .gitignore protection "
                "could not be confirmed."
            ),
        })

    required_template_variables = ["NODE_ENV"]

    template_variables = {
        variable
        for template in environment_templates
        for variable in template["variables"]
    }

    missing_required = [
        variable
        for variable in required_template_variables
        if variable not in template_variables
    ]

    if missing_required:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "Required environment variables are missing from "
                "the environment template: "
                + ", ".join(missing_required)
            ),
        })

    possible_secrets = sum(
        1
        for finding in findings
        if finding.get("severity") == "REVIEW"
        and "Possible hardcoded credential literal"
        in finding.get("issue", "")
    )

    test_fixture_items = sum(
        1
        for finding in findings
        if finding.get("severity") == "INFO"
    )

    review_items = sum(
        1
        for finding in findings
        if finding.get("severity") == "REVIEW"
    )

    status = "WARN" if review_items else "PASS"

    summary = (
        f"Found {len(environment_files)} environment files, "
        f"{len(environment_templates)} templates, "
        f"Git tracking {git_status}, "
        f"{possible_secrets} possible hardcoded credentials, "
        f"and {test_fixture_items} test-file review items."
    )

    details = {
        "environment_files": environment_files,
        "environment_templates": environment_templates,
        "tracked_environment_files": tracked_env_files,
        "git_status": git_status,
        "git_available": git_status == "AVAILABLE",
        "gitignore_protects_env": gitignore_protects_env,
        "source_files_scanned": len(source_files),
        "possible_hardcoded_secrets": possible_secrets,
        "test_fixture_items": test_fixture_items,
        "review_items": review_items,
        "required_template_variables": required_template_variables,
        "missing_required_template_variables": missing_required,
        "secret_values_exposed": False,
        "environment_files_modified": False,
        "note": (
            "Static environment validation. Credential detection checks "
            "quoted string literals assigned to recognized credential "
            "names. Test-file findings are INFO items and still require "
            "verification. False positives and undetected secrets are "
            "possible. Git tracking is NOT_CHECKED when no Git repository "
            "is available. No files or dependencies are modified."
        ),
    }

    return result(
        "Environment Validation",
        status,
        summary,
        findings,
        details,
    )
