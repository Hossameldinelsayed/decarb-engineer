# Hosting the AI Decarbonization Engineer

The app is designed to be hosted **inside the corporate network** — no external
site, no public link (corporate security blocks those). It runs fully offline
(no API key); live-LLM mode is optional.

## Public URL via Google Cloud Run (works on most corporate networks)

Cloud Run serves the container under `https://<name>.run.app` — a Google domain
that corporate web filters almost always allow (unlike `streamlit.app`). It
supports custom domains and automatic HTTPS, and the Dockerfile already listens
on Cloud Run's `$PORT`.

Run these from a machine with internet (your personal laptop, or Google
**Cloud Shell** in the browser at https://shell.cloud.google.com — which avoids
the corporate proxy entirely):

```bash
# 1. Install the gcloud CLI (skip if using Cloud Shell): https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>     # create one at console.cloud.google.com (billing on; free tier covers a demo)

# 2. Deploy straight from the source folder (Cloud Build builds the Dockerfile)
cd decarb-engineer
gcloud run deploy decarb-engineer \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --memory 1Gi
```

`gcloud` will offer to enable the needed APIs (Cloud Run, Cloud Build, Artifact
Registry) — accept. After ~2 min it prints a **Service URL** like
`https://decarb-engineer-abc123-ew.a.run.app`. Share that link.

- `--allow-unauthenticated` makes it open to anyone with the URL (good for a demo).
  To restrict to signed-in Google accounts, drop that flag.
- To deploy from the GitHub repo instead, in Cloud Shell:
  `git clone https://github.com/Hossameldinelsayed/decarb-engineer && cd decarb-engineer` then run the same `gcloud run deploy`.
- Optional custom domain: Cloud Run console -> the service -> **Manage custom domains**.
- Optional live LLM: `gcloud run deploy ... --set-env-vars ANTHROPIC_API_KEY=sk-...`

## Option A (recommended): Docker, hosted internally

Build once on a machine that can reach PyPI (or a corporate PyPI mirror); then
the image runs anywhere on the internal network with no outside dependency.

```bash
cd decarb-engineer
docker build -t decarb-engineer .
docker run -d -p 8501:8501 --name decarb-engineer decarb-engineer
```

Or with Compose:

```bash
docker compose up -d
```

Then open:
- on the host:        `http://localhost:8501`
- for colleagues:     `http://<server-hostname-or-ip>:8501`  (same LAN/VPN)

Because this is plain internal HTTP/LAN traffic, it does **not** go through the
external web-filtering proxy that shows "your connection is not private".

**Behind a corporate proxy at build time?** Pass the proxy to the build only:

```bash
docker build --build-arg HTTP_PROXY=$HTTP_PROXY --build-arg HTTPS_PROXY=$HTTPS_PROXY -t decarb-engineer .
```

(or point pip at your internal mirror). Once built, running needs no internet.

## Option B: plain Python on an internal machine (no Docker)

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows (use py -3.11 if needed)
pip install -r requirements.txt
streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

Share `http://<machine-ip>:8501` with colleagues on the network.

## Option C: external (Streamlit Community Cloud) — only if IT allows

Gives a public `https://<name>.streamlit.app` link, but most corporate networks
block `streamlit.app`. If you want it, ask IT to allowlist:

```
share.streamlit.io
*.streamlit.app
*.streamlitusercontent.com
```

then deploy from the GitHub repo (`main`, file `app/streamlit_app.py`).

## Live LLM agents (optional, any option)

Set `ANTHROPIC_API_KEY` in the container/host environment (or Streamlit secrets).
Without it the app uses deterministic offline proposals and still runs end to end.

## Notes
- `requirements.txt` is the install manifest; `.streamlit/config.toml` carries the
  Schneider theme; `data/schneider_solutions.json` is the editable solution catalog.
- Default port 8501; change with `--server.port` or the Compose `ports` mapping.
