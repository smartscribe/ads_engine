"""
Transcribe the 6 Aryan videos via Deepgram Nova-3, render TikTok-style
caption PNGs per cue, and burn them into new mp4s via ffmpeg overlay.

Why PIL+overlay (not ass/subtitle filter): Homebrew ffmpeg 8.1 on this
machine is built without libass/libfreetype, so the `ass` and `subtitles`
filters are not available. The `overlay` filter is universally present,
so we render each cue as a transparent PNG with PIL and composite via
timed overlays.

Pipeline per video:
  1. POST mp4 to Deepgram /v1/listen?model=nova-3&punctuate=true&smart_format=true
  2. Parse word-level timestamps
  3. Chunk into 1-3 word cues (<=1.2s each, break on punctuation/pauses)
  4. Render each cue as a transparent PNG (Arial Black, white + black stroke)
  5. ffmpeg: input video + one looped PNG per cue, chain overlay filters
     with `enable='between(t,start,end)'` per cue, -shortest to bound loops

Outputs:
  - data/captioned-videos/{stem}.captioned.mp4
  - data/captioned-videos/{stem}/cue_NN.png (kept for debugging)
  - data/captioned-videos/transcripts.json
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

SOURCE_DIR = Path("/Users/nathanpeereboom/Downloads/ugc_wild_video_ads (1)")
OUT_DIR = Path("data/captioned-videos")

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_PARAMS = {
    "model": "nova-3",
    "punctuate": "true",
    "smart_format": "true",
    "language": "en",
}

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

# Caption styling — auto-fits to video width
FONT_SIZE_MAX = 88
FONT_SIZE_MIN = 48
SAFE_WIDTH_FRACTION = 0.86  # text bbox must fit within 86% of video width
STROKE_WIDTH = 6
TEXT_COLOR = (255, 255, 255, 255)
STROKE_COLOR = (0, 0, 0, 255)
SHADOW_OFFSET = (0, 5)
SHADOW_COLOR = (0, 0, 0, 180)
MARGIN_FROM_BOTTOM_FRACTION = 0.30  # overlay sits 30% of video height above bottom

MAX_WORDS_PER_CUE = 2
MAX_CUE_DUR = 1.1
MIN_CUE_DUR = 0.35
CUE_GAP_AT_PAUSE = 0.35

# Brand-name normalization: Deepgram hears JotPsych as Jot Sykes / Jot psych /
# Jot's like / Jotpsych. Always collapse to a single token "JotPsych".
BRAND_CANONICAL = "JotPsych"
BRAND_PATTERNS = [
    r"jot\s+sykes",
    r"jot\s+psych",
    r"jot'?s?\s+like",
    r"jot\s+tech",
    r"jot\s+site",
    r"jotpsych",
]


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Cue:
    text: str
    start: float
    end: float


def transcribe(mp4: Path, api_key: str) -> list[Word]:
    with mp4.open("rb") as f:
        r = requests.post(
            DEEPGRAM_URL,
            params=DEEPGRAM_PARAMS,
            headers={"Authorization": f"Token {api_key}", "Content-Type": "video/mp4"},
            data=f.read(),
            timeout=120,
        )
    r.raise_for_status()
    alt = r.json()["results"]["channels"][0]["alternatives"][0]
    words = []
    for w in alt.get("words", []):
        text = w.get("punctuated_word") or w.get("word", "")
        words.append(Word(text=text, start=float(w["start"]), end=float(w["end"])))
    return normalize_brand(words)


def normalize_brand(words: list[Word]) -> list[Word]:
    """Collapse JotPsych mis-hearings into a single Word with merged timestamps."""
    import re

    # Build a lowercase joined string with char-to-word-index map
    lowered = " ".join(re.sub(r"[^a-z']+", "", w.text.lower()) for w in words)
    # char→word index
    char_to_word = []
    for wi, w in enumerate(words):
        token = re.sub(r"[^a-z']+", "", w.text.lower())
        for _ in token:
            char_to_word.append(wi)
        char_to_word.append(wi)  # trailing space

    matches: list[tuple[int, int]] = []  # (start_word_idx, end_word_idx inclusive)
    for pat in BRAND_PATTERNS:
        for m in re.finditer(pat, lowered):
            if not char_to_word:
                continue
            s_idx = char_to_word[m.start()] if m.start() < len(char_to_word) else None
            e_idx = char_to_word[m.end() - 1] if (m.end() - 1) < len(char_to_word) else None
            if s_idx is None or e_idx is None:
                continue
            matches.append((s_idx, e_idx))

    if not matches:
        return words

    # Build collapsed list, skipping words inside a match range and emitting one
    # merged Word per match.
    matches.sort()
    merged_spans: list[tuple[int, int]] = []
    for s, e in matches:
        if merged_spans and s <= merged_spans[-1][1] + 1:
            merged_spans[-1] = (merged_spans[-1][0], max(e, merged_spans[-1][1]))
        else:
            merged_spans.append((s, e))

    out: list[Word] = []
    i = 0
    span_idx = 0
    while i < len(words):
        if span_idx < len(merged_spans) and i == merged_spans[span_idx][0]:
            s, e = merged_spans[span_idx]
            trailing_punct = ""
            last_text = words[e].text.rstrip()
            for ch in reversed(last_text):
                if not ch.isalnum() and ch != "'":
                    trailing_punct = ch + trailing_punct
                else:
                    break
            out.append(Word(
                text=BRAND_CANONICAL + trailing_punct,
                start=words[s].start,
                end=words[e].end,
            ))
            i = e + 1
            span_idx += 1
        else:
            out.append(words[i])
            i += 1
    return out


def chunk_words(words: list[Word]) -> list[Cue]:
    cues: list[Cue] = []
    cur: list[Word] = []

    def flush():
        if not cur:
            return
        start = cur[0].start
        end = max(cur[-1].end, start + MIN_CUE_DUR)
        text = " ".join(w.text for w in cur).upper()
        cues.append(Cue(text=text, start=start, end=end))

    for w in words:
        if not cur:
            cur = [w]
            continue
        chunk_start = cur[0].start
        prev_end = cur[-1].end
        dur_if_added = w.end - chunk_start
        gap = w.start - prev_end
        ends_with_punct = cur[-1].text.rstrip().endswith((".", "!", "?", ","))

        if (
            len(cur) >= MAX_WORDS_PER_CUE
            or dur_if_added > MAX_CUE_DUR
            or gap > CUE_GAP_AT_PAUSE
            or ends_with_punct
        ):
            flush()
            cur = [w]
        else:
            cur.append(w)
    flush()
    return cues


def probe_video_size(mp4: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
         str(mp4)],
        capture_output=True, text=True, check=True,
    )
    w, h = r.stdout.strip().split("x")
    return int(w), int(h)


def render_cue_png(cue_text: str, video_w: int, out_path: Path) -> None:
    """Render a transparent PNG with bold white text, black stroke + drop shadow.

    Auto-fits font size so the stroked bbox stays inside SAFE_WIDTH_FRACTION
    of the video width. PNG itself is trimmed to content width + small pad,
    so ffmpeg overlay can center via x=(W-w)/2 without horizontal clipping.
    """
    max_text_w = int(video_w * SAFE_WIDTH_FRACTION)

    # Binary-style shrink: start at MAX and step down 4pt until fit
    probe_img = Image.new("RGBA", (10, 10))
    pd = ImageDraw.Draw(probe_img)

    font = None
    bbox = None
    for size in range(FONT_SIZE_MAX, FONT_SIZE_MIN - 1, -2):
        f = ImageFont.truetype(FONT_PATH, size)
        b = pd.textbbox((0, 0), cue_text, font=f, stroke_width=STROKE_WIDTH)
        w = b[2] - b[0]
        if w <= max_text_w:
            font, bbox = f, b
            break
    if font is None:
        # even at MIN it overflows — use MIN and let it clip; better than nothing
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE_MIN)
        bbox = pd.textbbox((0, 0), cue_text, font=font, stroke_width=STROKE_WIDTH)

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x = STROKE_WIDTH + abs(SHADOW_OFFSET[0]) + 8
    pad_y_top = STROKE_WIDTH + 8
    pad_y_bot = STROKE_WIDTH + abs(SHADOW_OFFSET[1]) + 12

    img_w = tw + 2 * pad_x
    img_h = th + pad_y_top + pad_y_bot

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x = pad_x - bbox[0]
    y = pad_y_top - bbox[1]

    draw.text(
        (x + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1]),
        cue_text, font=font,
        fill=SHADOW_COLOR,
        stroke_width=STROKE_WIDTH, stroke_fill=SHADOW_COLOR,
    )
    draw.text(
        (x, y),
        cue_text, font=font,
        fill=TEXT_COLOR,
        stroke_width=STROKE_WIDTH, stroke_fill=STROKE_COLOR,
    )
    img.save(out_path, "PNG")


def burn(src: Path, cues: list[Cue], png_paths: list[Path], out: Path) -> None:
    """Overlay all cue PNGs onto src with per-cue time gating, emit Meta-ready mp4."""
    # Place text at ~70% down the frame; MARGIN_FROM_BOTTOM_FRACTION controls distance
    # from the bottom edge. 0.30 = text bottom sits 30% of H above the bottom edge.
    y_expr = f"H-h-(H*{MARGIN_FROM_BOTTOM_FRACTION})"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src.resolve()),
    ]
    for png in png_paths:
        cmd += ["-loop", "1", "-i", str(png.resolve())]

    filter_parts = []
    prev_label = "0:v"
    for i, (cue, _png) in enumerate(zip(cues, png_paths)):
        input_label = f"{i+1}:v"
        out_label = "vout" if i == len(cues) - 1 else f"v{i+1}"
        filter_parts.append(
            f"[{prev_label}][{input_label}]overlay=x=(W-w)/2:y={y_expr}"
            f":enable='between(t,{cue.start:.3f},{cue.end:.3f})'[{out_label}]"
        )
        prev_label = out_label

    cmd += ["-filter_complex", ";".join(filter_parts)]
    cmd += ["-map", f"[{prev_label}]", "-map", "0:a?"]
    cmd += [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        str(out.resolve()),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    api_key = os.environ["DEEPGRAM_API_KEY"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    transcripts: dict = {}
    mp4s = sorted(SOURCE_DIR.glob("*.mp4"))
    print(f"Processing {len(mp4s)} videos\n", file=sys.stderr)

    for src in mp4s:
        stem = src.stem.replace(" ", "_")
        work_dir = OUT_DIR / stem
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        out_mp4 = OUT_DIR / f"{stem}.captioned.mp4"

        print(f"[{src.name}]", file=sys.stderr)
        print(f"  transcribe...", file=sys.stderr)
        words = transcribe(src, api_key)
        transcripts[src.name] = [
            {"text": w.text, "start": w.start, "end": w.end} for w in words
        ]
        if not words:
            print(f"  SKIP — no words transcribed", file=sys.stderr)
            continue
        print(f"  {len(words)} words", file=sys.stderr)

        cues = chunk_words(words)
        print(f"  {len(cues)} cues", file=sys.stderr)

        vw, _vh = probe_video_size(src)
        png_paths = []
        for i, cue in enumerate(cues):
            png = work_dir / f"cue_{i:02d}.png"
            render_cue_png(cue.text, vw, png)
            png_paths.append(png)

        print(f"  burning → {out_mp4.name}", file=sys.stderr)
        burn(src, cues, png_paths, out_mp4)
        print(f"  OK {out_mp4.stat().st_size // 1024}KB\n", file=sys.stderr)

    (OUT_DIR / "transcripts.json").write_text(json.dumps(transcripts, indent=2))
    print(f"\nCaptioned videos: {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
