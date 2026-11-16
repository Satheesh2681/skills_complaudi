
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ...core.utils import result


SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "Pods",
    "DerivedData",
}

PRIVACY_KEYS = {
    "NSCameraUsageDescription": "Camera",
    "NSMicrophoneUsageDescription": "Microphone",
    "NSPhotoLibraryUsageDescription": "Photo Library",
    "NSPhotoLibraryAddUsageDescription": "Photo Library Add",
    "NSLocationWhenInUseUsageDescription": "Location When In Use",
    "NSLocationAlwaysAndWhenInUseUsageDescription": "Background Location",
    "NSContactsUsageDescription": "Contacts",
    "NSCalendarsUsageDescription": "Calendar",
    "NSBluetoothAlwaysUsageDescription": "Bluetooth",
    "NSFaceIDUsageDescription": "Face ID",
}


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def find_files(directory, filename):
    if not directory.is_dir():
        return []

    return [
        path for path in directory.rglob(filename)
        if path.is_file()
        and not any(part in SKIP_DIRS for part in path.relative_to(directory).parts)
    ]


def parse_plist(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        values = {}

        children = list(root)

        for index in range(0, len(children) - 1, 2):
            key = children[index]
            value = children[index + 1]

            if key.tag == "key":
                values[key.text] = value.text if value.text else value.tag

        return values

    except (OSError, ET.ParseError):
        return {}


def execute(root):
    root = Path(root).resolve()

    findings = []
    details = {
        "ios_project_detected": False,
        "frameworks": [],
        "plist_files": [],
        "bundle_identifiers": [],
        "deployment_targets": [],
        "privacy_permissions": [],
        "build_configuration": {},
    }

    # 1. Detect iOS project directories
    ios_directories = [
        root / "ios",
        root / "web" / "ios",
    ]

    existing_directories = [
        directory for directory in ios_directories
        if directory.is_dir() and any(directory.iterdir())
    ]

    details["ios_project_detected"] = bool(existing_directories)
    details["ios_project_directories"] = [
        str(path.relative_to(root))
        for path in existing_directories
    ]

    # 2. Detect mobile frameworks
    config_files = [
        root / "capacitor.config.ts",
        root / "capacitor.config.js",
        root / "capacitor.config.json",
        root / "web" / "capacitor.config.ts",
        root / "web" / "capacitor.config.js",
        root / "web" / "capacitor.config.json",
        root / "app.json",
        root / "web" / "app.json",
    ]

    package_files = [
        root / "package.json",
        root / "web" / "package.json",
    ]

    for path in package_files:
        if not path.is_file():
            continue

        try:
            package = json.loads(read_text(path))
        except json.JSONDecodeError:
            continue

        dependencies = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }

        if "@capacitor/core" in dependencies:
            if "Capacitor" not in details["frameworks"]:
                details["frameworks"].append("Capacitor")

        if "react-native" in dependencies:
            if "React Native" not in details["frameworks"]:
                details["frameworks"].append("React Native")

    for path in config_files:
        if path.is_file() and "capacitor" in path.name.lower():
            if "Capacitor" not in details["frameworks"]:
                details["frameworks"].append("Capacitor")

    # 3. Find and inspect Info.plist
    plist_paths = []

    for directory in existing_directories:
        plist_paths.extend(find_files(directory, "Info.plist"))

    details["plist_files"] = [
        str(path.relative_to(root))
        for path in plist_paths
    ]

    if details["ios_project_detected"] and not plist_paths:
        findings.append({
            "severity": "HIGH",
            "issue": "No Info.plist file detected in the iOS project.",
        })

    for plist_path in plist_paths:
        values = parse_plist(plist_path)

        if not values:
            findings.append({
                "severity": "HIGH",
                "file": str(plist_path.relative_to(root)),
                "issue": "Info.plist could not be parsed. Verify its XML structure.",
            })
            continue

        bundle_id = values.get("CFBundleIdentifier")

        if bundle_id:
            details["bundle_identifiers"].append(bundle_id)
        else:
            findings.append({
                "severity": "HIGH",
                "file": str(plist_path.relative_to(root)),
                "issue": "CFBundleIdentifier is missing from Info.plist.",
            })

        for key, label in PRIVACY_KEYS.items():
            if key in values:
                details["privacy_permissions"].append({
                    "permission": label,
                    "key": key,
                    "description_present": bool(
                        str(values[key]).strip()
                    ),
                })

                if not str(values[key]).strip():
                    findings.append({
                        "severity": "HIGH",
                        "file": str(plist_path.relative_to(root)),
                        "issue": f"{key} is present but its description is empty.",
                    })

    # 4. Inspect Xcode project build settings
    project_files = []

    for directory in existing_directories:
        project_files.extend(find_files(directory, "project.pbxproj"))

    for project_file in project_files:
        content = read_text(project_file)

        bundle_ids = re.findall(
            r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([^";]+)"?;',
            content,
        )

        targets = re.findall(
            r'IPHONEOS_DEPLOYMENT_TARGET\s*=\s*"?([^";]+)"?;',
            content,
        )

        details["bundle_identifiers"].extend(bundle_ids)
        details["deployment_targets"].extend(targets)

    details["bundle_identifiers"] = sorted(
        set(details["bundle_identifiers"])
    )

    details["deployment_targets"] = sorted(
        set(details["deployment_targets"])
    )

    if details["ios_project_detected"] and not project_files:
        findings.append({
            "severity": "MEDIUM",
            "issue": "No Xcode project.pbxproj file detected.",
        })

    if details["ios_project_detected"] and not details["deployment_targets"]:
        findings.append({
            "severity": "INFO",
            "issue": "iOS deployment target could not be detected.",
        })

    # 5. Check build configuration signals
    details["build_configuration"] = {
        "xcode_project_found": bool(project_files),
        "info_plist_found": bool(plist_paths),
        "deployment_target_found": bool(details["deployment_targets"]),
        "bundle_identifier_found": bool(details["bundle_identifiers"]),
    }

    # 6. Report missing native project
    if not details["ios_project_detected"]:
        findings.append({
            "severity": "INFO",
            "issue": "No populated iOS project directory detected. Native iOS configuration checks were skipped.",
        })

    # 7. Report platform testing limitation
    findings.append({
        "severity": "INFO",
        "issue": "Native iOS builds, signing, simulator tests and device tests require macOS with Xcode. They were not performed by this Ubuntu audit.",
    })

    has_issues = any(
        item["severity"] in {"HIGH", "MEDIUM"}
        for item in findings
    )

    status = "WARN" if has_issues else "PASS"

    return result(
        "iOS Compatibility",
        status,
        "Inspected iOS project structure, Info.plist, bundle identifiers, deployment targets, framework signals and privacy permission descriptions.",
        findings,
        details,
    )
