"""ATS Resume Builder - Streamlit app. Paste a JD, get an ATS-friendly one-page resume."""
import datetime as dt
import hmac
import json
import os
import uuid

import streamlit as st

import ai
import core
from store import get_store

st.set_page_config(page_title='ATS Resume Builder', page_icon='📄', layout='wide', initial_sidebar_state='collapsed')
st.markdown("""<style>
.block-container{padding-top:3.6rem;max-width:1100px}
.hero{background:linear-gradient(135deg,#0f766e,#134e4a);color:#fff;border-radius:16px;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
.hero b{font-size:1.25rem;display:block}.hero span{opacity:.85;font-size:.85rem}
.pill{background:rgba(255,255,255,.18);border-radius:99px;padding:5px 12px;font-size:.8rem;white-space:nowrap}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0}
.stat{background:#f1f5f9;border-radius:12px;padding:10px 14px}.stat small{color:#64748b;display:block;font-size:.75rem}.stat b{font-size:1.2rem;color:#0f172a}
.ringbox{display:flex;align-items:center;gap:14px;background:#f1f5f9;border-radius:14px;padding:10px 16px}
.ringbox small{display:block;color:#64748b}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:600}
div[data-testid="stExpander"]{border-radius:12px}
</style>""", unsafe_allow_html=True)

ss = st.session_state
LEVELS = ['B.E. Computer Science', 'Diploma', '12th (HSC)', '10th (SSLC)']
P_FIELDS = ['first', 'mid', 'last', 'title', 'email', 'phone', 'loc', 'linkedin', 'github', 'portfolio', 'summary', 'skills', 'ach', 'pref_loc']
DATE = [('start', 'Start date'), ('end', 'End date')]
KINDS = {
    'edu': ('Education', 'deg', [('deg', 'Level / Degree'), ('inst', 'School / College'), *DATE, ('cur', 'Currently pursuing'), ('score', 'CGPA / %'), ('loc', 'Location')]),
    'exp': ('Experience', 'role', [('role', 'Role'), ('co', 'Company'), *DATE, ('cur', 'Currently working'), ('loc', 'Location'), ('pts', 'Bullets (one per line, no numbers needed)')]),
    'intern': ('Internships', 'role', [('role', 'Role'), ('co', 'Company'), *DATE, ('cur', 'Currently working'), ('loc', 'Location'), ('pts', 'Bullets (one per line, no numbers needed)')]),
    'proj': ('Projects', 'name', [('name', 'Project name'), ('tech', 'Tech used'), ('link', 'Link'), ('pts', 'Bullets (one per line, no numbers needed)')]),
    'cert': ('Certifications', 'name', [('name', 'Certification'), ('issuer', 'Issuer'), *DATE, ('cur', 'In progress')]),
}
SOURCES = ['LinkedIn', 'GUVI', 'Naukri', 'Indeed', 'Other']
STATUSES = ['Applied', 'Interview', 'Offer', 'Rejected', 'Saved']
BADGE = {'Applied': '🟦', 'Interview': '🟨', 'Offer': '🟩', 'Rejected': '🟥', 'Saved': '⬜'}
IST = ai.IST
SUGGEST = ['Python', 'SQL', 'Machine Learning', 'Deep Learning', 'NLP', 'Computer Vision', 'Pandas', 'NumPy', 'Scikit-learn', 'TensorFlow',
           'PyTorch', 'Power BI', 'Tableau', 'Excel', 'Streamlit', 'Flask', 'FastAPI', 'Git/GitHub', 'Docker', 'AWS', 'LangChain', 'RAG',
           'LLM', 'FAISS', 'Statistics', 'Data Visualization', 'Matplotlib/Seaborn', 'MySQL', 'PostgreSQL', 'Plotly']
MONTHS = ['Month'] + core.MON
YEARS = ['Year'] + [str(y) for y in range(dt.date.today().year + 6, 1989, -1)]
ICONS = {'Profile': '👤', 'JD': '📋', 'Review': '✨', 'Resume': '📄', 'History': '🕘'}


def secrets():
    try:
        return dict(st.secrets)
    except Exception:
        return {}


@st.cache_resource
def store():
    return get_store(secrets())


