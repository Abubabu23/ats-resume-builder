"""ATS scoring, resume model, quality checks and one-page PDF rendering."""
import copy
import io
import re

from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

KW = ['python', 'sql', 'machine learning', 'deep learning', 'nlp', 'computer vision', 'pandas', 'numpy',
      'scikit-learn', 'tensorflow', 'pytorch', 'keras', 'power bi', 'tableau', 'excel', 'statistics',
      'data visualization', 'data analysis', 'data cleaning', 'eda', 'feature engineering', 'regression',
      'classification', 'clustering', 'time series', 'llm', 'generative ai', 'genai', 'langchain', 'rag',
      'prompt engineering', 'agentic ai', 'openai', 'hugging face', 'transformers', 'opencv', 'yolo', 'git',
      'github', 'docker', 'aws', 'azure', 'gcp', 'flask', 'fastapi', 'streamlit', 'django', 'api', 'rest',
      'mongodb', 'mysql', 'postgresql', 'etl', 'big data', 'spark', 'hadoop', 'java', 'c++', 'javascript',
      'react', 'html', 'css', 'matplotlib', 'seaborn', 'plotly', 'jupyter', 'linux', 'agile',
      'data annotation', 'model deployment', 'mlops', 'a/b testing', 'hypothesis testing',
      'data structures', 'algorithms', 'oop', 'analytics', 'reporting', 'dashboard', 'kpi',
      'business intelligence', 'data modeling', 'data warehouse', 'nosql', 'neural networks', 'cnn', 'rnn',
      'lstm', 'bert', 'gpt', 'vector database', 'embeddings', 'fine-tuning', 'predictive modeling',
      'data mining', 'cloud', 'snowflake', 'databricks', 'kafka', 'airflow', 'dbt', 'looker', 'bigquery', 'redshift',
      'xgboost', 'lightgbm', 'nltk', 'spacy', 'mlflow', 'kubernetes', 'ci/cd', 'pytest', 'data pipelines',
      'data engineering', 'natural language processing', 'recommendation systems', 'power query', 'dax',
      'forecasting', 'anomaly detection', 'statistical modeling', 'faiss', 'pinecone', 'chroma', 'beautifulsoup',
      'selenium', 'web scraping', 'tf-idf', 'cosine similarity', 'feature selection', 'model evaluation',
      'cross-validation', 'hyperparameter tuning', 'ollama', 'groq']
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ACTION_IRREGULAR = {'built', 'led', 'ran', 'wrote', 'made', 'drove', 'taught'}


def norm(t):
    t = str(t).lower()
    t = re.sub(r'scikit[\s-]?learn', 'scikit-learn', t).replace('powerbi', 'power bi')
    return ' ' + re.sub(r'gen\s?ai', 'genai', t) + ' '


def has(t, k):
    return re.search(r'(?<![a-z0-9+#])' + re.escape(k) + r'(?![a-z0-9+#])', t) is not None


def pts(s):
    """One bullet per line. Strips leading bullet marks and list numbering like '1.' or '2)'."""
    out = []
    for x in str(s or '').split('\n'):
        x = re.sub(r'^[\s\-•*·▪●◦]+', '', x)
        x = re.sub(r'^\(?\d{1,2}[.)]\s*(?=[A-Za-z])', '', x).strip()
        if x:
            out.append(x)
    return out


def cnt(text, kws):
    t = norm(text)
    return sum(1 for k in kws if has(t, k))


def fm(m):
    if not m:
        return ''
    a = str(m).split('-')
    try:
        return f"{MON[int(a[1]) - 1]} {a[0]}" if len(a) > 1 else a[0]
    except (ValueError, IndexError):
        return str(m)


def ds(x):
    if x.get('start') or x.get('end') or x.get('cur'):
        return ' – '.join(p for p in [fm(x.get('start')), 'Present' if x.get('cur') else fm(x.get('end'))] if p)
    return x.get('dur') or x.get('yr') or ''


def full_name(p):
    return ' '.join(x for x in [p.get('first'), p.get('mid'), p.get('last')] if x)


def jd_keywords(jd):
    t = norm(jd or '')
    return [k for k in KW if has(t, k)]


def top_projects(prof, jd, n=3):
    jk = jd_keywords(jd)
    ps = [p for p in prof.get('proj', []) if p.get('name')]
    ps = sorted(enumerate(ps), key=lambda ip: (-cnt(f"{ip[1]['name']} {ip[1].get('tech', '')} {ip[1].get('pts', '')}", jk), ip[0]))
    return [p for _, p in ps][:n]


