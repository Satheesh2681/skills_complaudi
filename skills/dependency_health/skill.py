
import json
import os
from pathlib import Path

from ...core.utils import run, result


SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
}


def find_package_files(root):
    """Find package.json files without scanning generated or duplicate trees."""
    package_files = []

    duplicate_root = root / root.name
    skip_duplicate = (
        (root / "package.json").exists()
        and (duplicate_root / "package.json").exists()
    )

    for current, directories, filenames in os.walk(root):
        current_path = Path(current)
        relative = current_path.relative_to(root)

        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
            and not (
                skip_duplicate
                and relative == Path(".")
                and directory == root.name
            )
        ]

        if "package.json" in filenames:
            package_files.append(current_path / "package.json")

    return sorted(package_files)


def load_package_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def collect_dependencies(package_data):
    dependencies = {}

    for section in (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
    ):
        packages = package_data.get(section, {})

        if isinstance(packages, dict):
            dependencies.update(packages)

    return dependencies


def find_installed_package(package_name, package_dir, root):
    """Find a dependency in local or parent node_modules directories."""
    current = package_dir

    while True:
        candidate = (
            current / "node_modules" / package_name / "package.json"
        )

        if candidate.exists():
            return candidate

        if current == root:
            break

        current = current.parent

    return None


def extract_json(output):
    """Extract JSON even if npm prints extra text around it."""
    if not output:
        return None

    start = output.find("{")
    end = output.rfind("}")

    if start == -1 or end == -1 or end < start:
        return None

    try:
        return json.loads(output[start:end + 1])
    except json.JSONDecodeError:
        return None


def check_outdated(root, package_files):
    """Report only outdated packages with a confirmed current version."""
    outdated = []
    skipped = []
    errors = []

    for package_file in package_files:
        package_dir = package_file.parent
        lock_file = package_dir / "package-lock.json"

        if not lock_file.exists():
            skipped.append(str(package_dir.relative_to(root)))
            continue

        # Check node_modules in this project or its parent directories.
        has_node_modules = False
        current = package_dir

        while True:
            if (current / "node_modules").is_dir():
                has_node_modules = True
                break

            if current == root:
                break

            current = current.parent

        if not has_node_modules:
            skipped.append(str(package_dir.relative_to(root)))
            continue

        command_result = run(
            ["npm", "outdated", "--json"],
            cwd=package_dir,
            timeout=120,
        )

        data = extract_json(command_result["output"])

        if not isinstance(data, dict):
            if command_result["returncode"] not in (0, 1):
                errors.append({
                    "directory": str(package_dir.relative_to(root)),
                    "message": "npm outdated could not complete successfully.",
                })
            continue

        for name, details in data.items():
            if not isinstance(details, dict):
                continue

            current_version = details.get("current")

            # Do not count packages without a confirmed installed version.
            if current_version is None:
                continue

            outdated.append({
                "package": name,
                "current": current_version,
                "wanted": details.get("wanted"),
                "latest": details.get("latest"),
                "directory": str(package_dir.relative_to(root)),
            })

    return {
        "packages": outdated,
        "skipped_directories": skipped,
        "errors": errors,
    }


def check_licenses(root, package_files):
    """Inspect installed dependency license metadata."""
    licenses = {}
    missing = []

    for package_file in package_files:
        package_data = load_package_json(package_file)

        if package_data is None:
            continue

        package_dir = package_file.parent
        dependencies = collect_dependencies(package_data)

        for name in dependencies:
            installed_package = find_installed_package(
                name,
                package_dir,
                root,
            )

            if installed_package is None:
                continue

            data = load_package_json(installed_package)

            if data is None:
                continue

            license_value = data.get("license")

            if not license_value:
                missing.append({
                    "package": name,
                    "directory": str(package_dir.relative_to(root)),
                })
                continue

            licenses.setdefault(name, set()).add(str(license_value))

    return {
        "licenses_found": {
            name: sorted(values)
            for name, values in licenses.items()
        },
        "missing_license": missing,
    }