def blank(kind, **kw):
    e = {'id': uuid.uuid4().hex[:8], **{f: '' for f, _ in KINDS[kind][2]}}
    e['cur'] = False
    e.update(kw)
    return e


def normalize(prof):
    prof = prof or {}
    out = {'p': {f: '' for f in P_FIELDS}}
    out['p'].update(prof.get('p', {}))
    for k in KINDS:
        out[k] = [{**blank(k), **e, 'id': e.get('id') or uuid.uuid4().hex[:8]} for e in prof.get(k, [])]
    if not out['edu']:
        out['edu'] = [blank('edu', deg=d) for d in LEVELS]
    groups = prof.get('skill_groups')
    if not groups:
        groups = []
        for line in core.pts(out['p'].get('skills', '')):
            cat, _, rest = line.partition(':') if ':' in line else ('', '', line)
            groups.append({'cat': cat.strip(), 'items': [x.strip() for x in rest.split(',') if x.strip()]})
    out['skill_groups'] = [{'id': g.get('id') or uuid.uuid4().hex[:8], 'cat': g.get('cat', ''), 'items': list(g.get('items', []))} for g in groups]
    if not out['skill_groups']:
        out['skill_groups'] = [{'id': uuid.uuid4().hex[:8], 'cat': '', 'items': []}]
    sync_skills(out)
    return out


def sync_skills(prof):
    """Keeps the text form of skills (used by scoring and PDF) in sync with the skill chips."""
    prof['p']['skills'] = '\n'.join((f"{g['cat'].strip()}: " if g['cat'].strip() else '') + ', '.join(g['items'])
                                   for g in prof['skill_groups'] if g['items'])


def today():
    return dt.datetime.now(IST).strftime('%Y-%m-%d')


def daily_limit():
    return int(secrets().get('AI_DAILY_LIMIT', 20))


# ---------- login ----------
def login():
    users = secrets().get('users') or ({'dev': 'dev'} if os.environ.get('APP_DEV') else {})
    st.markdown('<div class="hero"><div><b>📄 ATS Resume Builder</b><span>Paste a JD. Get an ATS-friendly one-page resume.</span></div></div>', unsafe_allow_html=True)
    if not users:
        st.error('No users configured. Add a [users] table in the app secrets.')
        st.stop()
    with st.container(border=True):
        st.subheader('Sign in')
        st.caption('Your resumes and history stay private to your account.')
        with st.form('login'):
            u = st.text_input('Username')
            p = st.text_input('Password', type='password')
            ok = st.form_submit_button('Sign in', type='primary', width='stretch')
        st.caption('🔒 Your email and phone are never sent to the AI.')
    if ok:
        ss.tries = ss.get('tries', 0) + 1
        exp = {k.lower(): v for k, v in users.items()}.get(u.strip().lower())
        if ss.tries > 8:
            st.error('Too many attempts. Reload the page and try again later.')
        elif exp is not None and hmac.compare_digest(str(exp).encode(), p.encode()):
            ss.user = u.strip().lower()
            st.rerun()
        else:
            st.error('Wrong username or password.')
    st.stop()


def sign_out():
    for k in list(ss):
        del ss[k]


def init_session():
    ss.prof = normalize(store().load_profile(ss.user))
    ss.saved = json.dumps(ss.prof, sort_keys=True)
    ss.job = {'title': '', 'company': '', 'source': 'LinkedIn', 'jd': ''}
    ss.sug, ss.limit, ss.msg = {}, None, None


def used():
    if ss.get('used_day') != today():
        ss.used, ss.used_day = store().get_usage(ss.user, today()), today()
    return ss.used


def ring(n):
    col = '#16a34a' if n >= 75 else '#d97706' if n >= 50 else '#dc2626'
    c = 2 * 3.14159 * 40
    return (f'<div class="ringbox"><svg width="96" height="96" viewBox="0 0 96 96"><circle cx="48" cy="48" r="40" fill="none" stroke="#e2e8f0" stroke-width="9"/>'
            f'<circle cx="48" cy="48" r="40" fill="none" stroke="{col}" stroke-width="9" stroke-linecap="round" stroke-dasharray="{c * n / 100:.1f} {c:.1f}" transform="rotate(-90 48 48)"/>'
            f'<text x="48" y="56" text-anchor="middle" font-size="26" font-weight="700" fill="{col}">{n}</text></svg>'
            f'<div><b>ATS score</b><small>out of 100</small></div></div>')


