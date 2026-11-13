from ...core.utils import result, run

def execute(root):
    r=run(['git','log','-10','--pretty=format:%h %ad %s','--date=short'],root,timeout=30)
    if r['returncode']==0 and r['output'].strip():
        notes='\n'.join('- '+line for line in r['output'].splitlines())
        (root/'complaudi_skills'/'reports'/'release-notes.md').write_text('# Recent Release Notes\n\n'+notes+'\n',encoding='utf-8')
        return result('Release Notes','PASS','Generated release notes from the latest 10 Git commits.',details={'git_log':r,'output':'complaudi_skills/reports/release-notes.md'})
    return result('Release Notes','WARN','No Git commit history available; release notes were not generated.',details=r)
