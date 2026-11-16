
import re
from pathlib import Path

from ...core.utils import result, text_files


def execute(root):
    findings = []
    workflow_dir = root / ".github" / "workflows"

    workflows = []
    if workflow_dir.is_dir():
        workflows = [
            path for path in workflow_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
        ]

    workflow_contents = []
    for path in workflows:
        try:
            workflow_contents.append(
                path.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            pass

    combined = "\n".join(workflow_contents)

    has_test_step = bool(re.search(
        r"\b(?:npm\s+test|pytest|jest|vitest|playwright\s+test|"
        r"run:\s*.*\btest\b|uses:.*test)",
        combined,
        re.IGNORECASE,
    ))

    has_deploy_step = bool(re.search(
        r"\b(?:deploy|deployment|publish|release)\b",
        combined,
        re.IGNORECASE,
    ))

    secret_tools = [
        "gitleaks",
        "trufflehog",
        "detect-secrets",
        "secretlint",
    ]
    secret_scanning = [
        tool for tool in secret_tools
        if re.search(re.escape(tool), combined, re.IGNORECASE)
    ]

    github_secret_scanning = bool(re.search(
        r"secret[_ -]?scanning|codeql",
        combined,
        re.IGNORECASE,
    ))

    if not workflows:
        findings.append({
            "severity": "HIGH",
            "message": "No GitHub Actions workflow files detected.",
            "recommendation": "Add CI/CD workflows under .github/workflows/.",
        })
    else:
        if not has_test_step:
            findings.append({
                "severity": "MEDIUM",
                "message": "No recognizable automated test step detected in workflows.",
                "recommendation": "Add an automated test step to the CI pipeline.",
            })

        if not has_deploy_step:
            findings.append({
                "severity": "LOW",
                "message": "No recognizable deployment or release step detected.",
                "recommendation": "Review whether automated deployment is required.",
            })

    if not secret_scanning and not github_secret_scanning:
        findings.append({
            "severity": "MEDIUM",
            "message": "No recognizable secret-scanning tool or workflow signal detected.",
            "recommendation": "Consider adding Gitleaks, TruffleHog, or GitHub secret scanning.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Found {len(workflows)} GitHub Actions workflow files. "
        f"Test step: {'detected' if has_test_step else 'not detected'}. "
        f"Deployment step: {'detected' if has_deploy_step else 'not detected'}. "
        f"Secret scanning signals: {len(secret_scanning) + int(github_secret_scanning)}."
    )

    return result(
        "CI/CD",
        status,
        summary,
        findings,
        {
            "workflow_files": [
                str(path.relative_to(root)) for path in workflows
            ],
            "test_step_detected": has_test_step,
            "deployment_step_detected": has_deploy_step,
            "secret_scanning_tools": secret_scanning,
            "github_secret_scanning_detected": github_secret_scanning,
            "analysis_type": "Heuristic static analysis",
        },
    )