def stats(items):
    return '<div class="stats">' + ''.join(f'<div class="stat"><small>{k}</small><b>{v}</b></div>' for k, v in items) + '</div>'


def completeness(prof):
    P = prof['p']
    checks = [('Name', P.get('first') or P.get('last')), ('Email', P.get('email')), ('Phone', P.get('phone')), ('Summary', P.get('summary')),
              ('Skills', P.get('skills')), ('Education', any(e.get('inst') for e in prof['edu'])),
              ('Experience or internship', any(x.get('co') for x in prof['exp'] + prof['intern'])),
              ('Projects with bullets', any(x.get('pts') for x in prof['proj'])), ('Profile link', P.get('github') or P.get('linkedin') or P.get('portfolio'))]
    done = sum(1 for _, ok in checks if ok)
    return round(100 * done / len(checks)), [n for n, ok in checks if not ok]


# ---------- profile ----------
def tin(d, f, label, key, area=False, **kw):
    fn = st.text_area if area else st.text_input
    d[f] = fn(label, d.get(f, ''), key=key, **kw)


def month_picker(label, val, key):
    """Month + year dropdowns. Returns 'YYYY-MM', 'YYYY' (no month) or ''."""
    y, _, m = (val or '').partition('-')
    mi = int(m) if m.isdigit() and 1 <= int(m) <= 12 else 0
    c1, c2 = st.columns(2)
    mm = c1.selectbox(f'{label} month', MONTHS, mi, key=key + '_m')
    yy = c2.selectbox(f'{label} year', YEARS, YEARS.index(y) if y in YEARS else 0, key=key + '_y')
    if yy == 'Year':
        return ''
    return f'{yy}-{MONTHS.index(mm):02d}' if mm != 'Month' else yy


def editor(kind):
    title, label_f, fields = KINDS[kind]
    items = ss.prof[kind]
    for i, e in enumerate(items):
        with st.expander(e.get(label_f) or f'{title} {i + 1}'):
            for f, lab in fields:
                key = f'e_{kind}_{e["id"]}_{f}'
                if f == 'cur':
                    e[f] = st.checkbox(lab, bool(e.get(f)), key=key)
                elif f in ('start', 'end'):
                    if f == 'end' and ss.get(f'e_{kind}_{e["id"]}_cur', e.get('cur')):
                        e['end'] = ''
                        continue
                    e[f] = month_picker(lab, e.get(f, ''), key)
                elif f == 'pts':
                    tin(e, f, lab, key, area=True, height=110)
                else:
                    tin(e, f, lab, key)
            if st.button('Remove', key=f'rm_{kind}_{e["id"]}'):
                items.pop(i)
                st.rerun()
    if st.button(f'+ Add {title.lower()}', key=f'add_{kind}'):
        items.append(blank(kind))
        st.rerun()


def skills_editor():
    st.caption('Type a skill and press Enter to add it. Pick from the list or add your own. Group name is optional (e.g. Languages).')
    groups = ss.prof['skill_groups']
    for i, g in enumerate(groups):
        with st.container(border=True):
            g['cat'] = st.text_input('Group name (optional)', g['cat'], key=f'e_sk_{g["id"]}_cat')
            opts = list(dict.fromkeys(g['items'] + SUGGEST))
            g['items'] = st.multiselect('Skills', opts, g['items'], accept_new_options=True, key=f'e_sk_{g["id"]}_items')
            if len(groups) > 1 and st.button('Remove group', key=f'rm_sk_{g["id"]}'):
                groups.pop(i)
                st.rerun()
    if st.button('+ Add skill group', key='add_sk'):
        groups.append({'id': uuid.uuid4().hex[:8], 'cat': '', 'items': []})
        st.rerun()


