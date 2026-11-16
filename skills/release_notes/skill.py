
from pathlib import Path

from ...core.utils import result, run


def execute(root):
    root = Path(root).resolve()

    # Read the latest 10 Git commits from the audited project
    r = run(
        [
            "git",
            "log",
            "-10",
            "--pretty=format:%h %ad %s",
            "--date=short",
        ],
        root,
        timeout=30,
    )

    if r["returncode"] != 0 or not r["output"].strip():
        return result(
            "Release Notes",
            "WARN",
            "No Git commit history available; release notes were not generated.",
            details={
                "message": r.get("output", "Git log unavailable.")
            },
        )

    # Format commit history
    notes = "\n".join(
        "- " + line
        for line in r["output"].splitlines()
        if line.strip()
    )

    # Save reports inside the audited project
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_file = reports_dir / "release-notes.md"

    output_file.write_text(
        "# Recent Release Notes\n\n"
        "Automatically generated from the latest 10 Git commits.\n\n"
        + notes
        + "\n",
        encoding="utf-8",
    )

    return result(
        "Release Notes",
        "PASS",
        "Generated release notes from the latest 10 Git commits.",
        details={
            "commit_count": len(r["output"].splitlines()),
            "output": str(output_file),
        },
    )
