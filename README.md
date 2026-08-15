# CaptionLab

CaptionLab is the private Runpod Serverless worker for accurate word-timed captions.

## What is included

- `caption_engine.py`: faster-whisper timing, script-to-audio alignment, ASS generation, caption styles, distinct caption effects, and FFmpeg burn-in.
- `caption_worker.py`: stateless Runpod Serverless queue handler.
- `requirements.captions.txt`: pinned worker dependencies.
- `Dockerfile.captions`: CUDA base image with FFmpeg, dependencies, the `large-v3` model cache, and browser-matching fonts.
- `Dockerfile.captions.patch`: current v3 source and font patch image layer.
- `deploy_captions.ps1`: AMD64 Docker build and Docker Hub push helper.
- `RUNPOD_CAPTIONS_HANDOFF.md`: full setup, account, cost, endpoint, gateway, testing, and troubleshooting guide.

Caption worker v3 packages the same approved font families used by the browser preview and emits distinct ASS behavior for the supported effects: pop, bounce, glow, lift, underline, marker, stroke, and none.

## Existing deployment

- Docker image: `docker.io/aliinha/ugc-pipeline:captions-v3`
- Published digest: `sha256:9eb3c325f06a8d991520562411e682e8aaa9cfd126746ddadad5aa42bde01464`
- Existing endpoint ID: `2qmk512pi39ec2`
- Endpoint type: Queue + Flex workers
- Scaling: minimum 0, maximum 1, idle timeout 5 seconds
- Intended GPU class: 16 GB A4000/A4500/RTX 4000

Verify the endpoint in the Runpod console or with the Runpod MCP before creating another one. Endpoint IDs are not secrets; API keys must never be committed here.

## Gateway uploads

The secure gateway accepts independent MP4, MOV, WebM, and M4V uploads up to 200 MB. Each upload can use either an exact supplied script for script-to-audio alignment or worker transcription when no script is available. Small files can use inline transport; larger files require the documented S3-compatible temporary input/output path.

The browser must call the secure gateway rather than Runpod directly. Runpod API keys and object-storage credentials remain server-side.

## Quick start

Read `RUNPOD_CAPTIONS_HANDOFF.md` first. The short version is:

```powershell
Set-Location C:\path\to\captionlab
docker build --platform linux/amd64 -f Dockerfile.captions -t aliinha/ugc-pipeline:captions-v1 .
docker push aliinha/ugc-pipeline:captions-v1
.\deploy_captions.ps1
```

The deploy script publishes `aliinha/ugc-pipeline:captions-v3` and requires Docker Hub authentication. Runpod account authentication and billing are separate from Docker Hub authentication.

## Safety

- Do not commit or share `.env` files, Runpod API keys, Docker credentials, S3 credentials, or generated customer media.
- The browser must call a secure gateway, not Runpod directly.
- Flex workers scale to zero, but running jobs are billed.
- Use short smoke tests first and keep maximum workers at 1 until measured.
- The worker deletes its temporary job directory after every job.
- Only caption videos you own or have permission to process.

## Public repository sharing

This public repository belongs to the personal GitHub account `AIOnline1`. Anyone can clone/read it; only grant collaborator access when someone needs to push changes. Never share `.env`, API, Docker, or S3 credentials, and never use generated media as a repository-sharing mechanism.

Public GitHub source access and Runpod access are separate. Someone who needs to inspect or manage endpoint `2qmk512pi39ec2` must receive Runpod account access separately or deploy the worker in their own Runpod account.
