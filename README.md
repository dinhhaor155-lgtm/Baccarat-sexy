# Baccarat Sexy API

Small Flask API wrapper for Baccarat table data. It proxies the upstream Baccarat result endpoint and filters the response to AE tables only.

## Endpoints

- `/` health/info response
- `/status` local app status
- `/api` upstream JSON filtered to AE tables
- `/pretty` formatted AE-only JSON
- `/roads` computed Baccarat derived roads for AE tables

## Deploy on Railway

Railway can deploy this repository directly as a Python app. The included `Procfile` starts the service with Gunicorn and binds to Railway's `$PORT`.

Set these Railway variables from your current browser/session before deploying:

- `AIBCR_CSRF_TOKEN`
- `AIBCR_XSRF_TOKEN`
- `AIBCR_LARAVEL_SESSION`

## Run locally

```bash
pip install -r requirements.txt
python bcr.py
```
