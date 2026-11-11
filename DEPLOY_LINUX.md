# Ubuntu VM deployment

This is the Linux counterpart to DEPLOY.md / DEPLOY_NL.md. macOS launchd remains supported. Ubuntu uses systemd and native FFmpeg; no Apple hardware encoder or proprietary Mac fonts are required.

## Installed target

- VM: `youtube-worker`, `192.168.2.31`, Ubuntu 24.04, 2 vCPU, approximately 8 GiB RAM.
- Service account: `uploader`.
- Pipeline: `/srv/youtube/pipeline`.
- Existing clip worker: `/opt/youtube-worker`, still independent.
- English unit: `youtube-autopilot@en.service`, enabled for boot.
- Dutch unit: `youtube-autopilot@nl.service`, opt-in; separate channel token.

VM defaults are 1280×720 landscape, 720×1280 Shorts, two encoder threads and the fast x264 preset. Both production channels share the existing render lock and a systemd slice limited to 180% CPU and 5 GiB memory, reserving room for the OS and clip worker. A memory cap can terminate an oversized render; it does not guarantee arbitrary long videos fit. Test a full episode before increasing dimensions or enabling both channels.

## Installation / updates

Run as the intended service user with sudo, from a runtime checkout under `/srv` or `/opt`:

```bash
cd /srv/youtube/pipeline
bash setup.sh
```

This installs dependencies and fonts, creates an isolated `.venv`, writes the resolved dependency list to `output/linux-requirements.lock`, installs systemd units, and enables English for boot. It does not start publishing or enable Dutch. Existing `.env` files are preserved. Only install trusted code: setup needs apt/systemd sudo access.

The deployed runtime was copied from the source checkout without `.git`, secrets, rendered files, or the Mac's tracked `output/` state. For updates, transfer source while excluding `.env`, `client_secret.json`, `token*.json`, `.venv`, `.git`, and `output`. Do not overwrite live state or credentials. Stop the appropriate production unit before updating; retain wanted media first.

The Mac remains usable separately, but do not run two publishing instances for the same channel. Before starting this VM's publishing, stop that channel on the Mac and securely migrate its current `output/autopilot_state.json`, `output/nl_autopilot_state.json`, and `output/series_*_state.json` where present. The series publisher also performs channel lookups to reconcile previously published numbered titles. A fresh checkout is not a reliable substitute for the Mac's current runtime state.

## Credentials — pending

The user is creating new API keys. Edit credentials on the VM, not in chat:

```bash
ssh -i ~/.ssh/zim_pipeline_ed25519 uploader@192.168.2.31
cd /srv/youtube/pipeline
nano .env
chmod 600 .env
```

Set `GROQ_API_KEY` and `PEXELS_API_KEY`; Gemini is optional. Confirm the configured Groq model is available to the new account. `SCRIPT_MODEL` can be overridden in `.env`; do not set it to an empty string. A successful local preflight does not validate API quotas, account access, model availability or YouTube permissions.

Place the Google Desktop OAuth client file at `/srv/youtube/pipeline/client_secret.json`, mode 600. From a computer with an authorised SSH key and browser, forward the callback:

```bash
ssh -i ~/.ssh/zim_pipeline_ed25519 -L 8080:127.0.0.1:8080 uploader@192.168.2.31
cd /srv/youtube/pipeline
.venv/bin/python autopilot.py --auth
```

Open the printed Google URL in that computer's browser. Authenticate the intended English channel; the result is `token.json`. For Dutch, run `.venv/bin/python brainrot.py auth` separately; it writes `token_nl.json`. Never copy one channel's token over the other. Do not expose callback port 8080 to the network or commit tokens. Authorisation is a user action; it has not been completed by the deployment.

## Checks before publishing

```bash
cd /srv/youtube/pipeline
.venv/bin/python linux/preflight.py --render-only
.venv/bin/python -m pytest -q
.venv/bin/python linux/smoke.py
bash manage.sh check
```

`smoke.py` generates test footage and a tone, renders a three-second landscape and Short using the real render functions, and renders all four thumbnail typefaces. It checks H.264/AAC, dimensions and duration. Outputs are in `output/linux-smoke/`. This validates local rendering, not cloud calls or the memory requirements of a ten-minute episode.

After keys are installed, test one full episode with no uploads:

```bash
.venv/bin/python autopilot.py --series --no-upload --keep-local
```

To test an actual upload privately with a chosen topic, retaining files:

```bash
.venv/bin/python pipeline.py 'Your reviewed topic' --upload --privacy private --keep-local
```

Confirm the destination channel and result in YouTube Studio. Then start ongoing English publishing:

```bash
bash manage.sh start
bash manage.sh logs
```

**The production daemons retain the existing public-upload behaviour.** Private testing does not make daemon uploads private. No production unit was started with real credentials during the migration.

Services check keys, token structure, file permissions, fonts, dependencies and free disk before starting. Missing credentials cause a clean skipped start, not a repeated rendering failure. Installing credentials does not start the service automatically: run `bash manage.sh start` after verification.

## Operations

### CPU-only illustrated story demo

```bash
.venv/bin/python scripts/illustrated_demo.py
```

Creates an original fictional 30-second paper-cut story, `output/illustrated_demo/the-waiting-light.mp4`, plus a six-panel storyboard and technical metadata. Artwork, layered motion, camera movement, captions, and ambient music are rendered locally. Narration uses the free Edge speech endpoint and needs internet, but no API key. This demonstrates illustrated animation, not diffusion-generated character animation. It never uploads or changes channel progress. Cached scene narration can be reused on subsequent renders.

## Service commands

```bash
bash manage.sh status
bash manage.sh stop
bash manage.sh restart
bash manage.sh check nl
bash manage.sh start nl
sudo systemctl enable youtube-autopilot@nl.service  # optional Dutch boot start
sudo journalctl -u youtube-autopilot@en.service -n 50 --no-pager
systemctl status youtube-pipeline.slice
df -h /srv/youtube
```

Linux does not install the Mac's age-based cleanup job, which can delete failed renders. `KEEP_LOCAL_AFTER_UPLOAD=true` is the VM default so migration outputs can be reviewed. Change it deliberately after successful verification if you want the pipeline's confirmed-upload cleanup. Retained files will accumulate; new series renders wait when free disk falls below 5 GiB. Back up state and credentials privately; do not delete state to free disk space.