def package_name_from_lock_key(key):
    """Extract a package name from an npm lockfile package path."""
    if "node_modules/" not in key:
        return None

    name = key.rsplit("node_modules/", 1)[-1]

    if name.startswith("@"):
        parts = name.split("/")
        if len(parts) < 2:
            return None
        return "/".join(parts[:2])

    return name.split("/")[0]


def check_duplicates(root, package_files):
    """Find multiple installed versions using package-lock.json."""
    duplicates = []

    for package_file in package_files:
        package_dir = package_file.parent
        lock_file = package_dir / "package-lock.json"

        if not lock_file.exists():
            continue

        lock_data = load_package_json(lock_file)

        if not isinstance(lock_data, dict):
            continue

        versions = {}

        # npm lockfile v2/v3 format.
        packages = lock_data.get("packages", {})

        if isinstance(packages, dict):
            for key, details in packages.items():
                if not isinstance(details, dict):
                    continue

                name = package_name_from_lock_key(key)
                version = details.get("version")

                if name and version:
                    versions.setdefault(name, set()).add(str(version))

        # npm lockfile v1 compatibility.
        def scan_dependencies(dependencies):
            if not isinstance(dependencies, dict):
                return

            for name, details in dependencies.items():
                if not isinstance(details, dict):
                    continue

                version = details.get("version")

                if version:
                    versions.setdefault(name, set()).add(str(version))

                scan_dependencies(details.get("dependencies", {}))

        scan_dependencies(lock_data.get("dependencies", {}))

        for name, package_versions in versions.items():
            if len(package_versions) > 1:
                duplicates.append({
                    "package": name,
                    "versions": sorted(package_versions),
                    "directory": str(package_dir.relative_to(root)),
                })

    return duplicates


def execute(root):
    root = Path(root).resolve()

    package_files = find_package_files(root)

    if not package_files:
        return result(
            "Dependency Health",
            "WARN",
            "No package.json files found.",
            [{
                "severity": "WARN",
                "issue": "Cannot inspect npm dependencies without package.json.",
            }],
            {},
        )

    total_dependencies = 0
    package_details = []

    for package_file in package_files:
        package_data = load_package_json(package_file)

        if package_data is None:
            continue

        dependencies = collect_dependencies(package_data)
        total_dependencies += len(dependencies)

        package_details.append({
            "directory": str(package_file.parent.relative_to(root)),
            "package_name": package_data.get("name", "Unknown"),
            "dependency_count": len(dependencies),
        })

    outdated_results = check_outdated(root, package_files)
    outdated = outdated_results["packages"]

    license_results = check_licenses(root, package_files)
    duplicates = check_duplicates(root, package_files)

    findings = []

    if outdated:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"Found {len(outdated)} confirmed outdated packages.",
        })

    if license_results["missing_license"]:
        findings.append({
            "severity": "MEDIUM",
            "issue": (
                f"Found {len(license_results['missing_license'])} "
                "installed packages without declared license information."
            ),
        })

    if duplicates:
        findings.append({
            "severity": "LOW",
            "issue": (
                f"Found {len(duplicates)} packages with multiple "
                "versions in their lockfiles."
            ),
        })

    if outdated_results["errors"]:
        findings.append({
            "severity": "LOW",
            "issue": "Some npm outdated checks could not be completed.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Inspected {len(package_files)} package.json files. "
        f"Found {total_dependencies} declared dependency entries, "
        f"{len(outdated)} confirmed outdated packages and "
        f"{len(duplicates)} packages with multiple locked versions."
    )

    return result(
        "Dependency Health",
        status,
        summary,
        findings,
        {
            "package_files_scanned": len(package_files),
            "total_declared_dependency_entries": total_dependencies,
            "package_details": package_details,
            "outdated_packages": outdated,
            "outdated_check_skipped_directories": (
                outdated_results["skipped_directories"]
            ),
            "outdated_check_errors": outdated_results["errors"],
            "duplicate_packages": duplicates,
            "license_results": license_results,
            "note": (
                "Outdated checks require npm and registry access. "
                "Packages without a confirmed installed version are "
                "not counted as outdated. Duplicate checks use "
                "package-lock.json and license checks inspect locally "
                "installed package metadata."
            ),
        },
    )