def page_profile():
    P = ss.prof['p']
    pct, miss = completeness(ss.prof)
    st.progress(pct / 100, text=f'Profile {pct}% complete')
    if miss:
        st.caption('Still missing: ' + ', '.join(miss))
    up = st.file_uploader('Import profile (JSON)', type='json')
    if up and ss.get('imported') != (up.name, up.size):
        try:
            ss.prof = normalize(json.load(up))
            ss.imported = (up.name, up.size)
            for k in [k for k in ss if k.startswith(('p_', 'e_'))]:
                del ss[k]
            st.rerun()
        except ValueError:
            st.error('That file is not valid JSON.')
    with st.expander('Contact', expanded=True):
        a, b, c = st.columns(3)
        tin(P, 'first', 'First name', 'p_first')
        tin(P, 'mid', 'Middle name', 'p_mid')
        tin(P, 'last', 'Last name', 'p_last')
        tin(P, 'title', 'Headline', 'p_title', placeholder='Data Scientist | AIML Engineer')
        for f, lab in [('email', 'Email'), ('phone', 'Phone'), ('loc', 'Location'), ('linkedin', 'LinkedIn'), ('github', 'GitHub'), ('portfolio', 'Portfolio / Kaggle / LeetCode')]:
            tin(P, f, lab, f'p_{f}')
    with st.expander('Summary'):
        tin(P, 'summary', 'Summary (60-80 words works best)', 'p_summary', area=True, height=170)
    st.markdown('**Skills**')
    skills_editor()
    for k in KINDS:
        st.markdown(f'**{KINDS[k][0]}**')
        editor(k)
    with st.expander('Achievements and preferences'):
        tin(P, 'ach', 'Achievements (one per line)', 'p_ach', area=True)
        tin(P, 'pref_loc', 'Preferred work location (never printed on the resume)', 'p_pref_loc')


# ---------- JD ----------
def go_resume():
    ss.nav = 'Resume'


def page_jd():
    j = ss.job
    j['jd'] = st.text_area('Job description', j['jd'], height=240, placeholder='Paste the full JD here...')
    a, b = st.columns(2)
    j['title'] = a.text_input('Job title', j['title'])
    j['company'] = b.text_input('Company', j['company'])
    j['source'] = st.selectbox('Job source', SOURCES, SOURCES.index(j['source']))
    st.button('Generate resume', type='primary', on_click=go_resume, width='stretch')


# ---------- review (AI) ----------
def limit_seconds():
    lim = ss.limit
    if lim is None:
        return None
    if lim['until'] is None:
        return -1
    left = (lim['until'] - dt.datetime.now(IST)).total_seconds()
    if left <= 0:
        ss.limit = None
        return None
    return left


def run_ai():
    j = ss.job
    if used() >= daily_limit():
        ss.limit = {'until': dt.datetime.now(IST) + dt.timedelta(seconds=ai.seconds_to_midnight())}
        return
    try:
        sug = ai.suggest(ss.prof, j['jd'], j['title'] or ss.prof['p'].get('title', ''), secrets())
        store().inc_usage(ss.user, today())
        ss.used += 1
        orig = {u['id']: u['text'] for u in ai.units(ss.prof)}
        ss.sug = {k: {'t': v, 'prev': orig[k], 'applied': False} for k, v in sug.items()}
        ss.limit, ss.msg = None, ('ok', f'{len(sug)} suggestions ready.' if sug else 'Nothing to change. Your bullets already look good.')
    except ai.AILimit as e:
        ss.limit = {'until': dt.datetime.now(IST) + dt.timedelta(seconds=e.seconds) if e.seconds else None}
    except Exception as e:
        ss.msg = ('err', f'AI is not available right now. {e}')


def apply_sug(uid, undo=False):
    s = ss.sug[uid]
    ai.set_unit(ss.prof, uid, s['prev'] if undo else s['t'])
    s['applied'] = not undo
    for k in [k for k in ss if k.startswith('e_')]:
        del ss[k]


