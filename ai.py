"""AI suggestions (Groq first, Gemini fallback), contact masking and limit messages."""
import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import requests

from core import KW, full_text, has, norm, pts

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


def _post(url, **kw):
    r = requests.post(url, timeout=45, **kw)
    if r.status_code == 429:
        ra = r.headers.get('retry-after', '')
        try:
            raise AILimit(float(ra))
        except ValueError:
            raise AILimit(None)
    r.raise_for_status()
    return r.json()


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
        providers.append(lambda: _groq(prompt, secrets['GROQ_API_KEY'], secrets.get('GROQ_MODEL', 'llama-3.3-70b-versatile')))
    if secrets.get('GEMINI_API_KEY'):
        providers.append(lambda: _gemini(prompt, secrets['GEMINI_API_KEY'], secrets.get('GEMINI_MODEL', 'gemini-2.5-flash')))
    if not providers:
        raise RuntimeError('No AI key configured. Add GROQ_API_KEY or GEMINI_API_KEY in secrets.')
    limits, last = [], None
    for call in providers:
        try:
            return json.loads(call())
        except AILimit as e:
            limits.append(e.seconds)
        except Exception as e:  # network / parse errors: try the next provider
            last = e
    if limits:
        known = [s for s in limits if s]
        raise AILimit(min(known) if known else None)
    raise RuntimeError(f'AI request failed: {last}')


def units(prof):
    u = []
    if prof['p'].get('summary'):
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


def flags(prof, original, suggestion):
    """Skills or numbers in a suggestion that are not already in the profile."""
    base = full_text(prof)
    pn, sn = norm(base), norm(suggestion)
    bad = [k for k in KW if has(sn, k) and not has(pn, k)]
    bad += [n for n in re.findall(r'\d+(?:\.\d+)?%?', suggestion) if n not in base]
    return bad


def suggest(prof, jd, title, secrets):
    """Returns {unit_id: suggested_text}. Contact details are never included."""
    items = [{'id': u['id'], 'text': mask(u['text'])} for u in units(prof)]
    prompt = (f"You are an ATS resume editor. Job title: {title}\nJD:\n{mask(jd)}\n\n"
              f"Candidate facts (the ONLY facts you may use):\nSkills: {mask(prof['p'].get('skills', ''))}\n"
              f"Certifications: {'; '.join(c.get('name', '') for c in prof.get('cert', []))}\n\n"
              "Rewrite each item to be clearer, start with an action verb, and use JD wording only for terms the candidate "
              "already has. STRICT: never add any skill, tool, number, metric, employer or claim that is not in the original item "
              "or the facts above. One line, under 28 words. Skip items that are already good. "
              'Return ONLY JSON: {"items":[{"id":"...","text":"..."}]}\n'
              f"Items:\n{json.dumps(items)}")
    data = ask_json(prompt, secrets)
    out = data.get('items', []) if isinstance(data, dict) else data
    originals = {u['id']: u['text'] for u in units(prof)}
    return {o['id']: str(o['text']) for o in out
            if isinstance(o, dict) and o.get('id') in originals and o.get('text') and o['text'] != originals[o['id']]}
