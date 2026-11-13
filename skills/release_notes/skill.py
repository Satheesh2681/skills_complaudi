
from pathlib import Path

from ...core.utils import result, run


def execute(root):
    r = run(
        ['git', 'log', '-10', '--pretty=format:%h %ad %s', '--date=short'],
        root,
        timeout=30
    )

    if r['returncode'] == 0 and r['output'].strip():
        notes = '\n'.join(
            '- ' + line for line in r['output'].splitlines()
        )

        # Locate the COMPLAUDI Skills repository reports directory
        reports_dir = Path(__file__).resolve().parents[2] / 'reports'

        # Create reports directory if it does not exist
        reports_dir.mkdir(parents=True, exist_ok=True)

        output_file = reports_dir / 'release-notes.md'

        output_file.write_text(
            '# Recent Release Notes\n\n' + notes + '\n',
            encoding='utf-8'
        )

        return result(
            'Release Notes',
            'PASS',
            'Generated release notes from the latest 10 Git commits.',
            details={
                'git_log': r,
                'output': str(output_file)
            }
        )

    return result(
        'Release Notes',
        'WARN',
        'No Git commit history available; release notes were not generated.',
        details=r
    )