def page_review():
    if not ss.job['jd'].strip():
        st.info('Paste a JD in the JD tab first.')
        return
    left = limit_seconds()
    if left is not None:
        st.warning(f"**AI suggestions are paused**\n\n{ai.limit_message(left if left > 0 else None)}", icon='⏳')
        if left > 0 and ss.limit and used() >= daily_limit():
            st.progress(max(0.0, min(1.0, 1 - left / 86400)), text=f'Limit resets in {int(left // 3600)}h {int(left % 3600 // 60)}m')
        with st.container(border=True):
            st.caption('Still working right now')
            st.markdown('✅ Resume generation and templates  \n✅ ATS score and missing keywords  \n✅ PDF download and history')
    st.button('Get AI suggestions' if left is None else 'Try AI again', type='primary' if left is None else 'secondary', on_click=run_ai, width='stretch')
    if ss.msg:
        getattr(st, {'ok': 'success', 'err': 'error'}[ss.msg[0]])(ss.msg[1])
    st.caption('Left: your current text. Right: AI suggestion. Suggestions with skills or numbers not in your profile are blocked.')
    for u in ai.units(ss.prof):
        s = ss.sug.get(u['id'])
        if not s:
            continue
        with st.container(border=True):
            st.markdown(f"**{u['label']}**")
            a, b = st.columns(2)
            a.caption('Actual')
            a.write(u['text'])
            b.caption('AI suggestion')
            b.write(s['t'])
            bad = [] if s['applied'] else ai.flags(ss.prof, u['text'], s['t'])
            if bad:
                st.error('Not in your profile: ' + ', '.join(bad))
            if s['applied']:
                st.button('Undo', key=f"un_{u['id']}", on_click=apply_sug, args=(u['id'], True))
            else:
                st.button('Apply', key=f"ap_{u['id']}", type='primary', disabled=bool(bad), on_click=apply_sug, args=(u['id'],))


# ---------- resume ----------
def preview(pdf):
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        pix = pymupdf.open(stream=pdf, filetype='pdf')[0].get_pixmap(dpi=110)
        st.image(pix.tobytes('png'), width='stretch')
    except Exception:
        st.caption('Preview needs PyMuPDF. The PDF download still works.')


def page_resume():
    j, prof = ss.job, ss.prof
    if not j['jd'].strip():
        st.info('Paste a JD in the JD tab to tailor the resume. Showing your base resume.')
    left, right = st.columns([5, 6], gap='large')
    with left:
        c1, c2 = st.columns(2)
        tp = c1.selectbox('Template', ['classic', 'modern', 'compact'], format_func=str.title)
        safe = c2.toggle('Single-line dates', False, help='Extra ATS-safe: date and location go on the college / company line.')
        A = core.ats(prof, j['jd'])
        F = core.fit_one_page(core.build_model(prof, j['jd'], safe), tp)
        st.markdown(ring(A['total']) if A['kws'] else '<div class="ringbox"><div><b>ATS score</b><small>Paste a JD to see it</small></div></div>', unsafe_allow_html=True)
        st.markdown(stats([('Keywords matched', f"{len(A['matched'])} of {len(A['kws'])}"), ('Length', '1 page' if not F['over'] else 'Over 1 page'),
                           ('Font', f"{F['z']:.1f} pt"), ('Dates', 'Single line' if safe else 'Right-aligned')]), unsafe_allow_html=True)
        name = (core.full_name(prof['p']) or 'Resume').replace(' ', '_')
        d1, d2 = st.columns(2)
        d1.download_button('⬇ Download PDF', F['pdf'], f'{name}_Resume.pdf', 'application/pdf', type='primary', width='stretch')
        if d2.button('Save to history', width='stretch'):
            store().add_history(ss.user, {'title': j['title'] or prof['p'].get('title') or 'Untitled', 'company': j['company'], 'source': j['source'],
                                          'status': 'Applied', 'score': A['total'], 'text': core.model_text(F['model']),
                                          'created_at': dt.datetime.now(IST).isoformat()})
            st.toast('Saved to history')
        if A['kws']:
            with st.container(border=True):
                st.caption('Matched')
                st.markdown(' '.join(f':green-badge[{k}]' for k in A['matched']) or '-')
                st.caption('Missing (add only skills you really have)')
                st.markdown(' '.join(f':red-badge[{k}]' for k in A['missing']) or 'None')
        if F['over']:
            st.warning('Still more than one page. Shorten your summary or remove content.')
        if F['trimmed']:
            with st.expander(f"{len(F['trimmed'])} bullets removed to fit one page"):
                for t in F['trimmed']:
                    st.write('- ' + t)
        if F['model']['hidden']:
            st.caption('Hidden projects (less relevant to this JD): ' + ', '.join(F['model']['hidden']))
        with st.expander('How is this score calculated?'):
            kw_pts = round(70 * len(A['matched']) / len(A['kws'])) if A['kws'] else 0
            st.write(f"**Keywords {kw_pts} / 70**: {len(A['matched'])} of {len(A['kws'])} JD keywords are in your resume.  \n"
                     f"**Format {A['fmt']} / 30**: email 5, phone 5, summary 5, skills 5, education 4, experience or projects 3, profile link 3.")
            st.caption('This is an estimate based on about 150 common skill keywords. A skill outside that list (for example a rare tool) is not counted. '
                       'Real company ATS tools score differently, so use this to compare versions of your own resume.')
        with st.expander('ATS parse test: what a bot reads'):
            try:
                checks, raw = core.parse_check(F['pdf'], F['model'])
                for label, ok, detail in checks:
                    st.write(('✅ ' if ok else '❌ ') + label + (f' ({detail})' if detail else ''))
                st.caption('Text extracted from the PDF:')
                st.code(raw, language=None)
            except Exception as e:
                st.caption(f'Parse test needs PyMuPDF. {e}')
        with st.expander('Quality check'):
            warns = core.quality(F['model']) + A['tips']
            for w in warns:
                st.write('- ' + w)
            if not warns:
                st.success('Clean.')
    with right:
        st.caption('Preview: this is exactly what the PDF contains')
        preview(F['pdf'])


