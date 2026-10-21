"""AI suggestions (Groq first, Gemini fallback), contact masking and limit messages."""
import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import requests

from core import KW, ds, full_text, has, norm, pts

IST = ZoneInfo('Asia/Kolkata')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
PHONE = re.compile(r'(?<!\d)\+?\d[\d\s().-]{8,}\d(?!\d)')
URL = re.compile(r'(?:https?://|www\.)\S+|(?:linkedin|github)\.com/\S*', re.I)


class AILimit(Exception):
    """Raised when every AI provider is out of free quota."""

    def __init__(self, seconds=None):
        super().__init__('AI limit reached')
        self.seconds = seconds


def mask(text):
    """Remove emails, phone numbers and profile links before text goes to an AI provider."""
    text = EMAIL.sub('[EMAIL]', str(text))
    text = URL.sub('[LINK]', text)
    return PHONE.sub('[PHONE]', text)


def seconds_to_midnight():
    now = dt.datetime.now(IST)
    nxt = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (nxt - now).total_seconds()


def limit_message(seconds=None):
    if not seconds:
        return 'The free AI limit is finished for now. Please try again after some time.'
    h, m = divmod(int(seconds // 60), 60)
    dur = f'{h}h {m}m' if h else f'{max(m, 1)}m'
    at = (dt.datetime.now(IST) + dt.timedelta(seconds=seconds)).strftime('%I:%M %p').lstrip('0')
    return f'The free AI limit is finished for now. Try again in {dur}, around {at}.'


class ModelError(Exception):
    """Provider rejected the request (unknown / retired model, bad parameter)."""


def _post(url, **kw):
    r = requests.post(url, timeout=45, **kw)
    if r.status_code == 429:
        ra = r.headers.get('retry-after', '')
        try:
            raise AILimit(float(ra))
        except ValueError:
            raise AILimit(None)
    if r.status_code in (400, 404):
        raise ModelError(f'{r.status_code}: {r.text[:160]}')
    r.raise_for_status()
    return r.json()


# Groq retired llama-3.3-70b-versatile on 2026-08-16, so we try current models in order.
GROQ_MODELS = ['openai/gpt-oss-120b', 'qwen/qwen3.6-27b', 'openai/gpt-oss-20b']
GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-flash-latest']


def _models(secrets, name, default):
    given = [m.strip() for m in str(secrets.get(name, '')).split(',') if m.strip()]
    return given or default


def _try_models(fn, models):
    last = None
    for m in models:
        try:
            return fn(m)
        except ModelError as e:
            last = e
    raise last


def _json(text):
    t = text.strip()
    i, j = t.find('{'), t.rfind('}')
    return json.loads(t[i:j + 1] if 0 <= i < j else t)


def _groq(prompt, key, model):
    j = _post('https://api.groq.com/openai/v1/chat/completions', headers={'Authorization': 'Bearer ' + key},
              json={'model': model, 'temperature': 0.2, 'response_format': {'type': 'json_object'},
                    'messages': [{'role': 'user', 'content': prompt}]})
    return j['choices'][0]['message']['content']


def _gemini(prompt, key, model):
    j = _post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
              params={'key': key},
              json={'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json'}})
    return j['candidates'][0]['content']['parts'][0]['text']


def ask_json(prompt, secrets):
    """Try Groq, then Gemini. Raises AILimit if all configured providers are rate limited."""
    providers = []
    if secrets.get('GROQ_API_KEY'):
        providers.append(lambda: _try_models(lambda m: _groq(prompt, secrets['GROQ_API_KEY'], m), _models(secrets, 'GROQ_MODEL', GROQ_MODELS)))
    if secrets.get('GEMINI_API_KEY'):
        providers.append(lambda: _try_models(lambda m: _gemini(prompt, secrets['GEMINI_API_KEY'], m), _models(secrets, 'GEMINI_MODEL', GEMINI_MODELS)))
    if not providers:
        raise RuntimeError('No AI key configured. Add GROQ_API_KEY or GEMINI_API_KEY in secrets.')
    limits, last = [], None
    for call in providers:
        try:
            return _json(call())
        except AILimit as e:
            limits.append(e.seconds)
        except Exception as e:  # network / parse errors: try the next provider
            last = e
    if limits:
        known = [s for s in limits if s]
        raise AILimit(min(known) if known else None)
    raise RuntimeError(f'AI request failed: {last}')


