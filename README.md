# ATS Resume Builder (Streamlit)

Paste a job description and get an ATS-friendly, one-page resume plus an ATS score.

**Features:** login, profile saved in Supabase, JD keyword match + ATS score, top-3 relevant projects (max 3 bullets each),
ATS-safe layout, 3 templates, one-page auto-fit text PDF, AI bullet suggestions with Apply/Undo (Groq, Gemini fallback),
history + status dashboard, friendly message when the free AI limit is finished.

**Privacy:** email, phone and links are masked before any text goes to the AI. Suggestions that add skills or numbers
not already in your profile are blocked.

## Deploy (free)
1. Push this folder to a **private** GitHub repo. Never commit `.streamlit/secrets.toml` or your profile JSON.
2. Supabase: create a project, open SQL Editor, run `schema.sql`. Copy the project URL and the `service_role` key.
3. Get a Groq API key (and optionally a Gemini key).
4. share.streamlit.io: New app, pick the repo, main file `app.py`. In Advanced settings > Secrets paste
   the values from `.streamlit/secrets.toml.example` (set your own password under `[users]`).
5. Open the app, sign in, go to Profile and upload `abu_profile.json` (Import profile). Full guide: DEPLOY.md

## Run locally
```
pip install -r requirements.txt
APP_DEV=1 streamlit run app.py     # dev login: dev / dev, data saved in ./data
python -m pytest tests
```
