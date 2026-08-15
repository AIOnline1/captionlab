# Runpod Caption Pipeline Handoff

This document explains how to give a coding agent access to Runpod and how to operate the caption pipeline we already built and tested.

It is written for a second developer or a family member who may not know the infrastructure yet. Follow the sections in order. Do not skip the account, balance, secret-handling, or cost-safety sections.

Last checked: 2026-08-15

## What this system does

The caption pipeline takes a finished video and either:

1. uses a supplied transcript and aligns it to the spoken audio, or
2. transcribes the video audio with Whisper and uses the recognized words.

It then creates word-timed social captions, burns them into a new MP4 with FFmpeg, and returns:

- the captioned MP4;
- the timed word list;
- an ASS subtitle file;
- a JSON timing/style file.

The proven flow is:

```text
Browser/editor
  -> secure UGCWebsite FastAPI gateway
  -> Runpod Serverless queue endpoint
  -> caption_worker.py
  -> temporary worker files
  -> faster-whisper word timing
  -> ASS caption generation
  -> FFmpeg H.264 render
  -> temporary output or object-storage URL
  -> gateway polls Runpod and exposes the result to the browser
```

The browser must not call Runpod directly. The Runpod API key belongs only on the gateway server.

The worker is stateless. It deletes its temporary job directory in a `finally` block after every job. Firebase is not involved in this caption render path, and Firebase Storage is not required.

## What this can and cannot promise

Yes, this can caption ordinary uploaded videos accurately, but "any video" has practical boundaries:

- Supported gateway uploads are MP4, MOV, WEBM, and M4V.
- The gateway accepts files up to 200 MB, but inline JSON transport is intended for files up to approximately 6.5 MB.
- Larger files need the documented S3-compatible temporary input/output path.
- The video needs a usable speech track. Music-only, silent, heavily clipped, very noisy, overlapping, or extremely fast speech can reduce transcription accuracy.
- Clear single-speaker speech with the correct language supplied is the most reliable case.
- `caption_source=transcribe` uses `faster-whisper large-v3` to create the displayed words.
- `caption_source=script` uses the supplied presenter script for the displayed wording and aligns it to recognized audio timing. This is the preferred mode when the exact script is known.
- The system is highly accurate, not mathematically perfect. Always use `mode=prepare` to review word timing for important videos before burning the final captions.
- Captions do not identify speakers, translate speech, remove background music, or correct unsupported claims.

The Markdown file is an operating guide, not a self-contained hosted service. To run the system, the agent also needs either the caption source files in the private `captionlab` repository, access to the existing worker image/endpoint, or permission to deploy a new endpoint. The document never contains a Runpod API key.

## Public GitHub repository and sharing

The caption worker source is mirrored in the public personal repository:

<https://github.com/AIOnline1/captionlab>

The repository contains only caption-specific source, Docker/build files, the pinned worker dependencies, and this handoff. It deliberately excludes `.env` files, API keys, Docker credentials, generated videos, audio, and unrelated UGC integrations. Anyone can clone/read it; only the owner can push unless explicit write access is granted.

Share only:

- the public repository URL;
- this `RUNPOD_CAPTIONS_HANDOFF.md` file (already stored in the repository);
- the endpoint ID `2qmk512pi39ec2` when they are meant to inspect the existing deployment.

Do not share `.env`, Runpod API keys, Docker Hub passwords/tokens, S3 credentials, or generated customer media. If the collaborator must manage the existing endpoint, grant Runpod account access separately through the account's supported login/OAuth controls. Otherwise they should deploy into their own Runpod account.

Public source access does not grant Runpod access. A collaborator also needs access to the Runpod account/endpoint, or must authenticate their own Runpod account and deploy the worker image there.

## Important cost warning

Runpod is paid GPU infrastructure. It is not a free service.

Before running anything:

1. Create or sign in to a Runpod account at <https://console.runpod.io/>.
2. Verify the email/account if Runpod requests it.
3. Add a payment method or deposit credits in the Runpod billing page.
4. Set a personal spending limit or budget reminder.
5. Never create an active worker for this caption endpoint unless a warm worker is genuinely needed.
6. Keep the endpoint at `min workers = 0` and `max workers = 1` initially.
7. Stop or terminate any ordinary Pod after testing. A normal Pod can continue billing while idle.
8. Check the Runpod console balance and usage after every test session.