def full_text(prof):
    P = prof['p']
    parts = [P.get('summary', ''), P.get('skills', ''), P.get('ach', '')]
    parts += [f"{c.get('name', '')} {c.get('issuer', '')}" for c in prof.get('cert', [])]
    for k in ('exp', 'intern'):
        parts += [f"{x.get('role', '')} {x.get('pts', '')}" for x in prof.get(k, [])]
    parts += [f"{x.get('name', '')} {x.get('tech', '')} {x.get('pts', '')}" for x in prof.get('proj', [])]
    return ' '.join(parts)


def _visible_text(prof, jd):
    P = prof['p']
    parts = [P.get('summary', ''), P.get('skills', ''), P.get('ach', '')]
    parts += [f"{c.get('name', '')} {c.get('issuer', '')}" for c in prof.get('cert', [])]
    for k in ('exp', 'intern'):
        parts += [f"{x.get('role', '')} {x.get('pts', '')}" for x in prof.get(k, [])]
    parts += [f"{x['name']} {x.get('tech', '')} {x.get('pts', '')}" for x in top_projects(prof, jd)]
    return ' '.join(parts)


def ats(prof, jd):
    P = prof['p']
    jk = jd_keywords(jd)
    pn = norm(_visible_text(prof, jd))
    matched = [k for k in jk if has(pn, k)]
    missing = [k for k in jk if not has(pn, k)]
    checks = [(P.get('email'), 5, 'Add your email'), (P.get('phone'), 5, 'Add your phone'),
              (P.get('summary'), 5, 'Write a summary'), (P.get('skills'), 5, 'Fill your skills'),
              (any(e.get('deg') for e in prof.get('edu', [])), 4, 'Add education'),
              (any(x.get('co') or x.get('pts') for x in prof.get('exp', []) + prof.get('intern', []))
               or any(p.get('name') for p in prof.get('proj', [])), 3, 'Add experience or projects'),
              (P.get('github') or P.get('linkedin') or P.get('portfolio'), 3, 'Add a GitHub / LinkedIn link')]
    fmt = sum(w for ok, w, _ in checks if ok)
    tips = [t for ok, _, t in checks if not ok]
    total = round(70 * len(matched) / len(jk) + fmt) if jk else 0
    return {'total': total, 'kws': jk, 'matched': matched, 'missing': missing, 'tips': tips, 'fmt': fmt}


def build_model(prof, jd, ats_safe=True):
    P = prof['p']
    jk = jd_keywords(jd)
    top = top_projects(prof, jd)
    hidden = [p['name'] for p in prof.get('proj', []) if p.get('name') and p not in top]

    def bl(s):
        return sorted(pts(s), key=lambda b: -cnt(b, jk))[:3]

    sec = []
    if P.get('summary'):
        sec.append({'h': 'SUMMARY', 'p': P['summary']})
    lines = []
    for l in pts(P.get('skills')):
        cat, _, rest = l.partition(':') if ':' in l else ('', '', l)
        items = [s.strip() for s in rest.split(',') if s.strip()]
        items.sort(key=lambda s: 0 if cnt(s, jk) else 1)
        if items:
            lines.append({'cat': cat.strip(), 'items': items})
    if lines:
        sec.append({'h': 'SKILLS', 'lines': lines})
    if top:
        sec.append({'h': 'PROJECTS', 'e': [{'t': p['name'], 'tech': p.get('tech', ''), 'd': p.get('link', ''), 'b': bl(p.get('pts'))} for p in top]})
    ed = [e for e in prof.get('edu', []) if e.get('deg') and (e.get('inst') or e.get('start') or e.get('end') or e.get('cur') or e.get('score') or e.get('yr'))]
    if ed:
        sec.append({'h': 'EDUCATION', 'e': [{'t': e['deg'], 's': ' – '.join(x for x in [e.get('inst'), e.get('score')] if x), 'd': ds(e), 'l': e.get('loc', '')} for e in ed]})
    for k, h in (('exp', 'PROFESSIONAL EXPERIENCE'), ('intern', 'INTERNSHIPS')):
        ex = [x for x in prof.get(k, []) if x.get('co') or x.get('role')]
        if ex:
            sec.append({'h': h, 'e': [{'t': x.get('role') or x.get('co'), 's': x.get('co', '') if x.get('role') else '', 'd': ds(x), 'l': x.get('loc', ''), 'b': bl(x.get('pts'))} for x in ex]})
    cs = [c for c in prof.get('cert', []) if c.get('name')]
    if cs:
        sec.append({'h': 'CERTIFICATIONS', 'e': [{'t': c['name'] + (' – ' + c['issuer'] if c.get('issuer') else ''), 'd': ds(c)} for c in cs]})
    if pts(P.get('ach')):
        sec.append({'h': 'ACHIEVEMENTS', 'b': pts(P['ach'])})
    M = {'name': full_name(P) or P.get('name', ''), 'title': P.get('title', ''),
         'ct': [x for x in [P.get('email'), P.get('phone'), P.get('loc'), P.get('linkedin'), P.get('github'), P.get('portfolio')] if x],
         'sec': sec, 'hidden': hidden}
    if ats_safe:  # date + location move onto the subtitle line (single-line parsing)
        for s in sec:
            for e in s.get('e', []):
                m = ' | '.join(x for x in [e.get('d'), e.get('l')] if x)
                if m:
                    e['s'] = ' | '.join(x for x in [e.get('s'), m] if x)
                    e['d'] = e['l'] = ''
    return M


