
import json
import re
from pathlib import Path

from ...core.utils import result, run


PACKAGE_FILES = [
    "package.json",
    "web/package.json",
]

SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?"
    r"(?:\+([0-9A-Za-z.-]+))?$"
)


def read_package(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def parse_version(version):
    if not isinstance(version, str):
        return None

    match = SEMVER_PATTERN.fullmatch(version.strip())

    if not match:
        return None

    major, minor, patch, prerelease, build = match.groups()

    return (
        int(major),
        int(minor),
        int(patch),
        prerelease or "",
    )


def normalize_tag(tag):
    tag = tag.strip()

    if tag.startswith("v"):
        tag = tag[1:]

    return tag


def execute(root):
    root = Path(root).resolve()

    findings = []
    details = {
        "package_versions": {},
        "invalid_versions": [],
        "git_tags": [],
        "latest_semver_tag": None,
        "version_consistency": {},
    }

    # 1. Read project package versions
    for relative_path in PACKAGE_FILES:
        package_path = root / relative_path

        if not package_path.is_file():
            continue

        package = read_package(package_path)

        if package is None:
            findings.append({
                "severity": "HIGH",
                "file": relative_path,
                "issue": "Package JSON is invalid or unreadable.",
            })
            continue

        version = package.get("version")

        if not version:
            findings.append({
                "severity": "MEDIUM",
                "file": relative_path,
                "issue": "Project version is missing from package.json.",
            })
            continue

        details["package_versions"][relative_path] = version

        if not parse_version(version):
            details["invalid_versions"].append({
                "file": relative_path,
                "version": version,
            })

            findings.append({
                "severity": "HIGH",
                "file": relative_path,
                "issue": f"Version '{version}' does not follow the expected semantic version format.",
            })

    # 2. Check root and frontend version consistency
    versions = details["package_versions"]

    if (
        "package.json" in versions
        and "web/package.json" in versions
    ):
        root_version = versions["package.json"]
        web_version = versions["web/package.json"]

        matches = root_version == web_version

        details["version_consistency"] = {
            "root_version": root_version,
            "web_version": web_version,
            "matches": matches,
        }

        if not matches:
            findings.append({
                "severity": "MEDIUM",
                "issue": "Root package.json and web/package.json versions do not match.",
            })

    # 3. Read Git tags
    tags_result = run(
        ["git", "tag", "--sort=-version:refname"],
        root,
        timeout=30,
    )

    tags = []

    if tags_result["returncode"] == 0:
        tags = [
            tag.strip()
            for tag in tags_result["output"].splitlines()
            if tag.strip()
        ]

    details["git_tags"] = tags[:10]

    if tags_result["returncode"] != 0:
        findings.append({
            "severity": "INFO",
            "issue": "Git tags could not be retrieved. Check whether the project is a Git repository.",
        })

    # 4. Find latest valid semantic version tag
    valid_tags = []

    for tag in tags:
        normalized = normalize_tag(tag)
        parsed = parse_version(normalized)

        if parsed:
            valid_tags.append((parsed, normalized, tag))

    valid_tags.sort(key=lambda item: item[0], reverse=True)

    if valid_tags:
        latest_tag = valid_tags[0][1]
        details["latest_semver_tag"] = latest_tag
    else:
        latest_tag = None

    # 5. Compare project version with latest semantic tag
    root_version = versions.get("package.json")

    if root_version and parse_version(root_version) and latest_tag:
        matches = root_version == latest_tag

        details["version_consistency"]["latest_git_tag_matches_root"] = matches

        if not matches:
            findings.append({
                "severity": "MEDIUM",
                "issue": (
                    f"Root project version {root_version} does not match "
                    f"the latest semantic Git tag {latest_tag}."
                ),
            })

    elif root_version and parse_version(root_version) and not tags:
        findings.append({
            "severity": "INFO",
            "issue": "No Git tags are available to compare with the project version.",
        })

    elif root_version and parse_version(root_version) and not latest_tag:
        findings.append({
            "severity": "INFO",
            "issue": "No valid semantic version Git tag was found.",
        })

    # 6. Check release version availability
    if not versions:
        findings.append({
            "severity": "HIGH",
            "issue": "No valid package version information was found.",
        })

    details["summary"] = {
        "package_files_found": len(versions),
        "invalid_version_count": len(details["invalid_versions"]),
        "git_tag_count": len(tags),
        "valid_semver_tag_count": len(valid_tags),
    }

    has_issues = any(
        item["severity"] in {"HIGH", "MEDIUM"}
        for item in findings
    )

    status = "WARN" if has_issues else "PASS"

    return result(
        "Feature Versioning",
        status,
        "Checked semantic versions, package version consistency, Git tags and release version readiness. No version files or Git tags were modified.",
        findings,
        details,
    )
