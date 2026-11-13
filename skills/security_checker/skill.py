
import re

from ...core.utils import run, result, text_files


def execute(root):
    findings = []

    for p, t in text_files(root):
        rel = str(p.relative_to(root))

        if '.env' in p.name and p.name not in {'.env.example', '.env.sample'}:
            findings.append({
                'severity': 'HIGH',
                'file': rel,
                'issue': 'Environment file exists; verify it is excluded from version control.'
            })

        if '-----BEGIN PRIVATE KEY-----' in t:
            findings.append({
                'severity': 'CRITICAL',
                'file': rel,
                'issue': 'Possible hard-coded private key.'
            })

        if re.search(r'\bAKIA[0-9A-Z]{16}\b', t):
            findings.append({
                'severity': 'CRITICAL',
                'file': rel,
                'issue': 'Possible hard-coded AWS access key.'
            })

    details = {}

    if (root / 'package-lock.json').exists() or (root / 'package.json').exists():
        details['npm_audit'] = run(
            ['npm', 'audit', '--json'],
            root,
            timeout=300
        )

        if details['npm_audit']['returncode'] not in (0, 1):
            findings.append({
                'severity': 'INFO',
                'issue': 'npm audit could not complete; inspect tool output.'
            })

    status = 'WARN' if findings or details.get('npm_audit', {}).get('returncode', 0) == 1 else 'PASS'

    return result(
        'Security Checker',
        status,
        'Checked repository hygiene and ran npm dependency audit when available.',
        findings,
        details
    )