Flex Serverless workers scale to zero when idle. That means there is no GPU worker charge while the endpoint is scaled down, but each running/initializing request is billed and storage or other attached resources may still cost money. Prices change, so use the live Runpod pricing page and endpoint console as the source of truth:

- <https://www.runpod.io/pricing>
- <https://console.runpod.io/serverless>

For this caption workload, the endpoint was designed for a 16 GB GPU class such as A4000/A4500/RTX 4000. Do not select an H100 or A100 for caption rendering unless a measured workload proves it is necessary.

## Runpod agent onboarding

Runpod publishes the onboarding instructions at:

<https://docs.runpod.io/agent-setup.md>

For GitHub Copilot, Cursor, Windsurf, Cline, and similar agents, the official guided installer is:

```powershell
npx @runpod/mcp-server@latest add
```

The installer detects the local coding agents and configures the hosted Runpod MCP connection. It may show an agent-selection menu. Select the agent you actually use.

The installer does not create a Pod or Serverless endpoint. It only installs agent integration/configuration.

After installation:

1. Restart VS Code or restart the coding agent so it reloads MCP configuration.
2. Ask the agent: `List my Runpod Serverless endpoints`.
3. When the agent asks for authentication, choose **Sign in with Runpod** and complete the OAuth browser flow.
4. Ask the agent: `List my Pods`.
5. An empty Pod list is a successful connection. It means there are no running Pods.
6. Ask the agent to show the current account balance before starting anything paid.

The agent setup uses OAuth for the MCP connection. Do not paste a Runpod API key into chat.

The official skills include a router plus skills for:

- Runpod MCP control-plane operations;
- Pods and Serverless endpoints;
- `runpodctl` file/CLI operations;
- Flash deployments;
- usage, pricing, storage, and GPU guidance;
- companion CLIs such as Docker and Hugging Face when needed.

Do not install `runpodctl`, Flash, Docker, or Hugging Face credentials just because they are mentioned. Install/use them only when the specific task requires them.

### Current local onboarding result

On the development machine, the official installer configured these user-level locations:

```text
C:\Users\aliin\AppData\Roaming\Code\User\mcp.json
C:\Users\aliin\.cursor\mcp.json
C:\Users\aliin\AppData\Roaming\Claude\claude_desktop_config.json
```

That configuration still requires the human OAuth sign-in. A configuration file is not proof that the MCP connection is authenticated.

## Existing caption deployment

The existing gateway configuration contains this Caption Serverless endpoint ID:

```text
2qmk512pi39ec2
```

Endpoint IDs are not secrets. API keys are secrets.

The existing worker image is intended to be:

```text
docker.io/aliinha/ugc-pipeline:captions-v3
```

Published v3 digest:

```text
sha256:9eb3c325f06a8d991520562411e682e8aaa9cfd126746ddadad5aa42bde01464
```

The production endpoint was verified on 2026-08-15 with minimum workers `0`, maximum workers `1`, and idle timeout `5` seconds.

The source files live in the existing UGCWebsite folder:

```text
C:\Users\aliin\Downloads\UGCWebsite\caption_engine.py
C:\Users\aliin\Downloads\UGCWebsite\caption_worker.py
C:\Users\aliin\Downloads\UGCWebsite\Dockerfile.captions
C:\Users\aliin\Downloads\UGCWebsite\Dockerfile.captions.patch
C:\Users\aliin\Downloads\UGCWebsite\deploy_captions.ps1
C:\Users\aliin\Downloads\UGCWebsite\requirements.captions.txt
C:\Users\aliin\Downloads\UGCWebsite\server.py
```

If working from another computer, make sure the agent has a copy of those files or access to the project repository. This Markdown file alone is the operating manual; it is not the worker image or source code.

Before creating a second endpoint, ask the Runpod agent to list endpoints and inspect endpoint `2qmk512pi39ec2`. Reuse the existing endpoint if it is healthy and belongs to the intended Runpod account.

If the endpoint is missing, inaccessible, or belongs to a different Runpod account, deploy a new endpoint using the instructions below. Do not create duplicates without checking first.

## Exact caption worker behavior

### Input video

The worker accepts either:

- `video_base64` for a small inline input; or
- `video_url` for an HTTPS URL the worker can download.

The existing gateway accepts uploaded MP4, MOV, WEBM, and M4V files up to 200 MB. It sends files inline when they are at most approximately 6.5 MB. Larger files require the optional S3-compatible input path.

