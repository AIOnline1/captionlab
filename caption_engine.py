"""Caption timing, ASS generation, and FFmpeg rendering for UGC videos."""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


CAPTION_STYLES: dict[str, dict[str, Any]] = {
    "pop": {
        "label": "Pop highlight",
        "description": "Bold social captions with an active lime word.",
        "font_name": "DejaVu Sans",
        "font_size": 68,
        "primary_color": "#FFFFFF",
        "active_color": "#B9F45A",
        "outline_color": "#090B0F",
        "back_color": "#090B0F",
        "outline": 5,
        "shadow": 2,
        "border_style": 1,
        "bold": True,
        "margin_v": 190,
        "max_words": 4,
        "animation": "pop",
    },
    "clean": {
        "label": "Clean bold",
        "description": "High-contrast white captions for a quiet, polished take.",
        "font_name": "DejaVu Sans",
        "font_size": 60,
        "primary_color": "#FFFFFF",
        "active_color": "#B9F45A",
        "outline_color": "#090B0F",
        "back_color": "#090B0F",
        "outline": 4,
        "shadow": 1,
        "border_style": 1,
        "bold": True,
        "margin_v": 170,
        "max_words": 5,
        "animation": "none",
    },
    "boxed": {
        "label": "Soft box",
        "description": "Compact captions on a dark editorial label.",
        "font_name": "DejaVu Sans",
        "font_size": 56,
        "primary_color": "#FFFFFF",
        "active_color": "#B9F45A",
        "outline_color": "#090B0F",
        "back_color": "#090B0F",
        "outline": 9,
        "shadow": 0,
        "border_style": 3,
        "bold": True,
        "margin_v": 185,
        "max_words": 5,
        "animation": "none",
        "active_word": True,
    },
    "neon": {
        "label": "Neon focus",
        "description": "Violet active words with a bright creator-editing feel.",
        "font_name": "DejaVu Sans",
        "font_size": 62,
        "primary_color": "#FFFFFF",
        "active_color": "#AA98FF",
        "outline_color": "#15111F",
        "back_color": "#15111F",
        "outline": 4,
        "shadow": 2,
        "border_style": 1,
        "bold": True,
        "margin_v": 180,
        "max_words": 4,
        "animation": "pop",
    },
    "minimal": {
        "label": "Minimal",
        "description": "Smaller captions with a light blue active word.",
        "font_name": "DejaVu Sans",
        "font_size": 48,
        "primary_color": "#F4F7FB",
        "active_color": "#76D9FF",
        "outline_color": "#090B0F",
        "back_color": "#090B0F",
        "outline": 2,
        "shadow": 4,
        "border_style": 1,
        "bold": False,
        "margin_v": 145,
        "max_words": 6,
        "animation": "none",
    },
}

TOKEN_RE = re.compile(r"\S+")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
CAPTION_EFFECTS = {"pop", "bounce", "glow", "lift", "underline", "marker", "stroke", "none"}
CAPTION_FONTS = {
    "Manrope",
    "Space Grotesk",
    "Barlow Condensed",
    "Archivo Black",
    "DM Mono",
    "IBM Plex Mono",
    "Playfair Display",
    "Bebas Neue",
    "Arial Black",
    "Georgia",
    "DejaVu Sans",
    "DejaVu Sans Condensed",
    "DejaVu Sans Mono",
    "DejaVu Serif",
    "DejaVu Serif Condensed",
}
_WHISPER_MODEL: Any = None
_WHISPER_MODEL_CONFIG: tuple[str, str, str] | None = None
_UROMAN: Any = None


def _ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as error:
        raise RuntimeError("ffmpeg is required for caption rendering") from error


def caption_style_catalog() -> list[dict[str, str]]:
    return [
        {"id": style_id, "label": style["label"], "description": style["description"]}
        for style_id, style in CAPTION_STYLES.items()
    ]


