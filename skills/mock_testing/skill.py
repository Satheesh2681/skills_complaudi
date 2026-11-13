from ...core.utils import result, run

def execute(root):
    if (root/'package.json').exists(): r=run(['npm','test','--','--run'],root,timeout=600)
    else: r=run(['python','-m','unittest','discover','-v'],root,timeout=600)
    status='PASS' if r['returncode']==0 else 'WARN'
    return result('Mock Testing',status,'Ran the project test suite as a mock/unit-test validation step; no external services were modified.',details=r)