In the hosted UGC browser, the cookie-authenticated gateway first issues a short-lived signed URL for the owner's private Supabase `videos/{user-id}/caption-input/...` folder. The browser uploads directly to that URL, then sends only `uploaded_storage_path` through Vercel, avoiding Vercel's multipart request limit. The gateway validates the owner prefix, downloads the object, and deletes that staged input. Other platforms may use this same pattern or the documented S3-compatible path.

The worker accepts these input fields:

```json
{
  "video_filename": "input.mp4",
  "video_base64": "base64-data-without-or-with-data-prefix",
  "transcript": "The exact presenter script or transcript.",
  "caption_source": "script",
  "style": "pop",
  "language": "",
  "words_per_group": 4,
  "mode": "render",
  "words": [],
  "style_config": {}
}
```

`video_base64` and `video_url` are alternatives. A request must provide one of them.

### Caption source modes

`caption_source` is either `script` or `transcribe`.

#### `script` mode

Use this when the intended presenter script is known.

The worker still extracts and transcribes the audio to get recognized word timings, then aligns the supplied script to the recognized words using normalized token matching. This is the preferred mode when the generated presenter script is authoritative because the displayed captions use the script wording while the audio supplies timing.

If exact matching is incomplete, unmatched script words are distributed between the nearest known timings. This lets a rewritten script remain captionable even when the audio recognition differs slightly.

A non-empty `transcript` is required in `script` mode at the gateway.

#### `transcribe` mode

Use this when no script is available.

The worker extracts the audio and uses the recognized Whisper words directly. A usable spoken recording is required.

### Transcription settings

The caption Docker image is configured for:

```text
CAPTION_MODEL=large-v3
CAPTION_DEVICE=cuda
CAPTION_COMPUTE_TYPE=float16
CAPTION_VAD_FILTER=1
```

The underlying caption engine uses `faster-whisper` with:

- `word_timestamps=True`;
- `condition_on_previous_text=False`;
- `beam_size=5`;
- VAD controlled by `CAPTION_VAD_FILTER`;
- optional forced `language`, such as `en`, `hi`, or `ur`;
- GPU CUDA inference with `float16` for the deployed worker.

The audio is normalized by FFmpeg to:

```text
16,000 Hz
mono
PCM signed 16-bit WAV
```

The worker keeps the native recognized words by default. The broader timing module contains `uroman` support for Romanized Hindi/Urdu workflows, but the deployed caption worker's default output is native script. Do not change this default without checking the actual caption readability and alignment.

### Timing preparation mode

Set:

```json
"mode": "prepare"
```

This returns timing and word data without burning captions into the video. It is used by the editor to preview timing before rendering.

Typical response:

```json
{
  "status": "prepared",
  "caption_source": "script",
  "duration": 17.4,
  "word_count": 82,
  "words": [
    {"text": "This", "start": 0.0, "end": 0.22, "nativeText": "This"}
  ],
  "native_words": [
    {"text": "This", "start": 0.0, "end": 0.22}
  ],
  "native_transcript": "This is the native recognized text",
  "transcript": "This is the displayed text",
  "detected_language": "en",
  "language_probability": 0.99,
  "output_script": "native"
}
```

### Render mode

The default is:

```json
"mode": "render"
```

The worker:

1. downloads or decodes the input video into a job-specific temporary directory;
2. prepares or receives timed words;
3. groups words by `words_per_group` and punctuation;
4. writes an ASS subtitle file;
5. runs FFmpeg to burn the ASS captions into the video;
6. returns the MP4, word list, and optional ASS/JSON URLs;
7. deletes the temporary job directory.

FFmpeg render settings are:

```text
video codec: libx264
preset: veryfast
CRF: 18
pixel format: yuv420p
audio: copied when present
fast start: enabled
```

The ASS canvas is:

```text
PlayResX: 1080
PlayResY: 1920
alignment: bottom-center
```

`words_per_group` must be between 1 and 8. If omitted, each style's default is used.

## Caption styles

The style catalog is exposed by:

```text
GET /api/captions/styles
```

The current styles are:

| ID | Look | Font size | Active color | Max words | Animation/default |
|---|---|---:|---|---:|---|
| `pop` | Bold social captions | 68 | `#B9F45A` lime | 4 | Per-word pop highlight |
| `clean` | Quiet polished white captions | 60 | `#B9F45A` available | 5 | Static grouped line |
| `boxed` | Dark editorial label | 56 | `#B9F45A` | 5 | Boxed per-word active highlight |
| `neon` | Violet active word | 62 | `#AA98FF` | 4 | Per-word pop highlight |
| `minimal` | Smaller understated captions | 48 | `#76D9FF` | 6 | Static grouped line |

The exact default visual values are defined in `caption_engine.py`. Do not reproduce the style system in a second worker by hand. Copy the source module into the image so frontend and worker behavior cannot drift.

CaptionLab can override presets with approved fonts including Manrope, Space Grotesk, Barlow Condensed, Archivo Black, Bebas Neue, Playfair Display, DM Mono, IBM Plex Mono, and the DejaVu sans/serif/mono families. The v3 worker packages the same custom faces used by the browser preview.

Verified v3 font test: libass resolved `Manrope` weight 700 to `/usr/local/share/fonts/ugc/Manrope.ttf`. The burned ASS outline and shadow are intentionally heavier than the browser's clean example, so compare letter shapes rather than expecting identical anti-aliasing.

Default `pop` style:

```text
font: DejaVu Sans
size: 68
primary: white
active: #B9F45A
outline: #090B0F
outline width: 5
shadow: 2
margin_v: 190
max_words: 4
```

Allowed style customization is intentionally constrained:

- approved font names only;
- font size clamped from 24 to 140;
- hex colors only;
- vertical margin clamped from 40 to 700;
- opacity clamped from 0 to 100;
- effects: `pop`, `bounce`, `glow`, `lift`, `underline`, `marker`, `stroke`, or `none`;
- optional uppercase mode;
- optional active-word mode.

Do not accept arbitrary FFmpeg filter expressions from a browser request.

The v3 renderer emits distinct ASS behavior for every listed effect. Browser previews are guidance; the burned MP4 is the final source of truth.

## Gateway API

The gateway is `UGCWebsite/server.py`. It keeps the Runpod key server-side, stages uploads, submits jobs, polls status, and registers completed files in the local UGC library.

### Prepare timing

```text
POST /api/captions/prepare
Content-Type: multipart/form-data
```

Fields:

```text
video: file
transcript: optional text
caption_source: script or transcribe
language: optional language code
```

Response status is `202 Accepted`:

```json
{
  "jobId": "local-gateway-job-id",
  "status": "queued",
  "statusUrl": "/api/captions/local-gateway-job-id",
  "provider": "runpod"
}
```

### Render captions

```text
POST /api/captions
Content-Type: multipart/form-data
```

Fields:

```text
video: file
transcript: text when caption_source=script
caption_source: script or transcribe
style: pop, clean, boxed, neon, or minimal
language: optional language code
words_per_group: integer 1 through 8
words: optional JSON timed-word array
style_config: optional JSON object
source_video_id: optional local library source ID
uploaded_storage_path: optional owner-scoped private Supabase path for browser uploads
```

### Poll status

```text
GET /api/captions/{local_job_id}
```

The gateway reports states such as:

```text
queued
processing
completed
failed
```

For a completed job, the gateway exposes `videoUrl`/`outputUrl`, word timing, and optional ASS/JSON URLs. The completed video is registered in the local `.ugc-library` database when the gateway can download or decode the result.

## Runpod worker contract

The worker submits to the standard Runpod Serverless queue endpoint:

```text
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/run
Authorization: Bearer <server-only-key>
Content-Type: application/json
```

The gateway then polls:

```text
GET https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{RUNPOD_JOB_ID}
Authorization: Bearer <server-only-key>
```

The existing gateway uses these environment variables:

```text
CAPTION_RUNPOD_ENDPOINT_ID=2qmk512pi39ec2
CAPTION_RUNPOD_API_KEY=<server-only-secret>
CAPTION_RUNPOD_API_BASE=https://api.runpod.ai/v2
CAPTION_LOCAL_RENDER=0
```

`CAPTION_RUNPOD_API_KEY` may fall back to `RUNPOD_API_KEY` in the existing server code, but using a clearly named caption key is easier to audit.

Never put these variables in:

- React/Vite `.env` variables beginning with `VITE_`;
- browser JavaScript;
- a public GitHub repository;
- this handoff document;
- a support chat message;
- a client-side Runpod request.

The endpoint ID is safe to share. The API key is not.

## Build the worker image

