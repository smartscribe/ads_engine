"""
Video Renderer — captures CSS animations from HTML templates as MP4 video.

Uses Playwright's built-in recordVideo to capture the template rendering
as a WebM file, then converts to MP4 via ffmpeg. Templates with @keyframes
CSS animations produce actual motion (text reveals, fade-ins, bouncing CTAs)
without any AI video generation.

Typical output: 4-6 second clips at 1080x1920 (Stories) or 1080x1080 (Feed).
Even simple CSS motion outperforms static images on Meta by 20-30% CTR.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import uuid

from engine.brand import COLORS, LOGOS, FONT_FILES
from engine.generation.template_renderer import (
    TEMPLATE_DIR,
    TEMPLATE_SIZES,
    COLOR_SCHEMES,
    _DEFAULT_CONTEXT,
    _escape_html,
    _resolve_template_file,
)


ASSETS_DIR = Path("data") / "creatives" / "rendered"
VIDEO_DIR = ASSETS_DIR / "video"


def _run_async(coro):
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class VideoRenderer:
    """
    Renders HTML templates with CSS animations to MP4 video.

    Workflow:
      1. Open Playwright page with recordVideo enabled
      2. Set HTML content (triggers CSS @keyframes)
      3. Wait for animation_duration_ms
      4. Close page → Playwright saves WebM
      5. Convert WebM → MP4 via ffmpeg (H.264, AAC silent)

    Usage:
        renderer = VideoRenderer()
        path = renderer.render(
            headline="2 hours of charting. Or 3 minutes.",
            body="JotPsych writes your clinical notes automatically.",
            cta="Try Free",
            template="story_1080x1920/full_bleed",
            color_scheme="dark",
            duration_ms=5000,
        )
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    async def _get_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch()
        return self._browser

    async def _close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def render(
        self,
        headline: str,
        body: str,
        cta: str,
        template: str = "story_1080x1920/full_bleed",
        color_scheme: str = "dark",
        custom_colors: Optional[dict] = None,
        context: Optional[dict] = None,
        duration_ms: int = 5000,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        Render an animated HTML template to MP4.

        Args:
            headline:        Headline text
            body:            Body copy
            cta:             CTA button text
            template:        Template identifier (should have CSS animations)
            color_scheme:    Color scheme preset
            custom_colors:   Override colors
            context:         Extra template variables
            duration_ms:     How long to record (ms). Should cover full animation.
            output_filename: Custom output name (without extension)

        Returns:
            Path to the rendered MP4 file.
        """
        return _run_async(
            self._render_async(
                headline, body, cta, template, color_scheme,
                custom_colors, context, duration_ms, output_filename,
            )
        )

    def render_batch(
        self,
        variants: list[dict],
        template: str = "story_1080x1920/full_bleed",
        color_scheme: str = "dark",
        duration_ms: int = 5000,
    ) -> list[str]:
        """Render multiple animated variants to MP4."""
        return _run_async(
            self._render_batch_async(variants, template, color_scheme, duration_ms)
        )

    async def _render_async(
        self,
        headline: str,
        body: str,
        cta: str,
        template: str,
        color_scheme: str,
        custom_colors: Optional[dict],
        context: Optional[dict],
        duration_ms: int,
        output_filename: Optional[str],
    ) -> str:
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["light"]).copy()
        if custom_colors:
            colors.update(custom_colors)

        template_file = _resolve_template_file(template)
        width, height = TEMPLATE_SIZES.get(template, (1080, 1920))

        html_content = template_file.read_text()

        logo_path = Path(LOGOS.get(colors["logo_variant"], LOGOS["primary_dark"])).resolve()
        logomark_path = Path(LOGOS.get(
            colors.get("logomark_variant", "logomark_dark"),
            LOGOS["logomark_dark"],
        )).resolve()
        font_archivo = Path(FONT_FILES["archivo"]).resolve()
        font_inter = Path(FONT_FILES["inter"]).resolve()

        layout = ""
        if template.startswith("google_"):
            layout = template.replace("google_", "")

        replacements = {
            "{{headline}}": _escape_html(headline),
            "{{body}}": _escape_html(body),
            "{{cta}}": _escape_html(cta),
            "{{logo_path}}": f"file://{logo_path}",
            "{{logomark_path}}": f"file://{logomark_path}",
            "{{font_path_archivo}}": f"file://{font_archivo}",
            "{{font_path_inter}}": f"file://{font_inter}",
            "{{width}}": str(width),
            "{{height}}": str(height),
            "{{layout}}": layout,
        }

        for key, value in colors.items():
            if key in ("logo_variant", "logomark_variant"):
                continue
            replacements[f"{{{{{key}}}}}"] = value

        merged_context = {**_DEFAULT_CONTEXT, **(context or {})}
        for key, value in merged_context.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder not in replacements:
                replacements[placeholder] = _escape_html(str(value))

        for placeholder, value in replacements.items():
            html_content = html_content.replace(placeholder, value)

        # Record video via Playwright
        tmp_dir = tempfile.mkdtemp(prefix="pw_video_")
        browser = await self._get_browser()

        browser_context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=tmp_dir,
            record_video_size={"width": width, "height": height},
        )

        page = await browser_context.new_page()
        await page.set_content(html_content)
        await page.wait_for_load_state("networkidle")

        # Let the CSS animations play out
        await page.wait_for_timeout(duration_ms)

        # Close page + context to finalize the video file
        video = page.video
        await page.close()
        await browser_context.close()

        webm_path = await video.path()

        # Generate output path
        if output_filename:
            mp4_name = output_filename if output_filename.endswith(".mp4") else f"{output_filename}.mp4"
        else:
            safe_template = template.replace("/", "_")
            mp4_name = f"{safe_template}_{uuid.uuid4().hex[:8]}.mp4"

        mp4_path = VIDEO_DIR / mp4_name

        # Convert WebM → MP4 via ffmpeg
        _webm_to_mp4(str(webm_path), str(mp4_path), duration_s=duration_ms / 1000)

        # Cleanup temp dir
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return str(mp4_path)

    async def _render_batch_async(
        self,
        variants: list[dict],
        template: str,
        color_scheme: str,
        duration_ms: int,
    ) -> list[str]:
        paths = []
        for variant in variants:
            per_variant_scheme = variant.get("color_scheme", color_scheme)
            per_variant_template = variant.get("template", template)
            path = await self._render_async(
                headline=variant.get("headline", ""),
                body=variant.get("body", variant.get("primary_text", "")),
                cta=variant.get("cta", variant.get("cta_button", "Learn More")),
                template=per_variant_template,
                color_scheme=per_variant_scheme,
                custom_colors=None,
                context=variant.get("context"),
                duration_ms=duration_ms,
                output_filename=None,
            )
            paths.append(path)

        await self._close()
        return paths

    def get_animated_templates(self) -> list[str]:
        """Templates that have CSS animations and benefit from video capture."""
        return [
            "story_1080x1920/full_bleed",
            "story_1080x1920/swipe_up",
        ]


def _webm_to_mp4(webm_path: str, mp4_path: str, duration_s: float = 5.0) -> None:
    """
    Convert WebM to MP4 using ffmpeg.

    Uses H.264 (libx264) for broad compatibility with Meta and Google ad platforms.
    Adds a silent audio track since some platforms reject video without audio.
    """
    if not shutil.which("ffmpeg"):
        # ffmpeg not installed — keep the WebM and rename
        out = Path(mp4_path)
        shutil.copy2(webm_path, out.with_suffix(".webm"))
        print(f"[video_renderer] ffmpeg not found; saved WebM instead: {out.with_suffix('.webm')}")
        return

    cmd = [
        "ffmpeg", "-y",
        "-i", webm_path,
        "-t", str(duration_s),
        # Silent audio track (platforms often require audio)
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-shortest",
        # H.264 encoding — max compatibility
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        mp4_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[video_renderer] ffmpeg error: {result.stderr[:500]}")
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:200]}")

    print(f"[video_renderer] Video saved: {mp4_path}")