def model_text(M):
    t = [M['name'] + ('\n' + M['title'] if M['title'] else ''), ' | '.join(M['ct'])]
    for s in M['sec']:
        t.append('\n' + s['h'])
        if s.get('p'):
            t.append(s['p'])
        for l in s.get('lines', []):
            t.append((l['cat'] + ': ' if l['cat'] else '') + ', '.join(l['items']))
        for e in s.get('e', []):
            t.append(e['t'] + (', ' + e['s'] if e.get('s') else '') + (f" ({e['tech']})" if e.get('tech') else '')
                     + (' | ' + e['d'] if e.get('d') else '') + (' | ' + e['l'] if e.get('l') else ''))
            t += ['- ' + b for b in e.get('b', [])]
        t += ['- ' + b for b in s.get('b', [])]
    return '\n'.join(t)


def quality(M):
    txt = model_text(M)
    bl = []
    summary = ''
    for s in M['sec']:
        summary = s.get('p', summary)
        for e in s.get('e', []):
            bl += e.get('b', [])
        bl += s.get('b', [])
    wc = len(txt.split())
    w = []
    if wc > 620:
        w.append(f'Resume is about {wc} words: too long for one page.')
    if wc < 250:
        w.append(f'Resume is about {wc} words: add more projects or bullets.')
    if len(summary.split()) > 80:
        w.append(f'Summary is {len(summary.split())} words: keep it under 80.')
    weak = [b for b in bl if not (b.split()[0].lower().endswith('ed') or b.split()[0].lower() in ACTION_IRREGULAR)]
    if weak:
        w.append(f'{len(weak)} bullets do not start with an action verb (Built, Developed...).')
    long_ = [b for b in bl if len(b.split()) > 32]
    if long_:
        w.append(f'{len(long_)} bullets are too long (keep under 30 words).')
    if bl and not any(ch.isdigit() for b in bl for ch in b):
        w.append('No numbers in bullets. Add real numbers or results if you have them.')
    return w


def render_pdf(M, tp='classic', z=None):
    """Text-based (ATS-readable) A4 PDF. Returns (bytes, page_count)."""
    W, H = 595.27, 841.89
    L, R = 38, 557
    TW = R - L
    ce = tp == 'classic'
    F = {'n': 'Times-Roman', 'b': 'Times-Bold', 'i': 'Times-Italic'} if ce else {'n': 'Helvetica', 'b': 'Helvetica-Bold', 'i': 'Helvetica-Oblique'}
    z = z or (9.2 if tp == 'compact' else 9.6 if ce else 10.5)
    lh = z + 1.9
    ac = (0.06, 0.46, 0.43) if tp == 'modern' else (0, 0, 0)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"{M['name']} - Resume")
    st = {'y': 40.0, 'p': 1}
    cx = W / 2

    def nl(n):
        if st['y'] + n > 814:
            c.showPage()
            st['y'], st['p'] = 40.0, st['p'] + 1

    def tx(t, x, s='n', size=None, al='l'):
        c.setFont(F[s], size or z)
        fn = {'r': c.drawRightString, 'c': c.drawCentredString}.get(al, c.drawString)
        fn(x, H - st['y'], t)

    def par(t, x, w, s='n'):
        for ln in simpleSplit(t, F[s], z, w):
            nl(lh)
            tx(ln, x, s)
            st['y'] += lh

    def bu(b):
        for i, ln in enumerate(simpleSplit(b, F['n'], z, TW - 14)):
            nl(lh)
            if not i:
                tx('•', L + 3)
            tx(ln, L + 14)
            st['y'] += lh

    hx, al = (cx, 'c') if ce else (L, 'l')
    c.setFillColorRGB(*ac)
    tx(M['name'], hx, 'b', 22 if ce else 20, al)
    st['y'] += 17
    c.setFillColorRGB(0, 0, 0)
    if M['title']:
        tx(M['title'], hx, 'i' if ce else 'n', z + 2, al)
        st['y'] += 15
    for ln in simpleSplit(' | '.join(M['ct']), F['n'], z - 1, TW):
        tx(ln, hx, 'n', z - 1, al)
        st['y'] += z + 1.5
    for s in M['sec']:
        st['y'] += 5
        nl(62)
        c.setFillColorRGB(*ac)
        tx(s['h'], L, 'b', z + 1)
        st['y'] += 3.5
        c.setStrokeColorRGB(*ac)
        c.setLineWidth(1.5 if ce else 0.7)
        c.line(L, H - st['y'], R, H - st['y'])
        c.setFillColorRGB(0, 0, 0)
        st['y'] += z + 3
        if s.get('p'):
            par(s['p'], L, TW)
        for l in s.get('lines', []):
            par((l['cat'] + ': ' if l['cat'] else '') + (', ' if l['cat'] else ' | ').join(l['items']), L, TW)
        for e in s.get('e', []):
            nl(36)
            y0 = st['y']
            dw = 120 if (e.get('d') or e.get('l')) else 0
            for ln in simpleSplit(e['t'], F['b'], z, TW - dw):
                tx(ln, L, 'b')
                st['y'] += lh
            y1 = st['y']
            if e.get('d'):
                st['y'] = y0
                tx(e['d'], R, 'n', z - 0.5, 'r')
            if e.get('l'):
                st['y'] = y0 + lh
                tx(e['l'], R, 'i', z - 0.5, 'r')
            st['y'] = y1
            if e.get('s'):
                par(e['s'], L, TW - dw, 'i')
            if e.get('tech'):
                par(e['tech'], L, TW, 'i')
            if e.get('l') and not e.get('s') and not e.get('tech'):
                st['y'] = max(st['y'], y0 + 2 * lh)
            for b in e.get('b', []):
                bu(b)
            st['y'] += 3
        for b in s.get('b', []):
            bu(b)
    c.save()
    return buf.getvalue(), st['p']


