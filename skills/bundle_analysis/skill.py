
import json
import os
import re
from pathlib import Path

from ...core.utils import result


SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "coverage",
    "playwright-report",
    "test-results",
}

BUILD_DIRECTORIES = {
    "dist",
    "build",
    ".next",
    "out",
}

LARGE_FILE_LIMIT = 1 * 1024 * 1024  # 1 MB


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def find_project_directories(root):
    """Find package directories without scanning a nested duplicate project."""
    projects = []

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
            projects.append(current_path)

    return sorted(projects)


def find_build_directories(root):
    """Find existing build output directories."""
    build_dirs = []

    duplicate_root = root / root.name
    skip_duplicate = (
        (root / "package.json").exists()
        and (duplicate_root / "package.json").exists()
    )

    for current, directories, filenames in os.walk(root):
        current_path = Path(current)
        relative = current_path.relative_to(root)

        if current_path.name in BUILD_DIRECTORIES:
            build_dirs.append(current_path)
            directories[:] = []
            continue

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

    return sorted(build_dirs)


def analyze_build_directory(build_dir, root):
    """Collect build size, largest files, JavaScript files and source maps."""
    total_size = 0
    file_count = 0
    javascript_files = []
    source_maps = []
    large_files = []

    for current, directories, filenames in os.walk(build_dir):
        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
        ]

        for filename in filenames:
            path = Path(current) / filename

            try:
                size = path.stat().st_size
            except OSError:
                continue

            relative_path = str(path.relative_to(root))

            total_size += size
            file_count += 1

            file_info = {
                "file": relative_path,
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 3),
            }

            if path.suffix.lower() in {".js", ".mjs", ".cjs"}:
                javascript_files.append(file_info)

            if path.suffix.lower() == ".map":
                source_maps.append(relative_path)

            if size > LARGE_FILE_LIMIT:
                large_files.append(file_info)

    largest_files = sorted(
        [
            {
                "file": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "size_mb": round(
                    path.stat().st_size / (1024 * 1024), 3
                ),
            }
            for path in build_dir.rglob("*")
            if path.is_file()
            and not any(
                part in SKIP_DIRECTORIES
                for part in path.relative_to(build_dir).parts
            )
        ],
        key=lambda item: item["size_bytes"],
        reverse=True,
    )[:10]

    return {
        "directory": str(build_dir.relative_to(root)),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 3),
        "file_count": file_count,
        "javascript_file_count": len(javascript_files),
        "javascript_files": javascript_files,
        "source_map_count": len(source_maps),
        "source_maps": source_maps,
        "large_file_count": len(large_files),
        "large_files": sorted(
            large_files,
            key=lambda item: item["size_bytes"],
            reverse=True,
        ),
        "largest_files": largest_files,
    }


def inspect_build_configuration(project_dirs):
    """Inspect package scripts and bundler configuration for optimization signals."""
    configurations = []
    tree_shaking_signals = []
    code_splitting_signals = []

    config_names = {
        "vite.config.js",
        "vite.config.ts",
        "vite.config.mjs",
        "webpack.config.js",
        "webpack.config.ts",
        "rollup.config.js",
        "rollup.config.ts",
        "next.config.js",
        "next.config.ts",
        "next.config.mjs",
    }

    for project_dir in project_dirs:
        package_file = project_dir / "package.json"
        package_data = load_json(package_file)

        if package_data is None:
            continue

        scripts = package_data.get("scripts", {})
        build_script = (
            scripts.get("build", "")
            if isinstance(scripts, dict)
            else ""
        )

        side_effects = package_data.get("sideEffects")

        if side_effects is not None:
            tree_shaking_signals.append({
                "directory": str(project_dir),
                "signal": "sideEffects field found in package.json",
                "value": side_effects,
            })

        if isinstance(build_script, str):
            if any(
                name in build_script.lower()
                for name in ("vite build", "webpack", "rollup")
            ):
                tree_shaking_signals.append({
                    "directory": str(project_dir),
                    "signal": "Production bundler build script found",
                    "value": build_script,
                })

        configurations.append({
            "directory": str(project_dir),
            "build_script": build_script,
            "side_effects": side_effects,
        })

        for config_name in config_names:
            config_file = project_dir / config_name

            if not config_file.exists():
                continue

            try:
                content = config_file.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            except OSError:
                continue

            if re.search(r"treeshake|treeShaking|usedExports", content, re.I):
                tree_shaking_signals.append({
                    "directory": str(project_dir),
                    "signal": f"Tree-shaking configuration found in {config_name}",
                })

            if re.search(
                r"splitChunks|manualChunks|code.?splitting|dynamic\s+import",
                content,
                re.I,
            ):
                code_splitting_signals.append({
                    "directory": str(project_dir),
                    "signal": f"Code-splitting configuration found in {config_name}",
                })

    return {
        "configurations": configurations,
        "tree_shaking_signals": tree_shaking_signals,
        "code_splitting_signals": code_splitting_signals,
    }


