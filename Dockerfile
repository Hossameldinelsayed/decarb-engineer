# AI Decarbonization Engineer - self-contained image for INTERNAL hosting.
# Build once on a machine with PyPI access (or an internal mirror); the image
# then runs anywhere on the corporate network with no external dependency.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Install deps first for better layer caching. The UI needs streamlit + plotly;
# pydantic is the engine; anthropic is optional (only for --live agents).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Listen on $PORT so this works on Google Cloud Run (it injects PORT, default
# 8080) AND locally (defaults to 8501). exec keeps streamlit as PID 1 for signals.
ENV PORT=8501
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8501'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/_stcore/health').status==200 else 1)"

CMD ["sh", "-c", "exec streamlit run app/streamlit_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