These commands must be run from:

```powershell
Set-Location C:\Users\aliin\Downloads\UGCWebsite
```

### First-time Docker checks

```powershell
docker --version
docker info
```

Docker Desktop must be installed and running. Runpod Serverless workers use Linux containers, so always build for AMD64:

```powershell
docker build --platform linux/amd64 ...
```

### Build the base captions image

The full base image is defined by `Dockerfile.captions`:

```powershell
docker build --platform linux/amd64 -f Dockerfile.captions -t aliinha/ugc-pipeline:captions-v1 .
```

The base image contains:

- CUDA 12.4 runtime with cuDNN;
- Ubuntu 22.04;
- Python 3;
- FFmpeg and ffprobe;
- DejaVu fonts plus the creator/editorial/mono font families exposed in CaptionLab;
- `faster-whisper`;
- `ctranslate2==4.5.0`;
- `uroman`;
- `httpx`;
- `runpod`;
- `boto3`;
- the `large-v3` Whisper model cache;
- `caption_engine.py`;
- `caption_worker.py`.

The model is warmed into the image cache during the Docker build. This makes worker initialization more predictable than downloading the model on every worker startup.

### Build the current patch image

`Dockerfile.captions.patch` is a small layer that starts from `aliinha/ugc-pipeline:captions-v1` and copies the current caption source files into the image.

Use the supplied deployment script:

```powershell
.\deploy_captions.ps1
```

That script performs:

```powershell
docker build --platform linux/amd64 -f Dockerfile.captions.patch -t aliinha/ugc-pipeline:captions-v3 .
docker push aliinha/ugc-pipeline:captions-v3
```

The script does not log in to Docker Hub for you. Authenticate interactively when Docker asks. Never place a Docker password or access token in this Markdown file or in chat.

If the image name must be changed for another Docker Hub account:

```powershell
$env:IMAGE = "yourdockeruser/ugc-pipeline:captions-v3"
docker build --platform linux/amd64 -f Dockerfile.captions.patch -t $env:IMAGE .
docker push $env:IMAGE
```

The patch Dockerfile must also be updated to use the account's available base image if `aliinha/ugc-pipeline:captions-v1` is private or inaccessible.

## Create or repair the Serverless endpoint

First ask the Runpod-enabled agent:

```text
List my Serverless endpoints and show the health of endpoint 2qmk512pi39ec2.
```

If the endpoint exists and is healthy, do not create another one.

If a new endpoint is required, use the Runpod console:

<https://console.runpod.io/serverless>

Choose **New Endpoint** and **Import from Docker Registry**.

Use:

```text
Container image: docker.io/aliinha/ugc-pipeline:captions-v3
Endpoint type: Queue
Worker type: Flex
Minimum/active workers: 0
Maximum workers: 1
GPUs per worker: 1
GPU class: 16 GB, preferably A4000/A4500/RTX 4000
Idle timeout: 5 seconds
Execution timeout: 300 seconds
FlashBoot: enabled
```

Do not expose ports. This worker uses the Runpod job handler, not a public HTTP port.

Set these worker environment variables:

```text
CAPTION_MODEL=large-v3
CAPTION_DEVICE=cuda
CAPTION_COMPUTE_TYPE=float16
CAPTION_VAD_FILTER=1
CAPTION_JOB_ROOT=/tmp/ugc-captions
PYTHONUNBUFFERED=1
```

Do not add a network volume for this caption image unless the model deployment is intentionally changed. The image already contains the model cache, and network-volume reads can be slower and add storage cost.

Deploy, then test with the endpoint Requests tab. The first request may take several minutes while Runpod initializes the Flex worker and loads the model. A first cold start is not evidence that the handler is broken.

## Direct endpoint smoke test

The safest first test is through the Runpod console Requests tab with a small test video or a small HTTPS test file. Do not start with a large production video.

A direct API request has this shape:

```powershell
$endpointId = "2qmk512pi39ec2"
$body = @{
  input = @{
    video_url = "https://example.com/test-caption-video.mp4"
    video_filename = "test-caption-video.mp4"
    transcript = "This is a small caption worker test."
    caption_source = "script"
    style = "pop"
    language = "en"
    words_per_group = 4
    mode = "render"
  }
} | ConvertTo-Json -Depth 8

$response = Invoke-RestMethod `
  -Method Post `
  -Uri "https://api.runpod.ai/v2/$endpointId/run" `
  -Headers @{ Authorization = "Bearer $env:RUNPOD_API_KEY" } `
  -ContentType "application/json" `
  -Body $body