# ---------- history ----------
def set_status(rid, key):
    store().update_status(ss.user, rid, ss[key])


def page_history():
    rows = store().list_history(ss.user)
    if not rows:
        st.info('Nothing saved yet. Use "Save to history" on the Resume tab.')
        return
    scores = [r['score'] for r in rows]
    a, b, c = st.columns(3)
    a.metric('Resumes', len(rows))
    b.metric('Average ATS', round(sum(scores) / len(scores)))
    c.metric('Best ATS', max(scores))
    st.caption('By source')
    st.bar_chart({s: sum(1 for r in rows if r['source'] == s) for s in SOURCES})
    st.caption(' · '.join(f"{s} {sum(1 for r in rows if r['status'] == s)}" for s in STATUSES))
    for r in rows:
        with st.expander(f"{BADGE.get(r['status'], '')} {r['title']}{' @ ' + r['company'] if r.get('company') else ''} · {r['source']} · ATS {r['score']}"):
            key = f"st_{r['id']}"
            st.selectbox('Status', STATUSES, STATUSES.index(r['status']), key=key, on_change=set_status, args=(r['id'], key))
            st.code(r['text'], language=None)
            if st.button('Delete', key=f"del_{r['id']}"):
                store().delete_history(ss.user, r['id'])
                st.rerun()


# ---------- main ----------
if 'user' not in ss:
    login()
if 'prof' not in ss:
    try:
        init_session()
    except Exception as e:
        st.error(f'Could not load your profile from the database. {e}')
        st.caption('Check: tables exist in Supabase (schema.sql), SUPABASE_URL and SUPABASE_KEY in Secrets.')
        st.stop()

st.markdown(f'''<div class="hero"><div><b>📄 ATS Resume Builder</b><span>Paste a JD. Get an ATS-friendly one-page resume.</span></div>
<div class="pill">✨ AI {used()} of {daily_limit()} today</div></div>''', unsafe_allow_html=True)
nav_col, out_col = st.columns([5, 1], vertical_alignment='center')
sync_skills(ss.prof)
with nav_col:
    page = st.segmented_control('Navigation', list(ICONS), default='Resume', key='nav', format_func=lambda x: f'{ICONS[x]} {x}', label_visibility='collapsed') or 'Resume'
out_col.button('Sign out', on_click=sign_out, icon=':material/logout:', width='stretch', key='signout_top')
{'Profile': page_profile, 'JD': page_jd, 'Review': page_review, 'Resume': page_resume, 'History': page_history}[page]()

snap = json.dumps(ss.prof, sort_keys=True)
if snap != ss.saved:  # autosave on any change
    store().save_profile(ss.user, ss.prof)
    ss.saved = snap
    if page == 'Profile':
        ss.sug = {}
with st.sidebar:
    st.caption(f'Signed in as {ss.user}')
    st.progress(min(1.0, used() / max(daily_limit(), 1)), text=f'AI today: {used()} of {daily_limit()}')
    st.button('Sign out', on_click=sign_out, key='signout_side')
