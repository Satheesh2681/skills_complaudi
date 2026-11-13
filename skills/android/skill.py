from ...core.utils import result

def execute(root):
    p=root/'web'/'android'; exists=p.exists() and any(p.iterdir())
    findings=[] if exists else [{'severity':'INFO','issue':'No populated Android platform project detected.'}]
    findings.append({'severity':'INFO','issue':'Android emulator/device tests require Android SDK and an available emulator/device; repository detection only is performed here.'})
    return result('Android Compatibility','WARN','Detected Android project assets; native device tests depend on local Android tooling.',findings,{'android_project_detected':exists})