$response
```

The API key must already be set in the current shell by the human operator. Do not print it:

```powershell
$env:RUNPOD_API_KEY = "<enter it locally, do not paste it into chat>"
```

Poll the returned job ID:

```powershell
$jobId = $response.id
Invoke-RestMethod `
  -Method Get `
  -Uri "https://api.runpod.ai/v2/$endpointId/status/$jobId" `
  -Headers @{ Authorization = "Bearer $env:RUNPOD_API_KEY" }
```

If using the agent MCP instead of a raw API key, ask the agent to submit a small caption smoke-test job and inspect the result. Prefer MCP for control-plane work and keep the gateway API key only on the server.

## Local gateway test

The gateway must have FFmpeg available and must be started from `UGCWebsite`.

```powershell
Set-Location C:\Users\aliin\Downloads\UGCWebsite
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Set server-only configuration before starting it:

```powershell
$env:CAPTION_RUNPOD_ENDPOINT_ID = "2qmk512pi39ec2"
$env:CAPTION_RUNPOD_API_KEY = "<enter locally; never paste into chat>"
$env:CAPTION_RUNPOD_API_BASE = "https://api.runpod.ai/v2"
$env:CAPTION_LOCAL_RENDER = "0"
```

Example multipart render request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/captions `
  -F "video=@C:\path\to\input.mp4" `
  -F "transcript=This is the exact presenter script to caption." `
  -F "caption_source=script" `
  -F "style=pop" `
  -F "language=en" `
  -F "words_per_group=4"
```

The response returns a local gateway job ID. Poll it:

```powershell
curl.exe http://127.0.0.1:8000/api/captions/<local-job-id>
```

The gateway should report `provider: runpod` when it queues the job on Serverless.

## Optional object storage for larger videos

The current gateway sends videos inline only up to approximately 6.5 MB. Larger inputs require an S3-compatible object store because base64 JSON is not appropriate for large files.

The worker supports S3-compatible output variables:

```text
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=<server-only>
S3_SECRET_ACCESS_KEY=<server-only>
S3_BUCKET=<bucket>
S3_PUBLIC_BASE_URL=https://<public-media-domain>
```

The gateway uses the same variables to upload large caption inputs. The worker writes keys under:

```text
caption-input/{job_id}/{filename}
```

and outputs under:

```text
captions/{job_id}/{filename}
```

If no S3 variables are configured, the worker returns inline base64 output for small videos. Inline output has a practical size limit and should be used only for short test clips.

Do not enable Firebase Storage merely to solve this. The existing caption design uses an S3-compatible output path when larger media is needed.

## Troubleshooting

### The agent cannot see Runpod tools

1. Restart VS Code or the agent.
2. Confirm the Runpod MCP entry exists in the user MCP configuration.
3. Ask the agent to list endpoints.
4. Complete the Runpod OAuth sign-in when prompted.
5. Do not report MCP as connected until an endpoint or Pod listing succeeds.

### Endpoint is missing

The existing endpoint ID is `2qmk512pi39ec2`. Endpoint IDs belong to a Runpod account. If Dad is signed into a different account, he may not see it. Either sign into the account that owns the endpoint or deploy the same image into his account.

### Endpoint is queued forever

Ask the agent to inspect:

```text
Show endpoint health and worker states for endpoint 2qmk512pi39ec2.
```

Interpretation:

- zero workers can mean Runpod is waiting for available GPU capacity;
- an unhealthy worker usually means the image crashed during startup;
- a job can be queued during a normal Flex cold start;
- repeated unhealthy workers require endpoint logs and image inspection.

Check the Runpod endpoint Workers and Logs tabs. Do not keep resubmitting jobs while the first one is still queued because that can multiply cost.

### Worker starts but fails to import modules

Rebuild the image from the correct Dockerfile and verify that these files are copied into `/opt/ugc`:

```text
caption_engine.py
caption_worker.py
```

The requirements must include:

```text
faster-whisper>=1.2,<2
ctranslate2==4.5.0
setuptools<81
uroman>=1.3,<2
httpx>=0.27,<1
runpod>=1.7,<2
boto3>=1.34,<2
```

