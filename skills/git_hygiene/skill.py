
import re
from pathlib import Path

from ...core.utils import result, run


def execute(root):
    findings = []
    git_dir = root / ".git"

    if not git_dir.exists():
        return result(
            "Git Hygiene",
            "WARN",
            "Git repository metadata not found.",
            [{
                "severity": "HIGH",
                "message": "Project is not detected as a Git repository.",
                "recommendation": "Initialize or locate the project's Git repository.",
            }],
            {"git_repository": False},
        )

    tracked = run(["git", "ls-files", "-z"], root)
    if tracked["returncode"] != 0:
        return result(
            "Git Hygiene",
            "WARN",
            "Unable to list tracked Git files.",
            [{"severity": "MEDIUM", "message": tracked["output"]}],
            {"git_repository": True},
        )

    tracked_files = [
        item for item in tracked["output"].split("\0") if item
    ]

    large_files = []
    for name in tracked_files:
        path = root / name
        try:
            if path.is_file() and path.stat().st_size > 5 * 1024 * 1024:
                large_files.append({
                    "file": name,
                    "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                })
        except OSError:
            pass

    conflict_files = []
    marker_pattern = re.compile(
        r"^(<<<<<<< |=======\s*$|>>>>>>> )",
        re.MULTILINE,
    )

    for name in tracked_files:
        path = root / name
        if path.suffix.lower() not in {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".json",
            ".md", ".yml", ".yaml", ".css", ".html",
        }:
            continue

        try:
            if path.is_file() and path.stat().st_size <= 2_000_000:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if marker_pattern.search(content):
                    conflict_files.append(name)
        except OSError:
            pass

    gitignore = root / ".gitignore"
    ignore_content = (
        gitignore.read_text(encoding="utf-8", errors="ignore")
        if gitignore.exists() else ""
    )

    recommended_patterns = [
        "node_modules",
        ".env",
        "__pycache__",
        ".venv",
    ]
    missing_patterns = [
        pattern for pattern in recommended_patterns
        if pattern not in ignore_content
    ]

    commits = run(
        ["git", "log", "-5", "--pretty=%s"],
        root,
    )
    commit_messages = [
        line.strip()
        for line in commits["output"].splitlines()
        if line.strip()
    ] if commits["returncode"] == 0 else []

    conventional_pattern = re.compile(
        r"^(feat|fix|docs|style|refactor|test|chore|perf|ci|build)(\([^)]+\))?: .+"
    )
    nonstandard_commits = [
        message for message in commit_messages
        if not conventional_pattern.match(message)
    ]

    if large_files:
        findings.append({
            "severity": "MEDIUM",
            "message": f"Found {len(large_files)} tracked files larger than 5 MB.",
            "recommendation": "Review whether large files should use Git LFS or be excluded.",
        })

    if conflict_files:
        findings.append({
            "severity": "HIGH",
            "message": f"Possible merge conflict markers found in {len(conflict_files)} tracked files.",
            "recommendation": "Review and resolve conflict markers before merging.",
        })

    if missing_patterns:
        findings.append({
            "severity": "LOW",
            "message": f".gitignore may be missing common patterns: {', '.join(missing_patterns)}.",
            "recommendation": "Review .gitignore for generated files and sensitive environment files.",
        })

    if nonstandard_commits:
        findings.append({
            "severity": "LOW",
            "message": f"{len(nonstandard_commits)} of the latest {len(commit_messages)} commit messages do not follow Conventional Commits.",
            "recommendation": "Consider using formats such as feat:, fix:, docs:, and chore:.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Checked {len(tracked_files)} tracked files. "
        f"Large files: {len(large_files)}; "
        f"possible conflict files: {len(conflict_files)}; "
        f"missing .gitignore patterns: {len(missing_patterns)}; "
        f"nonstandard recent commits: {len(nonstandard_commits)}."
    )

    return result(
        "Git Hygiene",
        status,
        summary,
        findings,
        {
            "tracked_files": len(tracked_files),
            "large_files": large_files,
            "conflict_files": conflict_files,
            "gitignore_exists": gitignore.exists(),
            "missing_gitignore_patterns": missing_patterns,
            "recent_commit_messages": commit_messages,
            "nonstandard_commit_messages": nonstandard_commits,
            "analysis_type": "Git metadata and static analysis",
        },
    )
