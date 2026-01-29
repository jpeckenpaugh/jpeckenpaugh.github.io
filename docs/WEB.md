# Lokarta Web Demo (Pyodide)

## Local Test
1. From the repo root, start a static server:

```bash
python3 -m http.server 8000
```

2. Open the web demo:

```text
http://localhost:8000/docs/
```

Note: do not use a file:// URL. The browser will block asset loading.

## GCS Static Hosting Notes
- Upload the repo contents (including `web/`) to a public bucket.
- Set `web/index.html` as the website entry point (or point to `/web/` in links).
- Ensure all files are world-readable.
- If hosting the site on a different domain, enable CORS for the bucket.
- Consider long cache headers for `web/asset-manifest.json` and static assets.
