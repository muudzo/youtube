# Nederlands kanaal — runbook

The Dutch channel is a **separate production surface** from the English
dark-history autopilot. Different channel, different OAuth token, different
daemon, different cadence. Nothing here changes the English pipeline.

## Why Dutch, and where the money actually is

| | Number | Consequence |
|---|---|---|
| NL CPM | ~$5.50 | Solid, and most Dutch creators publish in English — the lane is underserved |
| NL long-form RPM | ~$2.80–4.50 / 1k | Real revenue, but only past 8 minutes where mid-rolls unlock |
| Shorts RPM | $0.02–0.12 / 1k | ~Nothing. 10M views ≈ $200–1,200 |

So: **long-form earns, Shorts feed it.** The pipeline targets 9 minutes
(`NL_TARGET_VIDEO_LENGTH_MINUTES`) to stay clear of the 8-minute mid-roll
threshold, and warns at render time if a video lands under it.

Monetisation still requires the YPP threshold: 1,000 subscribers plus either
4,000 public watch hours or 10M Shorts views in 90 days. Nothing here shortcuts
that.

## The policy constraint that shaped the build

YouTube's inauthentic-content policy (renamed July 2025, expanded July 2026)
demonetises content that is generic, repetitive or template-based and
reproduced at scale. Reported enforcement keys on a fingerprint: one synthetic
narrator, one thumbnail template, stock-footage loops, superhuman upload pace.
Three strikes — warning, 90-day suspension, permanent YPP removal.

The English autopilot matches that fingerprint almost exactly. This pipeline
deliberately does not:

| Risk | Mitigation | Where |
|---|---|---|
| One synthetic narrator | 5 Dutch voices, rotated per video; Short gets a contrasting voice | `scripts/nl/voices.py` |
| One template | Hook shape, structure, captions, cut rhythm, thumbnail all rotate per video | `scripts/nl/variation.py` |
| No original value | Every script must commit to an `eigen_invalshoek` — an arguable thesis | `scripts/nl/script_generator.py` |
| Superhuman pace | 2 uploads/day max, ≥5h apart, jittered, aimed at Dutch evening peak | `scripts/nl/cadence.py` |
| Undisclosed AI | `status.containsSyntheticMedia` on upload + a Dutch disclosure line in every description | `scripts/nl/seo.py`, uploader |
| Sensitive topics | Health, finance, identity, tragedy and party politics blocked before production | `scripts/nl/safety.py` |

These are real mitigations, not a guarantee. Discovery mines raw search demand
and will surface topics you would not choose; the safety gate is a floor, and
what it lets through is still your editorial call.

## Setup

Two gates have waiting periods, so start them first.

### 1. Create the channel and phone-verify it (do this first — up to 3 days)

Create the new channel at <https://www.youtube.com/channel_switcher>, then
verify it at <https://www.youtube.com/verify>.

Custom thumbnails are locked until the channel is phone-verified, and this
pipeline uploads a thumbnail with every video. Verification perks can take up
to **3 business days** to activate. Note Google allows only **two YouTube
accounts per phone number per year** — the existing English channel may already
have consumed one.

Check status at Settings → Channel status and features.

### 2. API keys

```bash
cp .env.example .env
```

- `GROQ_API_KEY` — <https://console.groq.com/keys>
- `PEXELS_API_KEY` — <https://www.pexels.com/api/>

### 3. Google OAuth — publish the app, do NOT leave it in Testing

At <https://console.cloud.google.com>: enable **YouTube Data API v3**, then
create an **OAuth client ID** of type **Desktop app** and save the JSON as
`client_secret.json` in the repo root.

Then, on the OAuth consent screen, set **Publishing status → In production**.

This step is not optional for an unattended daemon. While publishing status is
"Testing", Google revokes the refresh token after **7 days**, so the daemon
stops uploading roughly weekly with an `invalid_grant` error. In production the
refresh token persists. You will see a "Google hasn't verified this app"
warning at consent — click *Advanced → Go to … (unsafe)*. That is expected for
a personal, unverified app and does not affect uploads.

`client_secret.json` is shared between both channels — it identifies the *app*,
not the channel. Only the token differs.

### 4. Authorise the Dutch channel specifically

The Dutch channel needs its **own** OAuth token. One token authorises one
channel — without a separate token the daemon publishes onto the English
channel.

```bash
./setup.sh                       # installs the com.youtube.brainrot agent too

# Sign in as the NEW Dutch channel here, not the existing one:
YOUTUBE_TOKEN_FILE=token_nl.json .venv/bin/python -c \
  "from scripts.youtube_uploader import get_authenticated_service; get_authenticated_service()"

.venv/bin/python brainrot.py check        # everything should read OK
```

### API quota is not your constraint

As of 1 June 2026 `videos.insert` bills to its own bucket at **1 unit per call,
100 calls/day** — it no longer costs 1,600 units and no longer competes with
reads. At 2 uploads/day this channel uses a rounding error of the quota. The
cadence cap in `scripts/nl/cadence.py` is a deliberate policy choice, not a
quota limit, and raising it is the riskiest change available to you.

## Daily use

```bash
.venv/bin/python brainrot.py topics                    # live Dutch search demand
.venv/bin/python brainrot.py produce "<onderwerp>"     # render, no upload
.venv/bin/python brainrot.py produce "<onderwerp>" --upload
.venv/bin/python brainrot.py daemon                    # continuous, cadence-capped
```

Two topics that keep colliding? `--salt v2` re-rolls the variant for the same
subject without reusing the first version's look and voice.

## Running it unattended

```bash
./manage.sh start nl      # start ONLY the Dutch daemon
./manage.sh status nl
./manage.sh logs nl
./manage.sh stop nl
```

`./manage.sh start` without `nl` starts the **English** autopilot and cleanup —
the two are deliberately separate because they publish to different channels.

## Tuning

| Variable | Default | Notes |
|---|---|---|
| `NL_MAX_UPLOADS_PER_DAY` | 2 | Raising this is the single riskiest change you can make |
| `NL_MIN_HOURS_BETWEEN_UPLOADS` | 5 | Minimum spacing |
| `NL_UPLOAD_JITTER_MINUTES` | 90 | Randomness on top of spacing |

## Before you publish the first one

Render a few without `--upload` and watch them. The variation engine only
guarantees that videos *differ*; it cannot tell you whether they are *good*.
The angle line printed at the end of each run is the fastest quality signal —
if `Invalshoek:` reads like a generic summary rather than a claim you could
argue with, the script is filler and will perform like it.