def units(prof, include_summary=True):
    u = []
    if include_summary and prof['p'].get('summary'):
        u.append({'id': 's', 'label': 'Summary', 'text': prof['p']['summary']})
    for k in ('exp', 'intern', 'proj'):
        for i, x in enumerate(prof.get(k, [])):
            for j, b in enumerate(pts(x.get('pts'))):
                u.append({'id': f'{k}:{i}:{j}', 'label': x.get('name') or x.get('role') or x.get('co') or k, 'text': b})
    return u


def set_unit(prof, uid, text):
    if uid == 's':
        prof['p']['summary'] = text
        return
    k, i, j = uid.split(':')
    x = prof[k][int(i)]
    lines = pts(x.get('pts'))
    lines[int(j)] = text
    x['pts'] = '\n'.join(lines)


GUARD_SKIP = {'reporting', 'analytics', 'dashboard', 'cloud', 'api', 'rest', 'agile', 'kpi', 'oop', 'algorithms', 'data analysis'}


def flags(prof, original, suggestion):
    """Skills or numbers in a suggestion that are not already in the profile."""
    base = full_text(prof) + ' ' + ' '.join(f"{e.get('deg', '')} {e.get('inst', '')} {ds(e)} {e.get('score', '')}" for e in prof.get('edu', []))
    pn, sn = norm(base), norm(suggestion)
    bad = [k for k in KW if k not in GUARD_SKIP and has(sn, k) and not has(pn, k)]
    bad += [n for n in re.findall(r'\d+(?:\.\d+)?%?', suggestion) if n not in base]
    return bad


def facts(prof):
    """Facts the AI may use. Contact details are never included."""
    P = prof['p']
    L = ['Skills: ' + mask(P.get('skills', '').replace('\n', '; '))]
    for e in prof.get('edu', []):
        if e.get('deg') and (e.get('inst') or e.get('start') or e.get('end')):
            L.append(f"Education: {e['deg']}, {e.get('inst', '')} ({ds(e)})")
    for k, lab in (('exp', 'Experience'), ('intern', 'Internship')):
        for x in prof.get(k, []):
            if x.get('co') or x.get('role'):
                L.append(f"{lab}: {x.get('role', '')} at {x.get('co', '')} ({ds(x)})")
                L += ['  - ' + mask(b) for b in pts(x.get('pts'))]
    for p in prof.get('proj', []):
        if p.get('name'):
            L.append(f"Project: {p['name']} ({p.get('tech', '')})")
            L += ['  - ' + mask(b) for b in pts(p.get('pts'))]
    for c in prof.get('cert', []):
        if c.get('name'):
            L.append(f"Certification: {c['name']} {c.get('issuer', '')}")
    if P.get('pref_loc'):
        L.append('Preference: ' + mask(P['pref_loc']))
    return '\n'.join(L)


SUMMARY_EXAMPLE = (
    "AI/ML Engineer with hands-on experience building GenAI systems: RAG pipelines, LLM integration, NLP model fine-tuning, and "
    "semantic search using FAISS. B.E. Computer Science graduate (2025) with a Data Science certification. Skilled in Python "
    "(Pandas, NumPy, Scikit-learn), statistical modelling, and end-to-end ML pipeline development, from data processing to "
    "deployment via Streamlit. Experienced in translating data insights into business-relevant solutions, from customer support "
    "automation to BI reporting for stakeholder decision-making. Diploma background in mechanical engineering complements data "
    "science for industrial and process-data analytics roles. Comfortable working independently and collaborating remotely using "
    "Git-based workflows and documentation-driven communication. Brings operational discipline and comfort in fast-paced "
    "environments from prior team leadership experience. Seeking an entry-level AI/ML Engineer role to build and deploy "
    "production-grade AI/ML solutions that solve real business problems.")


