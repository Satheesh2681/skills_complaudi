from ...core.utils import result, text_files

def execute(root):
    findings=[]; html=list(root.rglob('*.html'))
    html=[p for p in html if not any(x in p.parts for x in ('node_modules','dist','build'))]
    if not html: findings.append({'severity':'WARN','issue':'No HTML files found for SEO inspection.'})
    for p in html:
        t=p.read_text(encoding='utf-8',errors='ignore').lower(); rel=str(p.relative_to(root))
        for label,token in [('title tag','<title'),('meta description','name="description"'),('viewport','name="viewport"')]:
            if token not in t: findings.append({'severity':'MEDIUM','file':rel,'issue':f'Missing {label}.'})
    for name in ('robots.txt','sitemap.xml'):
        if not any(p.name==name for p in root.rglob(name)): findings.append({'severity':'LOW','issue':f'{name} not found.'})
    return result('SEO', 'WARN' if findings else 'PASS','Inspected HTML metadata and common crawler files.',findings,{'html_files_scanned':len(html)})
