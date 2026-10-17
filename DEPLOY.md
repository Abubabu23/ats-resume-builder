# Deploy guide (all free)

You need: a GitHub account, a Supabase account, a Groq account, a Streamlit Community Cloud account (sign in with GitHub).

## 1. Put the code on GitHub (private)
1. github.com > New repository > name `ats-resume-builder` > **Private** > Create.
2. Unzip `resume_app.zip` on your computer.
3. On the new repo page click "uploading an existing file", drag everything INSIDE the `resume_app` folder
   (app.py, core.py, ai.py, store.py, requirements.txt, schema.sql, README.md, DEPLOY.md, tests, .streamlit/config.toml)
   and Commit.
4. Do NOT upload `abu_profile.json` or any real secrets.

## 2. Create the database (Supabase)
1. supabase.com > New project (pick a region close to you, e.g. Mumbai) and set a database password.
2. Left menu > SQL Editor > New query > paste all of `schema.sql` > Run. You should see "Success".
3. Left menu > Project Settings > API. Copy: **Project URL** and the **service_role** key (click Reveal).
   The service_role key is secret. Never put it in GitHub.

## 3. Get the AI key (Groq)
1. console.groq.com > API Keys > Create API key. Copy it (starts with `gsk_`).
2. Optional backup: aistudio.google.com > Get API key (Gemini).

## 4. Deploy on Streamlit Community Cloud
1. share.streamlit.io > sign in with GitHub > Create app > "Deploy a public app from GitHub".
2. Repository: your repo. Branch: main. Main file path: `app.py`.
3. Click **Advanced settings** > Python 3.12 > **Secrets**, paste this and fill your values:

```
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "your-service-role-key"
GROQ_API_KEY = "gsk_xxx"
GEMINI_API_KEY = "optional"
AI_DAILY_LIMIT = 20

[users]
abu = "a-strong-password"
```
4. Click Deploy. First build takes 2 to 4 minutes.

## 5. First use
1. Open the app URL, sign in with the username and password from `[users]`.
2. Profile tab > Import profile (JSON) > upload `abu_profile.json`. Your data is saved to Supabase automatically.
3. JD tab > paste a JD > Generate resume > Download PDF.

## Troubleshooting
- "No users configured": the `[users]` table is missing in Secrets.
- Profile does not save / History empty: check SUPABASE_URL and SUPABASE_KEY, and that `schema.sql` ran.
- AI says paused: free limit reached. It resets (daily cap at midnight IST, provider limits vary).
- App asleep after some days of no use: open the URL and click "Wake up".
- Change a password or key: Streamlit Cloud > your app > Settings > Secrets, then Save (app restarts).
