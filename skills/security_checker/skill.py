
import json
import re
from pathlib import Path

from ...core.utils import files, run, result


SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv",
    "dist", "build", "coverage", ".next",
    "__pycache__", ".pytest_cache"
}

SAMPLE_ENV_FILES = {
    ".env.example",
    ".env.sample",
    ".env.template",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".env",
    ".sh", ".sql", ".md", ".txt",
    ".xml", ".properties", ".dockerfile"
}

SECRET_PATTERNS = {
    "AWS access key": (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "CRITICAL"
    ),
    "Private key": (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "CRITICAL"
    ),
    "Google Cloud service account key": (
        re.compile(
            r'"type"\s*:\s*"service_account".{0,2000}'
            r'"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----"',
            re.IGNORECASE | re.DOTALL
        ),
        "CRITICAL"
    ),
    "Azure client secret assignment": (
        re.compile(
            r'(?i)\b(?:AZURE_CLIENT_SECRET|'
            r'ARM_CLIENT_SECRET)\s*[:=]\s*["\']?'
            r'[A-Za-z0-9_~./+=-]{12,}'
        ),
        "HIGH"
    ),
    "Database connection string with credentials": (
        re.compile(
            r'(?i)\b(?:postgres|postgresql|mysql|mongodb|'
            r'mongodb\+srv)://[^/\s:@]+:[^@\s]+@'
        ),
        "HIGH"
    ),
    "JWT secret assignment": (
        re.compile(
            r'(?i)\b(?:JWT_SECRET|JWT_SIGNING_KEY|'
            r'JWT_PRIVATE_KEY)\s*[:=]\s*["\'][^"\']{8,}["\']'
        ),
        "HIGH"
    ),
    "Possible hardcoded password": (
        re.compile(
            r'(?i)\b(?:DB_PASSWORD|DATABASE_PASSWORD|'
            r'DATABASE_PASS|DB_PASS)\s*[:=]\s*["\']'
            r'[^"\']{8,}["\']'
        ),
        "HIGH"
    ),
    "Possible hardcoded API token": (
        re.compile(
            r'(?i)\b(?:API_SECRET|API_TOKEN|ACCESS_TOKEN|'
            r'CLIENT_SECRET)\s*[:=]\s*["\']'
            r'[^"\']{12,}["\']'
        ),
        "HIGH"
    ),
}


def add_finding(findings, severity, issue, file=None):
    finding = {
        "severity": severity,
        "issue": issue
    }

    if file:
        finding["file"] = file

    findings.append(finding)


