import json
from ...core.utils import result, run

def execute(root):
    tags=run(['git','tag','--sort=-version:refname'],root,timeout=30)
    pkg={}
    try: pkg=json.loads((root/'package.json').read_text(encoding='utf-8'))
    except Exception: pass
    version=pkg.get('version') or (tags['output'].splitlines()[0] if tags['returncode']==0 and tags['output'].strip() else 'unknown')
    return result('Feature Versioning','PASS' if version!='unknown' else 'WARN','Read project version and Git tags; did not change version files or create tags.',details={'package_version':version,'git_tags':tags['output'].splitlines()[:10] if tags['returncode']==0 else []})
