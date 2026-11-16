
import re

from ...core.utils import result, text_files


SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

SKIP_DIRECTORIES = {
    "node_modules", ".git", ".venv", "venv", "dist",
    "build", "coverage", ".next", "__pycache__",
}


def execute(root):
    findings = []
    source_files = []

    for path, content in text_files(root):
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue

        if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            continue

        source_files.append((path, content))

    if not source_files:
        return result(
            "Error Handling",
            "WARN",
            "No JavaScript or TypeScript source files found.",
            findings,
            {"files_scanned": 0},
        )

    checks = {
        "error_boundaries": re.compile(
            r"componentDidCatch|getDerivedStateFromError|ErrorBoundary",
            re.IGNORECASE,
        ),
        "async_try_catch": re.compile(
            r"async\s+(?:function\s+)?[\w$]*[^{}]*\{[^{}]*\btry\s*\{",
            re.DOTALL,
        ),
        "global_error_handlers": re.compile(
            r"window\.onerror|window\.addEventListener\s*\(\s*['\"]error['\"]|"
            r"process\.on\s*\(\s*['\"]uncaughtException['\"]",
            re.IGNORECASE,
        ),
        "promise_rejection_handlers": re.compile(
            r"unhandledrejection|process\.on\s*\(\s*['\"]unhandledRejection['\"]",
            re.IGNORECASE,
        ),
    }

    counts = {name: 0 for name in checks}

    for path, content in source_files:
        for name, pattern in checks.items():
            matches = pattern.findall(content)
            counts[name] += len(matches)

    if counts["error_boundaries"] == 0:
        findings.append({
            "severity": "MEDIUM",
            "message": "No React Error Boundary pattern detected.",
            "recommendation": "Review whether critical React UI sections need Error Boundaries.",
        })

    if counts["async_try_catch"] == 0:
        findings.append({
            "severity": "MEDIUM",
            "message": "No async try/catch pattern detected.",
            "recommendation": "Review asynchronous operations for appropriate error handling.",
        })

    if counts["global_error_handlers"] == 0:
        findings.append({
            "severity": "LOW",
            "message": "No global error handler pattern detected.",
            "recommendation": "Consider adding global error logging where appropriate.",
        })

    if counts["promise_rejection_handlers"] == 0:
        findings.append({
            "severity": "MEDIUM",
            "message": "No unhandled Promise rejection handler detected.",
            "recommendation": "Review how unhandled Promise rejections are captured and logged.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {len(source_files)} source files. "
        f"Found {counts['error_boundaries']} Error Boundary signals, "
        f"{counts['async_try_catch']} async try/catch signals, "
        f"{counts['global_error_handlers']} global error handler signals, "
        f"and {counts['promise_rejection_handlers']} Promise rejection handler signals."
    )

    return result(
        "Error Handling",
        status,
        summary,
        findings,
        {
            "files_scanned": len(source_files),
            "checks": counts,
            "analysis_type": "Heuristic static analysis",
        },
    )
