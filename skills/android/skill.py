
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
    ".gradle",
    ".idea",
}

ANDROID_PERMISSION_PREFIX = (
    "android.permission."
)


def read_text(path):
    try:
        return path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return ""


def find_files(directory, filename):
    if not directory.is_dir():
        return []

    return [
        path for path in directory.rglob(filename)
        if path.is_file()
        and not any(
            part in SKIP_DIRS
            for part in path.relative_to(directory).parts
        )
    ]


def execute(root):
    root = Path(root).resolve()

    findings = []

    details = {
        "android_project_detected": False,
        "project_directories": [],
        "manifest_files": [],
        "application_ids": [],
        "sdk_versions": [],
        "permissions": [],
        "gradle_files": [],
        "frameworks": [],
    }

    # 1. Detect Android project directories
    android_directories = [
        root / "android",
        root / "web" / "android",
    ]

    existing_directories = [
        directory
        for directory in android_directories
        if directory.is_dir() and any(directory.iterdir())
    ]

    details["android_project_detected"] = bool(
        existing_directories
    )

    details["project_directories"] = [
        str(directory.relative_to(root))
        for directory in existing_directories
    ]

    # 2. Detect Capacitor and React Native
    package_files = [
        root / "package.json",
        root / "web" / "package.json",
    ]

    for package_path in package_files:
        if not package_path.is_file():
            continue

        try:
            package = json.loads(read_text(package_path))
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

    # 3. Find Android manifests
    manifest_files = []

    for directory in existing_directories:
        manifest_files.extend(
            find_files(directory, "AndroidManifest.xml")
        )

    details["manifest_files"] = [
        str(path.relative_to(root))
        for path in manifest_files
    ]

    if details["android_project_detected"] and not manifest_files:
        findings.append({
            "severity": "HIGH",
            "issue": "No AndroidManifest.xml found in the Android project.",
        })

    # 4. Inspect manifest configuration
    for manifest_path in manifest_files:
        try:
            tree = ET.parse(manifest_path)
            manifest = tree.getroot()
        except (OSError, ET.ParseError):
            findings.append({
                "severity": "HIGH",
                "file": str(manifest_path.relative_to(root)),
                "issue": "AndroidManifest.xml could not be parsed. Check XML syntax.",
            })
            continue

        package_id = manifest.attrib.get("package")

        if package_id:
            details["application_ids"].append(package_id)

        android_ns = "{http://schemas.android.com/apk/res/android}"

        application = manifest.find("application")

        if application is None:
            findings.append({
                "severity": "HIGH",
                "file": str(manifest_path.relative_to(root)),
                "issue": "Application element is missing from AndroidManifest.xml.",
            })

        for element in manifest.iter():
            if element.tag in {
                "uses-permission",
                "uses-permission-sdk-23",
                "uses-permission-sdk-m",
            }:
                permission = element.attrib.get(
                    android_ns + "name"
                )

                if permission:
                    details["permissions"].append(permission)

    # 5. Inspect Gradle configuration
    gradle_files = []

    for directory in existing_directories:
        for filename in (
            "build.gradle",
            "build.gradle.kts",
        ):
            gradle_files.extend(
                find_files(directory, filename)
            )

    details["gradle_files"] = [
        str(path.relative_to(root))
        for path in gradle_files
    ]

    for gradle_path in gradle_files:
        content = read_text(gradle_path)

        application_ids = re.findall(
            r'applicationId\s*(?:=)?\s*["\']([^"\']+)["\']',
            content,
        )

        namespace_ids = re.findall(
            r'namespace\s*(?:=)?\s*["\']([^"\']+)["\']',
            content,
        )

        details["application_ids"].extend(
            application_ids + namespace_ids
        )

        for key in (
            "minSdk",
            "minSdkVersion",
            "targetSdk",
            "targetSdkVersion",
            "compileSdk",
            "compileSdkVersion",
        ):
            pattern = (
                rf'\b{key}\b\s*(?:=)?\s*'
                rf'(?:\(?\s*)["\']?(\d+)'
            )

            for value in re.findall(pattern, content):
                details["sdk_versions"].append({
                    "setting": key,
                    "version": value,
                    "file": str(gradle_path.relative_to(root)),
                })

    details["application_ids"] = sorted(
        set(details["application_ids"])
    )

    details["permissions"] = sorted(
        set(details["permissions"])
    )

    # 6. Check important configuration
    if details["android_project_detected"]:
        if not gradle_files:
            findings.append({
                "severity": "MEDIUM",
                "issue": "No Gradle build configuration found.",
            })

        if not details["application_ids"]:
            findings.append({
                "severity": "MEDIUM",
                "issue": "Android application ID or namespace could not be detected.",
            })

        if not details["sdk_versions"]:
            findings.append({
                "severity": "INFO",
                "issue": "Android SDK version settings could not be detected.",
            })

    if not details["android_project_detected"]:
        findings.append({
            "severity": "INFO",
            "issue": "No populated Android project directory detected. Native configuration checks were skipped.",
        })

    # 7. Report platform testing limitation
    findings.append({
        "severity": "INFO",
        "issue": "Android emulator, device and native build tests were not performed. They require Android SDK and suitable local tooling.",
    })

    details["summary"] = {
        "manifest_count": len(manifest_files),
        "gradle_file_count": len(gradle_files),
        "application_id_count": len(details["application_ids"]),
        "permission_count": len(details["permissions"]),
        "sdk_setting_count": len(details["sdk_versions"]),
    }

    has_issues = any(
        finding["severity"] in {"HIGH", "MEDIUM"}
        for finding in findings
    )

    status = "WARN" if has_issues else "PASS"

    return result(
        "Android Compatibility",
        status,
        "Inspected Android project structure, manifest, application IDs, SDK settings, permissions and Gradle configuration.",
        findings,
        details,
    )