Do not randomly upgrade `ctranslate2` or `setuptools`. The known Windows/local caption environment required `ctranslate2==4.5.0` and `setuptools<81`.

### `faster-whisper` cannot load the model

Check the worker environment:

```text
CAPTION_MODEL=large-v3
CAPTION_DEVICE=cuda
CAPTION_COMPUTE_TYPE=float16
```

Check that the endpoint GPU has enough VRAM and that the image model cache was built successfully. If the model was not baked/cached, the worker may try to download it at startup, causing a long cold start.

### Captions are out of sync

Use `caption_source=script` with the exact presenter script when possible. The system aligns the supplied text to recognized audio words. Check:

- the supplied transcript matches what was actually spoken;
- the language is correct;
- the video has a clean speech track;
- VAD is not removing quiet words;
- `words_per_group` is not excessively large.

For debugging, use `mode=prepare` and inspect the returned `words` before rendering.

### Captions are missing entirely

Check:

- the video has an audio stream;
- the input extension is MP4/MOV/WEBM/M4V;
- FFmpeg and ffprobe are present;
- `caption_source=script` has a non-empty transcript;
- `caption_source=transcribe` actually detects speech;
- the ASS file was returned or inspectable;
- the worker log contains no FFmpeg `ass` filter error.

### Large input is rejected

Files larger than approximately 6.5 MB cannot be sent through the gateway's inline base64 path. Configure the S3-compatible input/output variables or use a shorter test clip.

### Runpod job succeeds but gateway shows no video

Inspect the Runpod result. It must include either:

```text
video_url
```

or:

```text
video_base64
filename
content_type
```

If the worker returned a URL, make sure the URL is reachable from the gateway. If the worker returned inline base64, verify that the result was not too large for the gateway response path.

### Docker build or push fails

Check:

```powershell
docker info
docker login
```

Use a Docker Hub repository the current account can push to. Build with `--platform linux/amd64`. Do not push a CPU-only or Windows image for Runpod Linux GPU workers.

### A normal Pod was created by mistake

Terminate it immediately from the Runpod console or ask the agent:

```text
List my running Pods, then stop/terminate only the test Pod I identify.
```

Do not terminate an unknown Pod just because it exists. Confirm its name/ID first.

## Source-of-truth files

Keep these files together and deploy them as one tested unit:

```text
UGCWebsite/caption_engine.py
UGCWebsite/caption_worker.py
UGCWebsite/requirements.captions.txt
UGCWebsite/Dockerfile.captions
UGCWebsite/Dockerfile.captions.patch
UGCWebsite/deploy_captions.ps1
UGCWebsite/server.py
```

Do not copy only `caption_worker.py` into a new project. It imports `caption_engine.py`, and the exact alignment, ASS, style, and FFmpeg behavior lives in that module.

The gateway is separate from the worker:

```text
server.py                 local secure HTTP gateway
caption_worker.py         Runpod Serverless handler
caption_engine.py         timing, styles, ASS, FFmpeg
Dockerfile.captions       base image
Dockerfile.captions.patch current source-code patch image
```

## Safe operating checklist

Before a real run:

- [ ] Runpod account is signed in.
- [ ] Runpod balance/payment is configured.
- [ ] Budget and max worker limits are understood.
- [ ] Agent MCP OAuth is complete and endpoint listing works.
- [ ] Existing endpoint `2qmk512pi39ec2` was checked before creating anything.
- [ ] Endpoint is Queue + Flex, min workers 0, max workers 1.
- [ ] Endpoint execution timeout is 300 seconds.
- [ ] Worker image is the intended `captions-v3` image.
- [ ] Runpod API key is stored only on the gateway/server environment.
- [ ] No Runpod key is in browser code, Vite variables, Markdown, Git, or chat.
- [ ] Test with a short clip first.
- [ ] Check the endpoint result before submitting another job.
- [ ] Check Runpod balance and usage after testing.

## Official references

- Agent onboarding: <https://docs.runpod.io/agent-setup.md>
- Agent skills: <https://docs.runpod.io/get-started/agent-skills>
- Serverless quickstart: <https://docs.runpod.io/serverless/quickstart>
- Serverless worker overview: <https://docs.runpod.io/serverless/workers/overview>
- Endpoint settings: <https://docs.runpod.io/serverless/endpoints/manage-endpoints>
- Runpod pricing: <https://www.runpod.io/pricing>
- Runpod console: <https://console.runpod.io/>
