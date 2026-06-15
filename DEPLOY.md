# Deploying the AI Decarbonization Engineer to a public link

The app is built to run on **Streamlit Community Cloud** (free, gives a public
`https://<name>.streamlit.app` URL anyone can open). It runs fully offline (no
API key); the live-LLM mode is optional.

## 1. Put the code on GitHub (one time)

The GitHub CLI is installed. From the project folder:

```bat
cd C:\Users\Hossa\Documents\decarb-engineer
gh auth login                 :: sign in once (browser); choose HTTPS
gh repo create decarb-engineer --public --source . --remote origin --push
```

(Or, without the CLI: create an empty repo on github.com, then
`git remote add origin <url>` and `git push -u origin main`.)

> The repository will be **public** so it can be deployed and shared. No secrets
> are committed (`.env` is git-ignored; the app needs no API key to run).

## 2. Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with the same GitHub account.
2. **Create app -> Deploy a public app from GitHub**.
3. Set:
   - **Repository:** `<your-user>/decarb-engineer`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`
4. **Deploy**. After the build you get a public URL to share with anyone.

Pre-filled deploy link (after the repo exists, replace `<your-user>`):

```
https://share.streamlit.io/deploy?repository=<your-user>/decarb-engineer&branch=main&mainModule=app/streamlit_app.py
```

## 3. (Optional) enable live LLM agents on the hosted app

In the Streamlit Cloud app: **Settings -> Secrets**, add:

```
ANTHROPIC_API_KEY = "sk-..."
```

Without it, the app uses the deterministic offline proposals (the demo still runs
end to end).

## Notes
- `requirements.txt` (repo root) is what Streamlit Cloud installs.
- `.streamlit/config.toml` carries the Schneider theme.
- Python 3.11+ (Streamlit Cloud default is fine).
