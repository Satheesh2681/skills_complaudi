
import re

from ...core.utils import run, result


def parse_coverage(output):
    # Jest / Istanbul coverage summary
    match = re.search(
        r'(?im)^\s*All files\s*\|\s*([\d.]+)\s*\|',
        output
    )

    if match:
        return float(match.group(1))

    # Pytest-cov coverage summary
    match = re.search(
        r'(?im)^\s*TOTAL\s+.*?(\d+(?:\.\d+)?)%\s*$',
        output
    )

    if match:
        return float(match.group(1))

    return None


def execute(root):
    pkg = root / 'package.json'

    if pkg.exists():
        r = run(
            ['npm', 'test', '--', '--coverage'],
            root,
            timeout=600
        )
    else:
        r = run(
            ['python', '-m', 'pytest', '--cov'],
            root,
            timeout=600
        )

    details = dict(r)
    output = r.get('output', '')

    coverage_pct = parse_coverage(output)
    details['coverage_percentage'] = coverage_pct
    details['coverage_threshold'] = 60

    findings = []

    if coverage_pct is None:
        findings.append({
            'severity': 'MEDIUM',
            'issue': 'Coverage percentage could not be extracted from test output.'
        })

    elif coverage_pct < 60:
        findings.append({
            'severity': 'HIGH',
            'issue': f'Code coverage is {coverage_pct}% (below 60% threshold).'
        })

    if r['returncode'] == 127:
        status = 'WARN'
    elif r['returncode'] != 0:
        status = 'FAIL'
    elif coverage_pct is None:
        status = 'WARN'
    elif coverage_pct < 60:
        status = 'WARN'
    else:
        status = 'PASS'

    message = (
        f'Executed tests. Coverage: {coverage_pct}%'
        if coverage_pct is not None
        else 'Executed tests, but coverage percentage could not be determined.'
    )

    return result(
        'Code Coverage / Unit Testing',
        status,
        message,
        findings,
        details
    )
