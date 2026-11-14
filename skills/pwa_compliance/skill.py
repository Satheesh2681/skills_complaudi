
import json
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

SOURCE_EXTENSIONS = {
    ".html",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
}

MANIFEST_NAMES = {
    "manifest.json",
    "site.webmanifest",
    "manifest.webmanifest",
}

SERVICE_WORKER_NAMES = {
    "service-worker.js",
    "service-worker.ts",
    "sw.js",
    "sw.ts",
}


def walk_files(root):
    for current, dirs, filenames in __import__("os").walk(root):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in SKIP_DIRS
            and directory != "complaudi-master"
        ]

        for filename in filenames:
            path = Path(current) / filename

            try:
                if path.is_file():
                    yield path
            except OSError:
                continue


def read_text(path):
    try:
        return path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return ""


def relative_path(path, root):
    return str(path.relative_to(root)).replace("\\", "/")


def find_manifests(files):
    return [
        path
        for path in files
        if path.name.lower() in MANIFEST_NAMES
    ]


def find_service_workers(files):
    return [
        path
        for path in files
        if path.name.lower() in SERVICE_WORKER_NAMES
    ]


def find_html_files(files):
    return [
        path
        for path in files
        if path.suffix.lower() == ".html"
    ]


def check_manifest(manifest_paths, root):
    findings = []
    manifest_details = []

    for path in manifest_paths:
        relative = relative_path(path, root)
        content = read_text(path)

        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            findings.append({
                "severity": "REVIEW",
                "file": relative,
                "issue": "Web app manifest contains invalid JSON.",
            })
            continue

        if not isinstance(data, dict):
            findings.append({
                "severity": "REVIEW",
                "file": relative,
                "issue": "Web app manifest must contain a JSON object.",
            })
            continue

        required_fields = [
            "name",
            "short_name",
            "start_url",
            "display",
            "icons",
        ]

        missing_fields = [
            field
            for field in required_fields
            if not data.get(field)
        ]

        for field in missing_fields:
            findings.append({
                "severity": "REVIEW",
                "file": relative,
                "issue": (
                    f"Manifest is missing or has an empty "
                    f"'{field}' field."
                ),
            })

        icons = data.get("icons", [])
        valid_icons = []

        if isinstance(icons, list):
            for icon in icons:
                if isinstance(icon, dict) and icon.get("src"):
                    valid_icons.append(icon)

        if not valid_icons:
            findings.append({
                "severity": "REVIEW",
                "file": relative,
                "issue": "Manifest does not define a usable icon entry.",
            })

        icon_paths = []

        for icon in valid_icons:
            icon_src = icon.get("src", "")

            if not isinstance(icon_src, str):
                continue

            if (
                icon_src.startswith(("http://", "https://", "data:"))
                or icon_src.startswith("/")
            ):
                continue

            icon_path = (path.parent / icon_src).resolve()

            try:
                icon_path.relative_to(root)
            except ValueError:
                continue

            icon_paths.append(icon_path)

        missing_icons = [
            str(icon.relative_to(root)).replace("\\", "/")
            for icon in icon_paths
            if not icon.is_file()
        ]

        for icon in missing_icons:
            findings.append({
                "severity": "REVIEW",
                "file": relative,
                "issue": f"Manifest icon file was not found: {icon}",
            })

        manifest_details.append({
            "file": relative,
            "name_present": bool(data.get("name")),
            "short_name_present": bool(data.get("short_name")),
            "start_url_present": bool(data.get("start_url")),
            "display": data.get("display"),
            "icon_count": len(valid_icons),
            "missing_icon_files": missing_icons,
        })

    return findings, manifest_details


def check_html_links(html_files, root):
    findings = []
    manifest_links = []
    service_worker_signals = False

    manifest_pattern = re.compile(
        r'<link\b[^>]*rel\s*=\s*["\']manifest["\'][^>]*>',
        re.IGNORECASE,
    )

    for path in html_files:
        content = read_text(path)

        if manifest_pattern.search(content):
            manifest_links.append(relative_path(path, root))

        if re.search(
            r"serviceWorker\.register\s*\(",
            content,
            re.IGNORECASE,
        ):
            service_worker_signals = True

    if not manifest_links:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No HTML manifest link was detected. "
                "Check whether the application links its web app manifest."
            ),
        })

    return findings, manifest_links, service_worker_signals


