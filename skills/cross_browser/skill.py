
import re

from ...core.utils import result, text_files


def execute(root):
    findings = []
    css_files = []
    counts = {
        "supports_rules": 0,
        "vendor_prefixes": 0,
        "gap_properties": 0,
        "aspect_ratio_properties": 0,
    }

    for path, content in text_files(root):
        if path.suffix.lower() not in {".css", ".scss", ".sass", ".less"}:
            continue

        css_files.append(str(path.relative_to(root)))

        counts["supports_rules"] += len(
            re.findall(r"@supports\b", content, re.IGNORECASE)
        )
        counts["vendor_prefixes"] += len(
            re.findall(r"(?<![\w-])-(?:webkit|moz|ms|o)-[\w-]+", content, re.IGNORECASE)
        )
        counts["gap_properties"] += len(
            re.findall(r"(?<![\w-])(?:row-gap|column-gap|gap)\s*:", content, re.IGNORECASE)
        )
        counts["aspect_ratio_properties"] += len(
            re.findall(r"(?<![\w-])aspect-ratio\s*:", content, re.IGNORECASE)
        )

    if not css_files:
        return result(
            "Cross Browser",
            "WARN",
            "No CSS, SCSS, Sass, or Less files found.",
            findings,
            {"css_files_scanned": 0, "checks": counts},
        )

    if counts["supports_rules"] == 0:
        findings.append({
            "severity": "LOW",
            "message": "No CSS @supports feature detection rules found.",
            "recommendation": "Consider feature detection for CSS features requiring compatibility fallbacks.",
        })

    if counts["gap_properties"] and counts["supports_rules"] == 0:
        findings.append({
            "severity": "LOW",
            "message": "CSS gap properties found without @supports rules.",
            "recommendation": "Review whether older target browsers need layout fallbacks.",
        })

    if counts["aspect_ratio_properties"] == 0:
        findings.append({
            "severity": "INFO",
            "message": "No CSS aspect-ratio properties detected.",
            "recommendation": "If fixed image or media proportions are needed, review responsive sizing.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {len(css_files)} stylesheet files. "
        f"Found {counts['supports_rules']} @supports rules, "
        f"{counts['vendor_prefixes']} vendor-prefixed properties, "
        f"{counts['gap_properties']} gap properties, "
        f"and {counts['aspect_ratio_properties']} aspect-ratio properties."
    )

    return result(
        "Cross Browser",
        status,
        summary,
        findings,
        {
            "css_files_scanned": len(css_files),
            "checks": counts,
            "analysis_type": "Heuristic static analysis",
        },
    )
