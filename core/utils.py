from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path

SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "build", "coverage", ".next", "playwright-report", "test-results"}
TEXT_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".html", ".css", ".scss", ".json", ".yml", ".yaml", ".md", ".xml", ".toml", ".sh"}

def run(cmd, cwd, timeout=300):
    start=time.time()
    try:
        p=subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return {"command":cmd,"returncode":p.returncode,"output":p.stdout[-12000:],"duration_seconds":round(time.time()-start,2),"timed_out":False}
    except subprocess.TimeoutExpired as e:
        out=e.stdout or ""
        if isinstance(out,bytes): out=out.decode(errors="replace")
        return {"command":cmd,"returncode":124,"output":str(out)[-12000:]+"\nTimed out", "duration_seconds":round(time.time()-start,2),"timed_out":True}
    except FileNotFoundError:
        return {"command":cmd,"returncode":127,"output":f"Executable not found: {cmd[0]}","duration_seconds":round(time.time()-start,2),"timed_out":False}

def files(root):
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP for part in p.relative_to(root).parts):
            yield p

def text_files(root):
    for p in files(root):
        if p.suffix.lower() in TEXT_EXT:
            try:
                if p.stat().st_size <= 2_000_000: yield p, p.read_text(encoding="utf-8", errors="ignore")
            except OSError: pass

def result(name, status, summary, findings=None, details=None):
    return {"skill":name,"status":status,"summary":summary,"findings":findings or [],"details":details or {}}

def redact(s):
    import re
    s=re.sub(r'(?i)(password|secret|token|api[_-]?key)(\s*[=:]\s*)["\']?[^\s"\']+',r'\1\2[REDACTED]',s)
    return s
