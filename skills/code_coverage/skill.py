from ...core.utils import run, result

def execute(root):
    pkg=root/'package.json'
    if pkg.exists():
        r=run(['npm','test','--','--coverage'],root,timeout=600)
        status='PASS' if r['returncode']==0 else ('WARN' if r['returncode']==127 else 'FAIL')
        return result('Code Coverage / Unit Testing',status,'Executed configured npm test command with coverage flag.',details=r)
    r=run(['python','-m','pytest','--cov'],root,timeout=600)
    status='PASS' if r['returncode']==0 else 'WARN'
    return result('Code Coverage / Unit Testing',status,'Attempted pytest coverage; install pytest-cov to enable coverage metrics.',details=r)
