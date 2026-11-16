
import json
import time
from pathlib import Path

from ...core.utils import result


SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "coverage",
    "playwright-report",
    "test-results",
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"
}

SOURCE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx"
}

MAX_BUNDLE_SIZE = 500 * 1024
MAX_IMAGE_SIZE = 500 * 1024


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def source_files(root):
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in SKIP_DIRS for part in path.parts):
            continue

        if path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path


def execute(root):
    root = Path(root).resolve()
    start = time.perf_counter()

    findings = []
    details = {
        "checks": {},
    }

    # 1. Inspect build configuration without running a build
    package_candidates = [
        root / "package.json",
        root / "web" / "package.json",
    ]

    build_script_found = False

    for package_file in package_candidates:
        if not package_file.is_file():
            continue

        data = read_json(package_file)

        if data.get("scripts", {}).get("build"):
            build_script_found = True
            details["checks"]["package"] = str(
                package_file.relative_to(root)
            )
            break

    details["build"] = {
        "build_script_found": build_script_found,
        "build_executed": False,
        "note": "Build execution is handled separately by the audit engine."
    }

    if not build_script_found:
        findings.append({
            "severity": "INFO",
            "issue": "No root or web package.json build script was found."
        })

    # 2. Inspect existing production JavaScript and CSS bundles
    bundle_directories = [
        root / "dist",
        root / "build",
        root / "web" / "dist",
        root / "web" / "build",
    ]

    bundles = []
    total_bundle_size = 0

    for directory in bundle_directories:
        if not directory.is_dir():
            continue

        for path in directory.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in {".js", ".css"}
                and not any(part in SKIP_DIRS for part in path.parts)
            ):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue

                total_bundle_size += size

                bundles.append({
                    "file": str(path.relative_to(root)),
                    "size_kb": round(size / 1024, 2),
                })

                if size > MAX_BUNDLE_SIZE:
                    findings.append({
                        "severity": "MEDIUM",
                        "file": str(path.relative_to(root)),
                        "issue": "Large JavaScript or CSS bundle exceeds 500 KB."
                    })

    details["bundle_analysis"] = {
        "bundle_count": len(bundles),
        "total_size_kb": round(total_bundle_size / 1024, 2),
        "bundles": bundles[:50],
    }

    if not bundles:
        findings.append({
            "severity": "INFO",
            "issue": "No existing production bundles found. Build was not executed by this skill."
        })

    # 3. Detect large frontend images
    large_images = []

    image_directories = [
        root / "web" / "public",
        root / "public",
        root / "web" / "src",
        root / "src",
    ]

    for directory in image_directories:
        if not directory.is_dir():
            continue

        for path in directory.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in IMAGE_EXTENSIONS
                and not any(part in SKIP_DIRS for part in path.parts)
            ):
                try:
                    size = path.stat().st_size
                except OSError:
                    continue

                if size > MAX_IMAGE_SIZE:
                    large_images.append({
                        "file": str(path.relative_to(root)),
                        "size_kb": round(size / 1024, 2),
                    })

                    findings.append({
                        "severity": "MEDIUM",
                        "file": str(path.relative_to(root)),
                        "issue": "Large image exceeds 500 KB. Review compression and WebP/AVIF conversion."
                    })

    details["large_images"] = large_images[:50]

    # 4. Check frontend code-splitting signals
    lazy_loading_signals = 0
    source_count = 0

    for path in source_files(root):
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            continue

        source_count += 1

        if (
            "React.lazy" in content
            or "lazy(" in content
            or "import(" in content
        ):
            lazy_loading_signals += 1

    details["code_splitting"] = {
        "source_files_scanned": source_count,
        "files_with_lazy_loading_signals": lazy_loading_signals,
    }

    if source_count and lazy_loading_signals == 0:
        findings.append({
            "severity": "INFO",
            "issue": "No lazy-loading or dynamic import signals detected. Review frontend code splitting."
        })

    # 5. Check Vite performance configuration
    vite_configs = [
        root / "vite.config.js",
        root / "vite.config.ts",
        root / "web" / "vite.config.js",
        root / "web" / "vite.config.ts",
    ]

    vite_config_found = False
    chunk_budget_configured = False

    for config in vite_configs:
        if config.exists():
            vite_config_found = True

            try:
                content = config.read_text(encoding="utf-8")
                if "chunkSizeWarningLimit" in content:
                    chunk_budget_configured = True
            except OSError:
                pass

    details["vite_configuration"] = {
        "found": vite_config_found,
        "chunk_size_warning_limit_configured": chunk_budget_configured,
    }

    if vite_config_found and not chunk_budget_configured:
        findings.append({
            "severity": "INFO",
            "issue": "Vite chunkSizeWarningLimit is not explicitly configured. Consider setting a bundle-size budget."
        })

    # 6. Final assessment
    elapsed = round(time.perf_counter() - start, 2)
    details["assessment_seconds"] = elapsed

    findings.append({
        "severity": "INFO",
        "issue": "Static performance checks do not measure real user loading speed, API latency, Core Web Vitals or concurrent-user capacity."
    })

    has_issues = any(
        finding["severity"] in {"HIGH", "MEDIUM"}
        for finding in findings
    )

    return result(
        "Performance Testing",
        "WARN" if has_issues else "PASS",
        "Inspected existing production bundles, large images, code-splitting signals and Vite configuration. Build execution is handled separately by the audit engine.",
        findings,
        details,
    )