def execute(root):
    root = Path(root)
    findings = []
    details = {
        "analysis_type": "Static security and dependency inspection",
        "secret_scan": {},
        "git_hygiene": {},
        "dependency_audits": {},
        "docker_checks": {},
        "secret_values_redacted": True
    }

    # 1. Scan repository files for possible secrets.
    scanned_files = 0
    secret_counts = {}
    env_files = []

    for path in files(root):
        relative_parts = path.relative_to(root).parts

        if any(part in SKIP_DIRS for part in relative_parts):
            continue

        if path.name in SAMPLE_ENV_FILES:
            continue

        is_env_file = path.name.startswith(".env")

        if is_env_file:
            env_files.append(path.relative_to(root).as_posix())

        if path.suffix.lower() not in TEXT_EXTENSIONS and not is_env_file:
            continue

        try:
            if path.stat().st_size > 2_000_000:
                continue

            content = path.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except OSError:
            continue

        scanned_files += 1
        relative = path.relative_to(root).as_posix()

        for label, (pattern, severity) in SECRET_PATTERNS.items():
            matches = pattern.findall(content)

            if matches:
                secret_counts[label] = (
                    secret_counts.get(label, 0) + len(matches)
                )

                add_finding(
                    findings,
                    severity,
                    f"Possible {label} detected. Secret value was not recorded."
                    ,
                    relative
                )

    for env_file in env_files:
        add_finding(
            findings,
            "HIGH",
            "Environment file exists. Verify that it is excluded from Git tracking.",
            env_file
        )

    details["secret_scan"] = {
        "files_scanned": scanned_files,
        "possible_secret_matches": secret_counts,
        "environment_files_found": env_files,
        "secret_values_recorded": False
    }

    # 2. Check Git-tracked environment files.
    git_result = run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        root,
        timeout=30
    )

    if git_result["returncode"] == 0:
        tracked_result = run(
            ["git", "ls-files"],
            root,
            timeout=60
        )

        tracked_env = []

        if tracked_result["returncode"] == 0:
            tracked_env = [
                line.strip()
                for line in tracked_result["output"].splitlines()
                if Path(line.strip()).name.startswith(".env")
                and Path(line.strip()).name not in SAMPLE_ENV_FILES
            ]

            for env_file in tracked_env:
                add_finding(
                    findings,
                    "CRITICAL",
                    "Environment file is tracked by Git. Verify that it contains no real credentials.",
                    env_file
                )

        details["git_hygiene"] = {
            "git_repository_detected": True,
            "tracked_environment_files": tracked_env
        }

        # 3. Check Git history for possible exposed secrets.
        history_pattern = (
            r"AKIA[0-9A-Z]{16}|"
            r"-----BEGIN .*PRIVATE KEY-----|"
            r"(?i)(JWT_SECRET|DB_PASSWORD|AZURE_CLIENT_SECRET)"
            r"\s*[:=]\s*['\"][^'\"]{8,}"
        )

        history_result = run(
            [
                "git", "log",
                "--all",
                "--format=%h %s",
                "-G", history_pattern,
                "--",
                "."
            ],
            root,
            timeout=120
        )

        history_matches = []

        if history_result["returncode"] == 0:
            history_matches = [
                line.strip()
                for line in history_result["output"].splitlines()
                if line.strip()
            ]

            if history_matches:
                add_finding(
                    findings,
                    "HIGH",
                    "Possible secret-related changes detected in Git history. Review the matching commits securely."
                )

        details["git_hygiene"]["possible_secret_history_commits"] = (
            history_matches[:50]
        )
        details["git_hygiene"]["history_scan_completed"] = (
            history_result["returncode"] == 0
        )

    else:
        details["git_hygiene"] = {
            "git_repository_detected": False
        }

        add_finding(
            findings,
            "INFO",
            "Git repository unavailable; tracked-file and history checks were skipped."
        )

    # 4. npm dependency audit.
    if (root / "package-lock.json").exists():
        npm_audit = run(
            ["npm", "audit", "--json"],
            root,
            timeout=300
        )

        details["dependency_audits"]["npm"] = {
            "returncode": npm_audit["returncode"],
            "timed_out": npm_audit["timed_out"],
            "completed": npm_audit["returncode"] in (0, 1)
        }

        if npm_audit["returncode"] == 1:
            try:
                audit_data = json.loads(npm_audit["output"])
                vulnerabilities = audit_data.get(
                    "metadata", {}
                ).get("vulnerabilities", {})

                details["dependency_audits"]["npm"][
                    "vulnerabilities"
                ] = vulnerabilities

                if any(vulnerabilities.values()):
                    add_finding(
                        findings,
                        "HIGH",
                        "npm audit reported dependency vulnerabilities. Review the npm audit report."
                    )

            except (json.JSONDecodeError, AttributeError):
                add_finding(
                    findings,
                    "INFO",
                    "npm audit reported an issue; detailed vulnerability information could not be parsed."
                )

        elif npm_audit["returncode"] not in (0, 1):
            add_finding(
                findings,
                "INFO",
                "npm audit could not complete. Check npm availability and network access."
            )

    # 5. Python dependency audit.
    requirements = [
        root / "requirements.txt",
        root / "requirements-dev.txt"
    ]

    python_requirements = [
        path for path in requirements if path.exists()
    ]

    if python_requirements:
        if len(python_requirements) == 1:
            pip_audit = run(
                [
                    "pip-audit",
                    "--requirement",
                    str(python_requirements[0]),
                    "--format",
                    "json"
                ],
                root,
                timeout=300
            )

            details["dependency_audits"]["python"] = {
                "returncode": pip_audit["returncode"],
                "completed": pip_audit["returncode"] in (0, 1),
                "timed_out": pip_audit["timed_out"]
            }

            if pip_audit["returncode"] == 1:
                add_finding(
                    findings,
                    "HIGH",
                    "Python dependency audit reported possible vulnerabilities."
                )

            elif pip_audit["returncode"] == 127:
                add_finding(
                    findings,
                    "INFO",
                    "pip-audit is not installed; Python dependency vulnerabilities were not checked."
                )

            elif pip_audit["returncode"] not in (0, 1):
                add_finding(
                    findings,
                    "INFO",
                    "Python dependency audit could not complete."
                )

        else:
            details["dependency_audits"]["python"] = {
                "completed": False,
                "issue": "Multiple requirements files found; audit each file separately."
            }

    # 6. Docker security signals.
    docker_files = []

    for path in files(root):
        if path.name.lower() in {"dockerfile", "containerfile"}:
            docker_files.append(path)

    docker_findings = []

    for path in docker_files:
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except OSError:
            continue

        relative = path.relative_to(root).as_posix()

        if not re.search(r"(?im)^\s*USER\s+\S+", content):
            docker_findings.append(relative)
            add_finding(
                findings,
                "MEDIUM",
                "Dockerfile does not declare a non-default runtime USER. Verify container privilege configuration.",
                relative
            )

        if re.search(
            r"(?im)^\s*(?:ENV|ARG)\s+"
            r"(?:PASSWORD|SECRET|TOKEN|API_KEY)\s*=",
            content
        ):
            add_finding(
                findings,
                "HIGH",
                "Possible secret declared through Docker ENV or ARG. Use a secure secrets mechanism.",
                relative
            )

    details["docker_checks"] = {
        "dockerfiles_found": len(docker_files),
        "dockerfiles_without_user": docker_findings
    }

    # Final result.
    critical_count = sum(
        1 for item in findings
        if item["severity"] == "CRITICAL"
    )

    high_count = sum(
        1 for item in findings
        if item["severity"] == "HIGH"
    )

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {scanned_files} files; detected "
        f"{critical_count} critical and {high_count} high-severity "
        f"potential findings. Checked Git hygiene, available dependency "
        f"audit tools and Docker security signals. "
        f"Findings require manual verification."
    )

    return result(
        "Security Checker",
        status,
        summary,
        findings[:500],
        details
    )
