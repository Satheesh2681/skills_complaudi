from ...core.utils import result, run

def execute(root):
    details={}; findings=[]
    if (root/'package.json').exists():
        details['e2e_tests']=run(['npx','playwright','test','--list'],root,timeout=180)
        if details['e2e_tests']['returncode']!=0: findings.append({'severity':'INFO','issue':'Playwright test listing unavailable; no browser UAT suite was executed.'})
    else: findings.append({'severity':'INFO','issue':'No supported UAT test runner detected.'})
    return result('UAT Testing', 'WARN' if findings else 'PASS','Checked availability of end-to-end UAT tests. Listing tests does not execute user workflows.',findings,details)
