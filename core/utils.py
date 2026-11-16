
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
SETTINGS_PATH = BASE / "config" / "settings.json"

DEFAULT_SKIP = {
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
    ".pytest_cache",
    "htmlcov",
}

TEXT_EXT = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".html", ".css", ".scss", ".json",
    ".yml", ".yaml", ".md", ".xml", ".toml", ".sh",
}


def load_settings():
    """Load engine settings safely."""
    try:
        if SETTINGS_PATH.is_file():
            with SETTINGS_PATH.open(encoding="utf-8") as file:
                settings = json.load(file)

            if isinstance(settings, dict):
                return settings

    except (OSError, ValueError):
        pass

    return {}


def get_skip_directories():
    """Load excluded directories with safe defaults."""
    skip = set(DEFAULT_SKIP)
    configured = load_settings().get("skip_directories", [])

    if isinstance(configured, list):
        skip.update(
            item.strip()
            for item in configured
            if isinstance(item, str) and item.strip()
        )

    return skip


def get_max_file_size_bytes():
    """Read maximum text-file size from settings."""
    value = load_settings().get("max_file_size_mb", 10)

    try:
        size_mb = float(value)
        if not (0 < size_mb <= 1024):
            raise ValueError
    except (TypeError, ValueError):
        size_mb = 10

    return int(size_mb * 1024 * 1024)


def run(cmd, cwd, timeout=300):
    """Execute a command and return structured output."""
    start = time.time()

    try:
        process = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

        return {
            "command": cmd,
            "returncode": process.returncode,
            "output": process.stdout[-12000:],
            "duration_seconds": round(time.time() - start, 2),
            "timed_out": False,
        }

    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""

        if isinstance(output, bytes):
            output = output.decode(errors="replace")

        return {
            "command": cmd,
            "returncode": 124,
            "output": str(output)[-12000:] + "\nTimed out",
            "duration_seconds": round(time.time() - start, 2),
            "timed_out": True,
        }

    except FileNotFoundError:
        return {
            "command": cmd,
            "returncode": 127,
            "output": f"Executable not found: {cmd[0]}",
            "duration_seconds": round(time.time() - start, 2),
            "timed_out": False,
        }

    except OSError as error:
        return {
            "command": cmd,
            "returncode": 1,
            "output": f"Command execution error: {error}",
            "duration_seconds": round(time.time() - start, 2),
            "timed_out": False,
        }


def files(root):
    """Yield project files without entering excluded directories."""
    root = Path(root)

    if not root.is_dir():
        return

    skip = get_skip_directories()

    for current, directories, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        directories[:] = [
            directory
            for directory in directories
            if directory not in skip
        ]

        for filename in filenames:
            path = Path(current) / filename

            if path.is_file():
                yield path


def text_files(root):
    """Yield readable text files within configured size limit."""
    max_size = get_max_file_size_bytes()

    for path in files(root):
        if path.suffix.lower() not in TEXT_EXT:
            continue

        try:
            if path.stat().st_size <= max_size:
                yield (
                    path,
                    path.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    ),
                )

        except OSError:
            continue


def result(name, status, summary, findings=None, details=None):
    """Create a consistent skill result."""
    return {
        "skill": name,
        "status": status,
        "summary": summary,
        "findings": findings or [],
        "details": details or {},
    }


def redact(value):
    """Redact common secret assignments from text."""
    value = re.sub(
        r'(?i)(password|secret|token|api[_-]?key)'
        r'(\s*[=:]\s*)["\']?[^\s"\']+',
        r'\1\2[REDACTED]',
        value,
    )

    return value