def fit_one_page(M, tp='classic'):
    """Shrink font to 8.4pt, then drop the least relevant bullets, until it is one page."""
    base = 9.2 if tp == 'compact' else 9.6 if tp == 'classic' else 10.5
    C = copy.deepcopy(M)
    trimmed = []
    z = base
    while z >= 8.39:
        pdf, pages = render_pdf(C, tp, z)
        if pages < 2:
            return {'pdf': pdf, 'z': z, 'trimmed': trimmed, 'over': False, 'model': C}
        z = round(z - 0.2, 2)
    for _ in range(40):
        best, bc = None, 1
        for s in C['sec']:
            for e in s.get('e', []):
                if len(e.get('b', [])) > bc:
                    best, bc = e, len(e['b'])
        if not best:
            break
        trimmed.append(best['b'].pop())
        pdf, pages = render_pdf(C, tp, 8.4)
        if pages < 2:
            return {'pdf': pdf, 'z': 8.4, 'trimmed': trimmed, 'over': False, 'model': C}
    pdf, _ = render_pdf(C, tp, 8.4)
    return {'pdf': pdf, 'z': 8.4, 'trimmed': trimmed, 'over': True, 'model': C}


def parse_check(pdf_bytes, M):
    """Re-reads the generated PDF like an ATS would. Returns (checks, extracted_text)."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    text = '\n'.join(p.get_text() for p in doc)
    up = text.upper()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    heads = [s['h'] for s in M['sec']]
    pos = [up.find(h) for h in heads]
    first_head = min([p for p in pos if p >= 0], default=len(text))
    email = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    phone = re.search(r'(?<!\d)\+?\d[\d\s().-]{8,}\d(?!\d)', text)
    months = len(re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}', text))
    checks = [
        ('Text is selectable (not an image)', len(text.strip()) > 200, f'{len(text.split())} words read'),
        ('One page', len(doc) == 1, f'{len(doc)} page(s)'),
        ('Name is the first line', bool(lines) and lines[0] == M['name'], lines[0] if lines else 'nothing read'),
        ('Email found', bool(email), email.group(0) if email else 'not found'),
        ('Phone found', bool(phone), phone.group(0) if phone else 'not found'),
        ('Contact appears before the first section', bool(email) and email.start() < first_head, ''),
        ('All section headings found', all(p >= 0 for p in pos), ', '.join(h for h, p in zip(heads, pos) if p < 0) or 'all present'),
        ('Sections are in the expected order', pos == sorted(pos), ''),
        ('Dates are readable', months > 0 or not any(e.get('d') or e.get('s') for s in M['sec'] for e in s.get('e', [])), f'{months} dates found'),
        ('No broken characters', '\ufffd' not in text and '\u25a0' not in text, ''),
    ]
    return checks, text
