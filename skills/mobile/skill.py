
import re
from pathlib import Path

from ...core.utils import result, run


SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".next",
    "playwright-report",
    "test-results",
}

SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".html"}
STYLE_EXTENSIONS = {".css", ".scss", ".sass"}

MAX_FILE_SIZE = 1024 * 1024


def project_files(root, extensions):
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(root)

        if any(part in SKIP_DIRS for part in relative.parts):
            continue

        if path.suffix.lower() not in extensions:
            continue

        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue

        yield path


def read_file(path):
    try:
        return path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return ""


def execute(root):
    root = Path(root).resolve()

    findings = []
    details = {
        "responsive_design": {},
        "viewport": {},
        "overflow_signals": [],
        "touch_target_signals": [],
        "mobile_navigation": [],
    }

    source_files = list(
        project_files(root, SOURCE_EXTENSIONS)
    )

    style_files = list(
        project_files(root, STYLE_EXTENSIONS)
    )

    # 1. Check responsive CSS signals
    media_query_files = []
    responsive_unit_files = []

    for path in style_files:
        content = read_file(path)
        relative = str(path.relative_to(root))

        if re.search(r"@media\b", content, re.I):
            media_query_files.append(relative)

        if re.search(
            r"\b\d+(?:\.\d+)?(?:vw|vh|dvw|dvh|rem|%|em)\b",
            content,
            re.I,
        ):
            responsive_unit_files.append(relative)

        # 2. Detect possible horizontal overflow patterns
        if re.search(
            r"overflow-x\s*:\s*(hidden|clip)",
            content,
            re.I,
        ):
            details["overflow_signals"].append({
                "file": relative,
                "issue": "Horizontal overflow is being hidden. Verify that mobile content is not clipped.",
            })

        if re.search(
            r"min-width\s*:\s*\d{3,}px",
            content,
            re.I,
        ):
            details["overflow_signals"].append({
                "file": relative,
                "issue": "Large minimum width detected. Review layout behavior on narrow screens.",
            })

        # 3. Detect potentially small touch target styles
        if re.search(
            r"(?:width|height|min-width|min-height)"
            r"\s*:\s*(?:1[0-9]|2[0-9]|3[0-9])px",
            content,
            re.I,
        ):
            details["touch_target_signals"].append({
                "file": relative,
                "issue": "Small fixed dimensions detected. Verify interactive touch target sizes.",
            })

    details["responsive_design"] = {
        "stylesheet_count": len(style_files),
        "media_query_files": media_query_files[:50],
        "responsive_unit_files": responsive_unit_files[:50],
    }

    if style_files and not media_query_files:
        findings.append({
            "severity": "MEDIUM",
            "issue": "No CSS media queries detected. Review responsive behavior on mobile screens.",
        })

    # 4. Check viewport metadata
    html_files = list(
        project_files(root, {".html"})
    )

    viewport_found = False

    for path in html_files:
        content = read_file(path)

        if re.search(
            r'<meta\b[^>]*name\s*=\s*["\']viewport["\']',
            content,
            re.I,
        ):
            viewport_found = True
            break

    details["viewport"] = {
        "html_files_checked": len(html_files),
        "viewport_meta_found": viewport_found,
    }

    if html_files and not viewport_found:
        findings.append({
            "severity": "HIGH",
            "issue": "Mobile viewport metadata was not detected in HTML files.",
        })

    # 5. Check mobile navigation signals
    navigation_keywords = (
        "hamburger",
        "mobile-menu",
        "mobilemenu",
        "menutoggle",
        "navigation",
        "navbar",
    )

    for path in source_files:
        content = read_file(path)

        matched = [
            keyword
            for keyword in navigation_keywords
            if keyword in content.lower()
        ]

        if matched:
            details["mobile_navigation"].append({
                "file": str(path.relative_to(root)),
                "signals": matched,
            })

    # 6. Summarize potential layout and touch issues
    for item in details["overflow_signals"]:
        findings.append({
            "severity": "MEDIUM",
            "file": item["file"],
            "issue": item["issue"],
        })

    for item in details["touch_target_signals"]:
        findings.append({
            "severity": "INFO",
            "file": item["file"],
            "issue": item["issue"],
        })

    if not details["mobile_navigation"]:
        findings.append({
            "severity": "INFO",
            "issue": "No common mobile navigation signals detected. Verify navigation manually.",
        })

    # 7. Run existing mobile audit when available
    audit_script = root / "tests" / "mobile" / "audit.mjs"

    if audit_script.is_file():
        audit_result = run(
            ["node", str(audit_script)],
            root,
            timeout=300,
        )

        details["mobile_audit"] = {
            "executed": True,
            "returncode": audit_result["returncode"],
            "output": audit_result.get("output", "")[-4000:],
        }

        if audit_result["returncode"] != 0:
            findings.append({
                "severity": "HIGH",
                "issue": "Existing automated mobile audit script failed.",
            })
    else:
        details["mobile_audit"] = {
            "executed": False,
            "reason": "No tests/mobile/audit.mjs script found.",
        }

        findings.append({
            "severity": "INFO",
            "issue": "Automated device/browser mobile testing was not performed.",
        })

    details["summary"] = {
        "source_files_scanned": len(source_files),
        "stylesheet_files_scanned": len(style_files),
        "html_files_scanned": len(html_files),
        "responsive_stylesheet_count": len(media_query_files),
        "overflow_signals": len(details["overflow_signals"]),
        "touch_target_signals": len(details["touch_target_signals"]),
    }

    status = (
        "WARN"
        if any(
            finding["severity"] in {"HIGH", "MEDIUM"}
            for finding in findings
        )
        else "PASS"
    )

    return result(
        "Mobile Compatibility",
        status,
        "Inspected responsive CSS, viewport metadata, possible overflow, touch target styles and mobile navigation signals.",
        findings,
        details,
    )
