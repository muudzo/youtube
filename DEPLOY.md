# Deploying the Autopilot (auto-upload, no local storage)

This sets the channel up to run **fully unattended** on this Mac: it produces
videos continuously, uploads them to YouTube, and **deletes every local file
after each confirmed upload** so nothing piles up on disk.

## How it works

```
launchd (com.youtube.autopilot)
   └─ cron/run_autopilot.sh         # portable: finds repo + venv on its own
        └─ .venv/bin/python autopilot.py --daemon
             └─ loop:
                 ├─ produce 1 video + 1 Short  (pipeline.py)
                 ├─ upload both to YouTube
                 ├─ DELETE local render, audio, subs, thumbnail, footage
                 └─ repeat until the daily API quota is spent, then sleep to reset
```

- **Delete-after-upload** lives in [scripts/cleanup.py](scripts/cleanup.py) and
  only runs after a *confirmed* upload. A failed upload keeps its files so it can
  be retried. Override per-run with `--keep-local`.
- **"As many videos as possible"** is capped by YouTube's Data API quota, not by
  us. Default quota is **10,000 units/day**; each upload costs **1,600 units**, so
  realistically **~3 video+Short pairs/day**. The daemon tracks spend and sleeps
  until the quota resets (00:00 US/Pacific) once it's exhausted. To go higher,
  request a quota increase in Google Cloud Console and raise
  `DAILY_UPLOAD_UNIT_BUDGET` in [config.py](config.py).

## One-time setup

```bash
./setup.sh
```

This installs ffmpeg, builds `.venv`, installs deps, creates output dirs, and
installs the launchd agents (it does **not** start them yet).

Then complete the three manual steps below.

### 1. API keys

```bash
cp .env.example .env
```

Edit `.env` and add (both free):
- `GROQ_API_KEY` — https://console.groq.com/keys (script generation)
- `PEXELS_API_KEY` — https://www.pexels.com/api/ (stock footage)
- `GEMINI_API_KEY` — optional fallback

### 2. Google OAuth credentials (`client_secret.json`)

1. https://console.cloud.google.com → create/select a project
2. Enable **YouTube Data API v3** (APIs & Services → Library)
3. APIs & Services → **Credentials** → Create Credentials → **OAuth client ID**
4. Application type: **Desktop app**
5. Download the JSON, rename to `client_secret.json`, place in the repo root
6. On the OAuth consent screen, add your Google account as a **Test user**
   (otherwise login is blocked while the app is in "testing").

### 3. First login (one time, needs a browser)

```bash
.venv/bin/python -c "from scripts.youtube_uploader import get_authenticated_service; get_authenticated_service()"
```

A browser opens; approve access. This writes `token.json` (auto-refreshing), so
the daemon never needs the browser again.

## Start / stop

```bash
./manage.sh start      # launch the daemon + nightly cleanup
./manage.sh status     # see if they're running
./manage.sh logs       # tail the live log
./manage.sh stop       # stop everything
./manage.sh restart
```

The daemon auto-starts at login and restarts itself if it crashes (launchd
`KeepAlive`).

## Verify it's working

```bash
# Generate one video locally WITHOUT uploading or deleting (safe smoke test):
.venv/bin/python pipeline.py "The Dyatlov Pass Incident" --no-upload --keep-local

# Produce + upload one, then auto-delete locally:
.venv/bin/python autopilot.py --videos 1
```

Watch disk usage stay flat: `du -sh output assets/stock_footage`.

## Notes / gotchas

- **macOS Full Disk Access**: if launchd jobs can't read files, grant Full Disk
  Access to `/bin/zsh` (System Settings → Privacy & Security).
- **Sleep**: a sleeping Mac won't render. Plug in and set
  *Prevent automatic sleeping on power adapter* (or run `caffeinate`).
- **New-channel limits**: brand-new channels are capped at low daily upload
  counts and can't set custom thumbnails until verified — expect YouTube to
  throttle before the API quota does at first.