def _safe_hex(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate.upper() if HEX_COLOR_RE.fullmatch(candidate) else fallback


def get_caption_style(style_id: str, style_config: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = (style_id or "pop").strip().lower()
    if clean_id not in CAPTION_STYLES:
        raise ValueError(f"Unknown caption style: {clean_id}")
    style = dict(CAPTION_STYLES[clean_id])
    config = style_config or {}
    if not isinstance(config, dict):
        raise ValueError("style_config must be an object")
    if config.get("font_name") in CAPTION_FONTS:
        style["font_name"] = config["font_name"]
    if config.get("font_size") is not None:
        style["font_size"] = max(24, min(140, int(config["font_size"])))
    style["primary_color"] = _safe_hex(config.get("primary_color"), style["primary_color"])
    style["active_color"] = _safe_hex(config.get("active_color"), style["active_color"])
    style["outline_color"] = _safe_hex(config.get("outline_color"), style["outline_color"])
    style["back_color"] = _safe_hex(config.get("back_color"), style["back_color"])
    if config.get("back_opacity") is not None:
        style["back_opacity"] = max(0, min(100, int(config["back_opacity"])))
    if config.get("margin_v") is not None:
        style["margin_v"] = max(40, min(700, int(config["margin_v"])))
    effect = str(config.get("effect", "")).strip().lower()
    if effect in CAPTION_EFFECTS:
        style["effect"] = effect
        style["animation"] = "pop" if effect in {"pop", "bounce", "glow", "lift", "underline", "marker", "stroke"} else "none"
    if "active_word" in config:
        style["active_word"] = bool(config["active_word"])
    if "uppercase" in config:
        style["uppercase"] = bool(config["uppercase"])
    return style


def _normalise_word(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)


def _tokens(text: str) -> list[dict[str, str]]:
    return [{"text": match.group(0), "normal": _normalise_word(match.group(0))} for match in TOKEN_RE.finditer(text)]


def _probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return max(0.1, float(result.stdout.strip()))
    result = subprocess.run([_ffmpeg_binary(), "-i", str(path)], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError("ffprobe or an FFmpeg duration probe is required for caption timing")
    hours, minutes, seconds = match.groups()
    return max(0.1, int(hours) * 3600 + int(minutes) * 60 + float(seconds))


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    ffmpeg = _ffmpeg_binary()
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(video_path), "-map", "0:a:0", "-vn",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _transcribe_words_with_metadata(audio_path: Path, language: str = "") -> tuple[list[dict[str, Any]], str | None, float | None]:
    global _WHISPER_MODEL, _WHISPER_MODEL_CONFIG
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("faster-whisper is not installed in the caption worker") from error

    model_name = os.environ.get("CAPTION_MODEL", "large-v3")
    device = os.environ.get("CAPTION_DEVICE", "cuda")
    compute_type = os.environ.get("CAPTION_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
    config = (model_name, device, compute_type)
    if _WHISPER_MODEL is None or _WHISPER_MODEL_CONFIG != config:
        _WHISPER_MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
        _WHISPER_MODEL_CONFIG = config

    kwargs: dict[str, Any] = {
        "word_timestamps": True,
        "vad_filter": os.environ.get("CAPTION_VAD_FILTER", "1").strip().lower() in {"1", "true", "yes", "on"},
        "condition_on_previous_text": False,
        "beam_size": 5,
    }
    if language.strip():
        kwargs["language"] = language.strip()
    segments, info = _WHISPER_MODEL.transcribe(str(audio_path), **kwargs)
    words: list[dict[str, Any]] = []
    for segment in segments:
        segment_words = getattr(segment, "words", None) or []
        for word in segment_words:
            if word.start is None or word.end is None:
                continue
            text = str(word.word or "").strip()
            if text:
                words.append({"text": text, "start": float(word.start), "end": float(word.end)})
    detected_language = str(getattr(info, "language", "") or "") or None
    language_probability = getattr(info, "language_probability", None)
    return words, detected_language, float(language_probability) if language_probability is not None else None


def _transcribe_words(audio_path: Path, language: str = "") -> list[dict[str, Any]]:
    return _transcribe_words_with_metadata(audio_path, language)[0]


def _romanize_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    global _UROMAN
    try:
        from uroman import Uroman
    except ImportError as error:
        raise RuntimeError("uroman is required for Romanized Hindi/Urdu transcript output") from error
    if _UROMAN is None:
        _UROMAN = Uroman()
    romanized: list[dict[str, Any]] = []
    for word in words:
        native_text = str(word.get("text", ""))
        romanized.append({**word, "nativeText": native_text, "text": _UROMAN.romanize_string(native_text)})
    return romanized


def _display_words(words: list[dict[str, Any]], output_script: str) -> list[dict[str, Any]]:
    script = (output_script or "native").strip().lower()
    if script not in {"native", "romanized"}:
        raise ValueError("output_script must be native or romanized")
    if script == "native":
        return [{**word, "nativeText": word.get("nativeText", word.get("text", ""))} for word in words]
    return _romanize_words(words)


def _evenly_timed_words(text: str, duration: float) -> list[dict[str, Any]]:
    tokens = _tokens(text)
    if not tokens:
        return []
    weights = [max(1.0, float(len(token["normal"]))) for token in tokens]
    total_weight = sum(weights)
    cursor = 0.0
    result: list[dict[str, Any]] = []
    for token, weight in zip(tokens, weights):
        span = duration * weight / total_weight
        result.append({"text": token["text"], "start": cursor, "end": min(duration, cursor + span)})
        cursor += span
    return result


def _align_script_to_words(script: str, recognised: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    script_tokens = _tokens(script)
    if not script_tokens:
        return []
    if not recognised:
        return _evenly_timed_words(script, duration)

    recognised_tokens = [_normalise_word(word["text"]) for word in recognised]
    script_norm = [token["normal"] for token in script_tokens]
    matcher = difflib.SequenceMatcher(a=script_norm, b=recognised_tokens, autojunk=False)
    mapped: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapped[block.a + offset] = block.b + offset

    result: list[dict[str, Any] | None] = [None] * len(script_tokens)
    for index, recognised_index in mapped.items():
        source = recognised[recognised_index]
        start = max(0.0, min(duration, float(source["start"])))
        end = max(start, min(duration, float(source["end"])))
        result[index] = {"text": script_tokens[index]["text"], "start": start, "end": end}

    index = 0
    while index < len(script_tokens):
        if result[index] is not None:
            index += 1
            continue
        run_start = index
        while index < len(script_tokens) and result[index] is None:
            index += 1
        run_end = index
        left_end = float(result[run_start - 1]["end"]) if run_start and result[run_start - 1] else 0.0
        right_start = float(result[run_end]["start"]) if run_end < len(result) and result[run_end] else duration
        right_start = max(left_end, min(duration, right_start))
        run_tokens = script_tokens[run_start:run_end]
        weights = [max(1.0, float(len(token["normal"]))) for token in run_tokens]
        total_weight = sum(weights) or 1.0
        available = right_start - left_end
        if available <= 0.0:
            available = max(0.04 * len(run_tokens), min(duration, 0.04 * len(run_tokens)))
            left_end = max(0.0, min(duration - available, right_start - available))
        cursor = left_end
        for offset, (token, weight) in enumerate(zip(run_tokens, weights)):
            span = available * weight / total_weight
            start = cursor
            end = right_start if offset == len(run_tokens) - 1 else min(right_start, cursor + span)
            result[run_start + offset] = {"text": token["text"], "start": start, "end": max(start, end)}
            cursor = end
    return [word for word in result if word is not None]


def _group_words(words: list[dict[str, Any]], max_words: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        punctuation_break = bool(re.search(r"[.!?;:]$", word["text"]))
        if len(current) >= max_words or punctuation_break:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _ass_time(seconds: float) -> str:
    total_cs = max(0, round(seconds * 100))
    hours, remainder = divmod(total_cs, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds_value, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds_value:02d}.{centiseconds:02d}"


def _ass_colour(value: str) -> str:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    red, green, blue = clean[0:2], clean[2:4], clean[4:6]
    return f"&H00{blue}{green}{red}&"


def _ass_colour_with_alpha(value: str, alpha: int = 0) -> str:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    red, green, blue = clean[0:2], clean[2:4], clean[4:6]
    return f"&H{max(0, min(255, alpha)):02X}{blue}{green}{red}&"


def _ass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _word_line(group: list[dict[str, Any]], active_index: int | None, style: dict[str, Any]) -> str:
    parts: list[str] = []
    primary = _ass_colour(style["primary_color"])
    active = _ass_colour(style["active_color"])
    for index, word in enumerate(group):
        display = word["text"].upper() if style.get("uppercase") else word["text"]
        display = _ass_escape(display)
        if index == active_index:
            effect = style.get("effect", style.get("animation", "none"))
            scale = "\\fscx108\\fscy108" if effect == "pop" else "\\fscx106\\fscy112" if effect in {"bounce", "lift"} else ""
            underline = "\\u1" if effect == "underline" else ""
            stroke = f"\\3c{active}\\bord3" if effect == "stroke" else ""
            glow = f"\\3c{active}\\bord5\\blur4" if effect == "glow" else ""
            marker = f"\\c&H00110F0E&\\3c{active}\\bord7" if effect == "marker" else ""
            reset = f"\\c{primary}\\3c{_ass_colour(style['outline_color'])}\\bord{style['outline']}\\blur0\\b0\\u0\\fscx100\\fscy100"
            parts.append(f"{{\\c{active}\\b1{scale}{underline}{stroke}{glow}{marker}}}{display}{{{reset}}}")
        else:
            parts.append(display)
    return " ".join(parts)


def build_ass(
    words: list[dict[str, Any]],
    style_id: str,
    words_per_group: int | None = None,
    style_config: dict[str, Any] | None = None,
) -> tuple[str, list[list[dict[str, Any]]]]:
    style = get_caption_style(style_id, style_config)
    group_limit = max(1, min(8, words_per_group or int(style["max_words"])))
    groups = _group_words(words, group_limit)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "\n[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Caption,{font},{size},{primary},{primary},{outline},{back},{bold},0,0,0,100,100,0,0,{border},{outline_width},{shadow},2,40,40,{margin},1".format(
            font=style["font_name"],
            size=style["font_size"],
            primary=_ass_colour_with_alpha(style["primary_color"]),
            outline=_ass_colour_with_alpha(style["outline_color"]),
            back=_ass_colour_with_alpha(style["back_color"], 255 - round(255 * style.get("back_opacity", 100) / 100)),
            bold=-1 if style["bold"] else 0,
            border=style["border_style"],
            outline_width=style["outline"],
            shadow=style["shadow"],
            margin=style["margin_v"],
        ),
        "\n[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for group in groups:
        if not group:
            continue
        if style.get("animation") == "none" and not style.get("active_word"):
            lines.append(f"Dialogue: 0,{_ass_time(group[0]['start'])},{_ass_time(group[-1]['end'])},Caption,,0,0,0,,{_word_line(group, None, style)}")
            continue
        for index, word in enumerate(group):
            end = group[index + 1]["start"] if index + 1 < len(group) else group[-1]["end"]
            start = float(word["start"])
            end = max(float(word["end"]), float(end), start + 0.04)
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,{_word_line(group, index, style)}")
    return "\n".join(lines) + "\n", groups


def _normalise_timed_words(words: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in words:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, min(duration, float(item.get("start", 0.0))))
        end = max(start, min(duration, float(item.get("end", start))))
        result.append({"text": text, "start": start, "end": end})
    return result


def prepare_caption_timing(
    video_path: Path,
    transcript: str = "",
    caption_source: str = "script",
    language: str = "",
    output_script: str = "native",
) -> dict[str, Any]:
    duration = _probe_duration(video_path)
    source = (caption_source or "script").strip().lower()
    if source not in {"script", "transcribe"}:
        raise ValueError("caption_source must be script or transcribe")
    with tempfile.TemporaryDirectory(prefix="caption-timing-", dir=str(video_path.parent)) as temp_dir:
        audio_path = Path(temp_dir) / "audio.wav"
        recognised: list[dict[str, Any]] = []
        detected_language: str | None = None
        language_probability: float | None = None
        try:
            _extract_audio(video_path, audio_path)
            recognised, detected_language, language_probability = _transcribe_words_with_metadata(audio_path, language)
        except (subprocess.CalledProcessError, RuntimeError):
            if source == "transcribe":
                raise
        if source == "transcribe":
            if not recognised:
                raise RuntimeError("No speech words were detected in the uploaded recording")
            words = recognised
        elif transcript.strip():
            words = _align_script_to_words(transcript.strip(), recognised, duration)
        elif recognised:
            words = recognised
        else:
            raise ValueError("Provide a transcript or use caption_source=transcribe")
    native_words = _normalise_timed_words(words, duration)
    display_words = _display_words(native_words, output_script)
    native_transcript = " ".join(str(word["text"]) for word in native_words)
    display_transcript = " ".join(str(word["text"]) for word in display_words)
    return {
        "caption_source": source,
        "duration": duration,
        "word_count": len(display_words),
        "words": display_words,
        "native_words": native_words,
        "native_transcript": native_transcript,
        "transcript": display_transcript,
        "detected_language": detected_language,
        "language_probability": language_probability,
        "output_script": (output_script or "native").strip().lower(),
    }


def render_caption(
    video_path: Path,
    output_path: Path,
    transcript: str = "",
    caption_source: str = "script",
    style_id: str = "pop",
    language: str = "",
    words_per_group: int | None = None,
    words: list[dict[str, Any]] | None = None,
    style_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    style = get_caption_style(style_id, style_config)
    duration = _probe_duration(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source = (caption_source or "script").strip().lower()
    if source not in {"script", "transcribe"}:
        raise ValueError("caption_source must be script or transcribe")

    if words is None:
        timing = prepare_caption_timing(video_path, transcript, source, language)
        words = timing["words"]
    else:
        words = _normalise_timed_words(words, duration)
        if not words:
            raise ValueError("Timed caption words cannot be empty")

    ass_text, groups = build_ass(words, style_id, words_per_group, style_config)
    with tempfile.TemporaryDirectory(prefix="caption-", dir=str(output_path.parent)):
        ass_path = output_path.with_suffix(".ass")
        words_path = output_path.with_suffix(".json")
        ass_path.write_text(ass_text, encoding="utf-8")
        words_path.write_text(json.dumps({"style": style_id, "source": source, "duration": duration, "words": words, "groups": groups, "style_config": style_config or {}}, indent=2), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _ffmpeg_binary()
        subprocess.run(
            [
                ffmpeg, "-y", "-i", str(video_path), "-vf", f"ass={ass_path.name}",
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", output_path.name,
            ],
            cwd=str(output_path.parent),
            check=True,
            capture_output=True,
            text=True,
        )
    return {
        "video_path": str(output_path),
        "ass_path": str(output_path.with_suffix(".ass")),
        "words_path": str(output_path.with_suffix(".json")),
        "style": style_id,
        "style_label": style["label"],
        "caption_source": source,
        "word_count": len(words),
        "duration": duration,
        "words": words,
    }