def suggest(prof, jd, title, secrets):
    """Returns {unit_id: suggested_text}. Contact details are never included."""
    items = [{'id': u['id'], 'text': mask(u['text'])} for u in units(prof, False)]
    prompt = (f"You are an ATS resume editor. Job title: {title}\nJD:\n{mask(jd)}\n\n"
              f"Candidate facts (the ONLY facts you may use):\n{facts(prof)}\n\n"
              "Rewrite each item to be clearer and ATS friendly, using JD wording only for terms the candidate already has. "
              "STRICT: never add any skill, tool, number, metric, employer, location or claim that is not in the original item "
              "or the facts above. "
              "For the item with id 's' (the summary) write 3 to 4 sentences, 60 to 80 words, in this order: (1) target role plus "
              "hands-on project experience with key tools; (2) education and work experience context including the employer and "
              "any live production work; (3) certifications; (4) the job target and, ONLY if a Preference fact exists, relocation. "
              f"Follow the structure of this example, not its facts: \"{SUMMARY_EXAMPLE}\" "
              "For every other item: one line, start with an action verb, under 28 words. Skip items that are already good. "
              'Return ONLY JSON: {"items":[{"id":"...","text":"..."}]}\n'
              f"Items:\n{json.dumps(items)}")
    data = ask_json(prompt, secrets)
    out = data.get('items', []) if isinstance(data, dict) else data
    originals = {u['id']: u['text'] for u in units(prof, False)}
    return {o['id']: str(o['text']) for o in out
            if isinstance(o, dict) and o.get('id') in originals and o.get('text') and o['text'] != originals[o['id']]}


def tailor_all(prof, jd, title, secrets):
    """One AI call: JD-specific summary (5-7 sentences) and rewritten bullets for the printed entries.
    Anything that adds a skill or number not in the profile is dropped. Returns {'summary','bullets','warn'}."""
    from core import jd_keywords, top_projects
    top = top_projects(prof, jd)
    vis = [u for u in units(prof, False) if not u['id'].startswith('proj:') or prof['proj'][int(u['id'].split(':')[1])] in top]
    items = [{'id': u['id'], 'text': mask(u['text'])} for u in vis]
    prompt = (f"You are an ATS resume tailor. Job title: {title}\nJD:\n{mask(jd)}\n\n"
              f"Candidate facts (the ONLY facts you may use):\n{facts(prof)}\n\n"
              f"Current summary (reference only): {mask(prof['p'].get('summary', ''))}\n\n"
              "TASK A, summary: write 5 to 7 sentences, 100 to 140 words, tailored to this JD. Order: (1) target-role headline with the "
              "hands-on systems and tools the JD asks for that the candidate really has; (2) education and certification; (3) skills and "
              "libraries; (4) experience turning data into business-relevant solutions, anchored in the project and work facts; "
              "(5) other background that complements the role (for example a diploma); (6) working style grounded in the facts "
              "(for example Git workflows, team leadership); (7) the job target and, ONLY if a Preference fact exists, relocation. "
              f"Follow the structure and depth of this example, not its facts: \"{SUMMARY_EXAMPLE}\"\n"
              f"JD skills to lead with when the candidate has them: {', '.join(jd_keywords(jd)) or 'none detected'}.\n"
              "TASK B, bullets: rewrite each item below so it highlights what matters for this JD, starts with an action verb, one line, "
              "under 28 words. Skip items that are already good.\n"
              "STRICT: never add any skill, tool, number, metric, employer, location or claim that is not in the facts.\n"
              'Return ONLY JSON: {"summary":"...","items":[{"id":"...","text":"..."}]}\n'
              f"Items:\n{json.dumps(items)}")
    data = ask_json(prompt, secrets)
    data = data if isinstance(data, dict) else {}
    warn, summary = [], str(data.get('summary', '')).strip() or None
    if summary:
        n = len(summary.split())
        bad = flags(prof, '', summary)
        if not 80 <= n <= 170:
            warn.append(f'AI summary had {n} words, so a profile-based summary was used.')
            summary = None
        elif bad:
            warn.append('AI summary added things not in your profile (' + ', '.join(bad[:4]) + '), so a profile-based summary was used.')
            summary = None
    originals = {u['id']: u['text'] for u in vis}
    bullets, dropped = {}, 0
    for o in data.get('items', []):
        if not isinstance(o, dict) or o.get('id') not in originals or not o.get('text'):
            continue
        t = str(o['text']).strip()
        if t == originals[o['id']]:
            continue
        if len(t.split()) > 45 or flags(prof, originals[o['id']], t):
            dropped += 1
            continue
        bullets[o['id']] = t
    if dropped:
        warn.append(f'{dropped} rewritten bullets were rejected because they added skills or numbers not in your profile.')
    return {'summary': summary, 'bullets': bullets, 'warn': warn}
