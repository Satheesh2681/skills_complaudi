import time
from ...core.utils import result, run

def execute(root):
    start=time.time(); details={}; findings=[]
    if (root/'package.json').exists():
        details['build_timing']=run(['npm','run','build'],root,timeout=600)
        if details['build_timing']['returncode']!=0: findings.append({'severity':'HIGH','issue':'Build failed; performance assessment is incomplete.'})
    elapsed=round(time.time()-start,2)
    details['assessment_seconds']=elapsed
    findings.append({'severity':'INFO','issue':'This is a static/build-time performance baseline, not a live load test. Configure a staging URL and load-test tool for throughput/latency measurements.'})
    return result('Performance Testing', 'WARN' if findings else 'PASS','Measured build execution time; live load testing requires a staging target.',findings,details)
