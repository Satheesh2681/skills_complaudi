from __future__ import annotations
import argparse, importlib, json, os, sys, time, html
from datetime import datetime, timezone
from pathlib import Path
from .utils import run

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parents[1]
ORDER=[
 ('Code Coverage / Unit Testing','code_coverage'),('Security Checker','security_checker'),('Performance Testing','performance'),('SEO','seo'),('UAT Testing','uat'),('Mock Testing','mock_testing'),('Security Testing','security_testing'),('Mobile Compatibility','mobile'),('iOS','ios'),('Android','android'),('Release Notes','release_notes'),('Feature Versioning','feature_versioning'),
]

def write_reports(project, records, metadata):
    out=BASE/'reports'; out.mkdir(parents=True,exist_ok=True)
    summary={'project':str(project),'generated_at':datetime.now(timezone.utc).isoformat(),'metadata':metadata,'results':records}
    (out/'assessment-report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    rows=[]
    for r in records:
        rows.append(f"<tr><td>{html.escape(r['skill'])}</td><td class='{r['status'].lower()}'>{r['status']}</td><td>{html.escape(r['summary'])}</td></tr>")
    doc='''<!doctype html><html><head><meta charset="utf-8"><title>Complaudi Assessment</title><style>body{font:15px system-ui;margin:36px;color:#172033}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:10px;text-align:left}.pass{color:#087443}.warn{color:#9a6700}.fail{color:#b42318}code{background:#eee;padding:3px}</style></head><body><h1>Complaudi Assessment Report</h1><p>Project: <code>'''+html.escape(str(project))+'''</code></p><p>Generated: '''+html.escape(summary['generated_at'])+'''</p><table><thead><tr><th>Stage</th><th>Status</th><th>Summary</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table><h2>Findings</h2>'''
    for r in records:
        if r.get('findings'):
            doc+=f"<h3>{html.escape(r['skill'])}</h3><ul>"+''.join(f"<li>{html.escape(str(f))}</li>" for f in r['findings'])+'</ul>'
    doc+='</body></html>'
    (out/'assessment-report.html').write_text(doc,encoding='utf-8')
    return out

def main():
    ap=argparse.ArgumentParser(description='Complaudi sequential project assessment engine')
    ap.add_argument('--project',default='.',help='Local project directory to assess')
    args=ap.parse_args(); project=Path(args.project).resolve()
    if not project.is_dir(): print(f'[ERROR] Project directory not found: {project}'); return 2
    print('='*48+'\n COMPLAUDI SKILLS ENGINE\n'+'='*48)
    # Checkout means validate/use the current local working copy; do not reset, checkout, stash, or alter user changes.
    print('\n[01] CODE CHECKOUT')
    git=run(['git','rev-parse','--show-toplevel'],project,timeout=20)
    if git['returncode']==0:
        branch=run(['git','branch','--show-current'],project,timeout=20)
        dirty=run(['git','status','--short'],project,timeout=20)
        print(f"[PASS] Local repository: {git['output'].strip()} | branch: {branch['output'].strip() or '(detached)'}")
        if dirty['output'].strip(): print('[INFO] Working tree has local changes; they will be preserved.')
        checkout={'status':'PASS','summary':'Validated current local Git working copy; no checkout/reset/stash performed.','details':{'branch':branch['output'].strip(),'working_tree':dirty['output'][:4000]}}
    else:
        print('[WARN] Directory is not a Git repository; continuing with local files.')
        checkout={'status':'WARN','summary':'No Git repository detected; assessed current local directory.','details':{}}
    print('\n[02] BUILD & COMPILATION')
    if (project/'package.json').exists(): build=run(['npm','run','build'],project,timeout=900)
    elif (project/'pyproject.toml').exists(): build=run([sys.executable,'-m','compileall','-q','.'],project,timeout=300)
    else: build={'returncode':0,'output':'No recognized build manifest; generic build stage skipped.','duration_seconds':0,'command':[]}
    print(f"{'[PASS]' if build['returncode']==0 else '[FAIL]'} Build: {build['output'][-700:].strip()}")
    records=[{'skill':'Code Checkout','status':checkout['status'],'summary':checkout['summary'],'findings':[],'details':checkout['details']},{'skill':'Build & Compilation','status':'PASS' if build['returncode']==0 else 'FAIL','summary':'Build command completed.' if build['returncode']==0 else 'Build failed; downstream skills were stopped.','findings':[],'details':build}]
    if build['returncode']!=0:
        print('\n[STOP] Build failed. Fix build errors before assessment skills can run.')
        out=write_reports(project,records,{'stopped_at':'build'})
        print(f'\nReport: {out}/assessment-report.html'); return 1
    print('\n[03] SKILLS EXECUTION')
    for idx,(label,module) in enumerate(ORDER,1):
        print(f'  [{idx:02d}] {label} ...',end=' ',flush=True)
        try:
            m=importlib.import_module(f'complaudi_skills.skills.{module}.skill')
            item=m.execute(project)
        except Exception as e:
            item={'skill':label,'status':'FAIL','summary':f'Skill crashed safely: {type(e).__name__}: {e}','findings':[],'details':{}}
        records.append(item); print(item['status'])
    print('\n[04] REPORT GENERATION')
    m=importlib.import_module('complaudi_skills.skills.report_generation.skill')
    records.append(m.execute(project))
    out=write_reports(project,records,{'checkout':'local working copy','build_command':build.get('command'),'execution_order':[x[0] for x in ORDER]})
    counts={s:sum(1 for r in records if r['status']==s) for s in ('PASS','WARN','FAIL')}
    print('\n'+'='*48+'\n ASSESSMENT COMPLETED\n'+'='*48)
    print(f"Total stages: {len(records)} | Passed: {counts['PASS']} | Warnings: {counts['WARN']} | Failed: {counts['FAIL']}")
    print(f'Report (HTML): {out}/assessment-report.html')
    print(f'Report (JSON): {out}/assessment-report.json')
    print('Note: WARN means a check needs environment-specific setup or manual review; it is not a passed test.')
    return 0 if counts['FAIL']==0 else 1

if __name__=='__main__': raise SystemExit(main())