def execute(root):
    root = Path(root).resolve()

    project_dirs = find_project_directories(root)
    build_dirs = find_build_directories(root)

    if not build_dirs:
        return result(
            "Bundle Analysis",
            "WARN",
            "No build output directories found. Run the project build first.",
            [{
                "severity": "MEDIUM",
                "issue": "No dist, build, .next, or out directory was found.",
            }],
            {
                "project_directories_scanned": len(project_dirs),
                "build_directories_found": 0,
                "note": (
                    "This skill analyzes existing build output. "
                    "It does not run the build command automatically."
                ),
            },
        )

    build_results = [
        analyze_build_directory(directory, root)
        for directory in build_dirs
    ]

    total_size = sum(
        item["total_size_bytes"]
        for item in build_results
    )

    total_js_files = sum(
        item["javascript_file_count"]
        for item in build_results
    )

    total_source_maps = sum(
        item["source_map_count"]
        for item in build_results
    )

    all_large_files = [
        file_info
        for item in build_results
        for file_info in item["large_files"]
    ]

    configuration_results = inspect_build_configuration(project_dirs)

    findings = []

    if total_source_maps:
        findings.append({
            "severity": "LOW",
            "issue": (
                f"Found {total_source_maps} source map files. "
                "Review whether they should be publicly deployed."
            ),
        })

    if all_large_files:
        findings.append({
            "severity": "MEDIUM",
            "issue": (
                f"Found {len(all_large_files)} build files larger than 1 MB."
            ),
        })

    if total_js_files > 1:
        code_splitting_status = "Possible"
    else:
        code_splitting_status = "Not detected"

    if not configuration_results["tree_shaking_signals"]:
        tree_shaking_status = "No configuration evidence found"
    else:
        tree_shaking_status = "Configuration evidence found"

    status = "WARN" if findings else "PASS"

    summary = (
        f"Analyzed {len(build_dirs)} build directories. "
        f"Total build size: {round(total_size / (1024 * 1024), 3)} MB. "
        f"Found {total_js_files} JavaScript files and "
        f"{total_source_maps} source maps."
    )

    return result(
        "Bundle Analysis",
        status,
        summary,
        findings,
        {
            "project_directories_scanned": len(project_dirs),
            "build_directories_scanned": len(build_dirs),
            "build_results": build_results,
            "total_build_size_bytes": total_size,
            "total_build_size_mb": round(
                total_size / (1024 * 1024), 3
            ),
            "total_javascript_files": total_js_files,
            "total_source_maps": total_source_maps,
            "large_files_over_1mb": all_large_files,
            "code_splitting": {
                "status": code_splitting_status,
                "javascript_file_count": total_js_files,
                "configuration_signals": (
                    configuration_results["code_splitting_signals"]
                ),
            },
            "tree_shaking": {
                "status": tree_shaking_status,
                "configuration_signals": (
                    configuration_results["tree_shaking_signals"]
                ),
            },
            "build_configurations": (
                configuration_results["configurations"]
            ),
            "note": (
                "Multiple JavaScript files suggest possible code splitting "
                "but do not prove it. Tree-shaking configuration signals "
                "do not prove unused code was removed. Actual verification "
                "requires bundler statistics or build analysis tools."
            ),
        },
    )
