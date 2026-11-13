from ...core.utils import result, run

def execute(root):
    details={}; findings=[]
    probe=root/'tests'/'security'/'probe.mjs'
    if probe.exists():
        details['security_probe']=run(['node',str(probe)],root,timeout=300)
        status='PASS' if details['security_probe']['returncode']==0 else 'WARN'
    else:
        status='WARN'; findings.append({'severity':'INFO','issue':'No tests/security/probe.mjs found; active security probes were not run.'})
    return result('Security Testing',status,'Executed the repository security probe when present. Only run active tests against systems you own or are authorized to test.',findings,details)
