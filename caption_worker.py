"""Scale-to-zero RunPod worker for styled talking-head captions."""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import httpx

from caption_engine import caption_style_catalog, prepare_caption_timing, render_caption


JOB_ROOT = Path(os.environ.get("CAPTION_JOB_ROOT", "/tmp/ugc-captions")).resolve()
MAX_INLINE_BYTES = 7_000_000


def _download(url: str, destination: Path) -> None:
    response = httpx.get(url, timeout=300.0, follow_redirects=True)
    response.raise_for_status()
    destination.write_bytes(response.content)


def _decode(value: str, destination: Path) -> None:
    if value.startswith("data:"):
        value = value.split(",", 1)[1]
    destination.write_bytes(base64.b64decode(value))


def _upload_to_s3(job_id: str, path: Path, content_type: str) -> str | None:
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    access_key = os.environ.get("S3_ACCESS_KEY_ID")
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY")
    bucket = os.environ.get("S3_BUCKET")
    public_base = os.environ.get("S3_PUBLIC_BASE_URL", "").rstrip("/")
    if not all((endpoint, access_key, secret_key, bucket, public_base)):
        return None
    import boto3

    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    key = f"captions/{job_id}/{path.name}"
    with path.open("rb") as source:
        client.upload_fileobj(source, bucket, key, ExtraArgs={"ContentType": content_type})
    return f"{public_base}/{key}"


def _inline_base64(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    if len(encoded) > 9_000_000:
        raise RuntimeError("Captioned output exceeds the inline RunPod response limit; configure S3 output")
    return encoded


def handler(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job.get("id") or uuid.uuid4().hex)
    payload = job.get("input", {}) or {}
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video_name = Path(payload.get("video_filename", "input.mp4")).name
    video_path = job_dir / video_name
    output_path = job_dir / f"captioned-{payload.get('style', 'pop')}.mp4"
    try:
        if payload.get("video_url"):
            _download(str(payload["video_url"]), video_path)
        elif payload.get("video_base64"):
            _decode(str(payload["video_base64"]), video_path)
        else:
            raise ValueError("Missing video_url or video_base64")
        if str(payload.get("mode", "render")).lower() == "prepare":
            timing = prepare_caption_timing(
                video_path=video_path,
                transcript=str(payload.get("transcript", "")),
                caption_source=str(payload.get("caption_source", "script")),
                language=str(payload.get("language", "")),
            )
            return {"status": "prepared", **timing}

        provided_words = payload.get("words")
        if not isinstance(provided_words, list):
            provided_words = None
        style_config = payload.get("style_config")
        if not isinstance(style_config, dict):
            style_config = None
        result = render_caption(
            video_path=video_path,
            output_path=output_path,
            transcript=str(payload.get("transcript", "")),
            caption_source=str(payload.get("caption_source", "script")),
            style_id=str(payload.get("style", "pop")),
            language=str(payload.get("language", "")),
            words_per_group=int(payload["words_per_group"]) if payload.get("words_per_group") else None,
            words=provided_words,
            style_config=style_config,
        )
        video_url = _upload_to_s3(job_id, output_path, "video/mp4")
        ass_url = _upload_to_s3(job_id, Path(result["ass_path"]), "text/x-ass")
        words_url = _upload_to_s3(job_id, Path(result["words_path"]), "application/json")
        response: dict[str, Any] = {
            "status": "completed",
            "style": result["style"],
            "style_label": result["style_label"],
            "caption_source": result["caption_source"],
            "word_count": result["word_count"],
            "duration": result["duration"],
            "words": result["words"],
        }
        if video_url:
            response["video_url"] = video_url
        else:
            response.update({"video_base64": _inline_base64(output_path), "filename": output_path.name, "content_type": "video/mp4"})
        if ass_url:
            response["ass_url"] = ass_url
        if words_url:
            response["words_url"] = words_url
        return response
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path)
    parser.add_argument("--transcript", default="")
    parser.add_argument("--caption-source", default="script", choices=("script", "transcribe"))
    parser.add_argument("--style", default="pop", choices=tuple(caption_style_catalog()[index]["id"] for index in range(len(caption_style_catalog()))))
    parser.add_argument("--output", type=Path, required=False)
    args = parser.parse_args()
    if not args.video:
        import runpod

        runpod.serverless.start({"handler": handler})
        return
    output = args.output or args.video.with_name(f"{args.video.stem}-captioned-{args.style}.mp4")
    print(json.dumps(render_caption(args.video, output, args.transcript, args.caption_source, args.style), indent=2))


if __name__ == "__main__":
    main()