def check_source_signals(files):
    registration_files = []
    offline_files = []
    https_files = []

    for path in files:
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue

        content = read_text(path)

        if re.search(
            r"serviceWorker\.register\s*\(",
            content,
            re.IGNORECASE,
        ):
            registration_files.append(path)

        if re.search(
            r"caches\.(?:open|match|keys|delete)\s*\(",
            content,
            re.IGNORECASE,
        ):
            offline_files.append(path)

        if re.search(
            r"upgrade-insecure-requests|Strict-Transport-Security",
            content,
            re.IGNORECASE,
        ):
            https_files.append(path)

    return registration_files, offline_files, https_files


def check_https_configuration(files):
    config_files = [
        path
        for path in files
        if path.name.lower() in {
            "vercel.json",
            "netlify.toml",
            "nginx.conf",
            "web.config",
            "firebase.json",
        }
    ]

    https_signals = []

    for path in config_files:
        content = read_text(path)

        if re.search(
            r"https|Strict-Transport-Security|force\s*:\s*true",
            content,
            re.IGNORECASE,
        ):
            https_signals.append(path.name)

    return https_signals


def execute(root):
    root = Path(root).resolve()
    files = list(walk_files(root))

    manifest_paths = find_manifests(files)
    service_worker_paths = find_service_workers(files)
    html_files = find_html_files(files)

    findings = []

    manifest_findings, manifest_details = check_manifest(
        manifest_paths,
        root,
    )
    findings.extend(manifest_findings)

    if not manifest_paths:
        findings.append({
            "severity": "REVIEW",
            "issue": "No web app manifest file was found.",
        })

    html_findings, manifest_links, html_sw_signal = check_html_links(
        html_files,
        root,
    )
    findings.extend(html_findings)

    (
        registration_files,
        offline_files,
        https_source_files,
    ) = check_source_signals(files)

    if not service_worker_paths:
        findings.append({
            "severity": "REVIEW",
            "issue": "No conventional service worker file was found.",
        })

    if not registration_files and not html_sw_signal:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No service worker registration call was detected."
            ),
        })

    if not offline_files:
        findings.append({
            "severity": "INFO",
            "issue": (
                "No Cache API usage was detected. "
                "Offline support could not be confirmed statically."
            ),
        })

    https_signals = check_https_configuration(files)

    if not https_signals and not https_source_files:
        findings.append({
            "severity": "INFO",
            "issue": (
                "No HTTPS enforcement configuration signal was detected. "
                "Verify HTTPS at the hosting or reverse-proxy level."
            ),
        })

    review_items = sum(
        1
        for finding in findings
        if finding.get("severity") == "REVIEW"
    )

    info_items = sum(
        1
        for finding in findings
        if finding.get("severity") == "INFO"
    )

    status = "WARN" if review_items else "PASS"

    summary = (
        f"Scanned {len(files)} files, found "
        f"{len(manifest_paths)} manifest files, "
        f"{len(service_worker_paths)} service worker files, "
        f"{len(registration_files)} registration signals, "
        f"and {review_items} review items."
    )

    details = {
        "files_scanned": len(files),
        "html_files_scanned": len(html_files),
        "manifest_files": [
            relative_path(path, root)
            for path in manifest_paths
        ],
        "manifest_links": manifest_links,
        "manifest_details": manifest_details,
        "service_worker_files": [
            relative_path(path, root)
            for path in service_worker_paths
        ],
        "service_worker_registration_files": [
            relative_path(path, root)
            for path in registration_files
        ],
        "offline_cache_signal_files": [
            relative_path(path, root)
            for path in offline_files
        ],
        "https_source_signal_files": [
            relative_path(path, root)
            for path in https_source_files
        ],
        "https_configuration_signals": https_signals,
        "review_items": review_items,
        "info_items": info_items,
        "live_installability_tested": False,
        "live_https_tested": False,
        "offline_runtime_tested": False,
        "note": (
            "Static PWA compliance checks only. File names and source "
            "patterns are heuristic signals. This skill does not launch "
            "a browser, verify live HTTPS, test installation, or confirm "
            "runtime offline behavior. No application files or "
            "dependencies are modified."
        ),
    }

    return result(
        "PWA Compliance",
        status,
        summary,
        findings,
        details,
    )
