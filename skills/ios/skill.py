from ...core.utils import result

def execute(root):
    p=root/'web'/'ios'
    exists=p.exists() and any(p.iterdir())
    findings=[] if exists else [{'severity':'INFO','issue':'No populated iOS platform project detected.'}]
    findings.append({'severity':'INFO','issue':'iOS simulator/device execution requires macOS with Xcode; this Ubuntu run performs repository-level detection only.'})
    return result('iOS Compatibility','WARN','Detected iOS project assets; native simulator testing is unavailable on Ubuntu.',findings,{'ios_project_detected':exists})
