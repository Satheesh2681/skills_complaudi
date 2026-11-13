from ...core.utils import result, run

def execute(root):
    p=root/'tests'/'mobile'/'audit.mjs'
    if p.exists():
        r=run(['node',str(p)],root,timeout=300); status='PASS' if r['returncode']==0 else 'WARN'
        return result('Mobile Compatibility',status,'Executed existing mobile audit script.',details=r)
    return result('Mobile Compatibility','WARN','No existing mobile audit script found; responsive browser checks were not run.',[{'severity':'INFO','issue':'Add browser/device test cases to enable automated responsive checks.'}])
