"""
Template Renderer — generates pixel-perfect ad images from HTML/CSS templates.

Uses Playwright as a headless screenshotting engine. Templates are plain
HTML/CSS with {{placeholder}} variables. The renderer injects brand fonts,
colors, copy, and any extended context, then screenshots to PNG.

Supports both the flat template layout (meta_feed.html) for backward
compatibility and the new subdirectory layout (feed_1080x1080/headline_hero.html)
for multi-variant generation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import tempfile
from pathlib import Path
from typing import Optional
import uuid

from engine.brand import BRAND_DIR, COLORS, LOGOS, LOGOS_SVG, FONT_FILES


TEMPLATE_DIR = Path(__file__).parent / "templates"
DATA_DIR = Path("data")
ASSETS_DIR = DATA_DIR / "creatives" / "rendered"

# Maps template identifiers to (width, height) viewport sizes.
# Supports both flat names (backward compat) and subdir/layout names.
TEMPLATE_SIZES = {
    # Flat (backward compat)
    "meta_feed": (1080, 1080),
    "meta_story": (1080, 1920),
    "google_300x250": (300, 250),
    "google_728x90": (728, 90),
    "google_160x600": (160, 600),
    # Subdirectory layouts
    "feed_1080x1080/headline_hero": (1080, 1080),
    "feed_1080x1080/split_screen": (1080, 1080),
    "feed_1080x1080/stat_callout": (1080, 1080),
    "feed_1080x1080/testimonial": (1080, 1080),
    "story_1080x1920/full_bleed": (1080, 1920),
    "story_1080x1920/swipe_up": (1080, 1920),
    "display_1200x628/responsive": (1200, 628),
    # New templates (G4)
    "meta_carousel_frame/card": (1080, 1080),
    "google_728x90/leaderboard": (728, 90),
    "google_160x600/skyscraper": (160, 600),
}

COLOR_SCHEMES = {
    "light": {
        "background_color": COLORS["warm_light"],
        "headline_color": COLORS["midnight"],
        "body_color": COLORS["deep_night"],
        "cta_background": COLORS["midnight"],
        "cta_text_color": "#FFFFFF",
        "accent_color": COLORS["sunset_glow"],
        "logo_variant": "primary_dark",
        "logomark_variant": "logomark_dark",
    },
    "dark": {
        "background_color": COLORS["midnight"],
        "headline_color": "#FFFFFF",
        "body_color": COLORS["warm_light"],
        "cta_background": COLORS["sunset_glow"],
        "cta_text_color": COLORS["deep_night"],
        "accent_color": COLORS["afterglow"],
        "logo_variant": "primary_light",
        "logomark_variant": "logomark_light",
    },
    "warm": {
        "background_color": COLORS["daylight"],
        "headline_color": COLORS["deep_night"],
        "body_color": COLORS["midnight"],
        "cta_background": COLORS["afterglow"],
        "cta_text_color": "#FFFFFF",
        "accent_color": COLORS["sunset_glow"],
        "logo_variant": "primary_dark",
        "logomark_variant": "logomark_dark",
    },
    "accent": {
        "background_color": COLORS["deep_night"],
        "headline_color": COLORS["sunset_glow"],
        "body_color": "#FFFFFF",
        "cta_background": COLORS["sunset_glow"],
        "cta_text_color": COLORS["deep_night"],
        "accent_color": COLORS["afterglow"],
        "logo_variant": "primary_light",
        "logomark_variant": "logomark_light",
    },
}

# Default values for optional template variables so templates
# render cleanly even if a field isn't supplied.
_DEFAULT_CONTEXT = {
    "stat_number": "2",       # default: "2 hrs saved/day" if not specified
    "stat_unit": "hrs saved\nper day",
    "attribution": "",
    "badge_text": "New",
}


def _resolve_template_file(template: str) -> Path:
    """
    Resolve a template identifier to a file path.

    Handles cases:
      1. Subdir layout:  "feed_1080x1080/headline_hero"
      2. New subdir layouts: "meta_carousel_frame/card", "google_728x90/leaderboard", etc.
      3. Flat name:      "meta_feed"  (backward compat)
      4. Google display: "google_300x250" → google_display.html with layout param
    """
    if "/" in template:
        candidate = TEMPLATE_DIR / f"{template}.html"
        if candidate.exists():
            return candidate
        raise ValueError(f"Template not found: {candidate}")

    # Flat google names — map to flat file for backward compat
    if template in ("google_300x250",):
        return TEMPLATE_DIR / "google_display.html"

    candidate = TEMPLATE_DIR / f"{template}.html"
    if candidate.exists():
        return candidate
    raise ValueError(f"Template not found: {candidate}")


def _run_async(coro):
    """Run an async coroutine from synchronous code, even if an event loop exists."""
    try:
        asyncio.get_running_loop()
        # Already in an async context — run in a thread to avoid nested loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class TemplateRenderer:
    """
    Renders HTML/CSS ad templates to PNG using Playwright (headless Chromium).

    Usage:
        renderer = TemplateRenderer()
        path = renderer.render(
            headline="Your notes, done.",
            body="JotPsych writes your clinical notes in 3 minutes.",
            cta="Try Free",
            template="feed_1080x1080/headline_hero",
            color_scheme="dark",
        )
    """

    def __init__(self):
        self._browser = None
        self._playwright = None
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public sync API
    # ------------------------------------------------------------------

    def render(
        self,
        headline: str,
        body: str,
        cta: str,
        template: str = "meta_feed",
        color_scheme: str = "light",
        custom_colors: Optional[dict] = None,
        context: Optional[dict] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        Render an ad template to PNG.

        Args:
            headline:        Headline text (also used as quote text in testimonial)
            body:            Body copy text
            cta:             CTA button text
            template:        Template identifier — flat or "subdir/layout"
            color_scheme:    Preset color scheme (light, dark, warm, accent)
            custom_colors:   Override specific color variables
            context:         Extra template variables (stat_number, attribution, etc.)
            output_filename: Custom filename; auto-generated UUID if omitted

        Returns:
            Absolute path to the rendered PNG file.
        """
        # Each sync render() call gets its own browser session.
        # The browser is bound to an asyncio event loop; reusing it across
        # separate _run_async() calls (each with a new loop) causes hangs.
        async def _render_and_close():
            try:
                return await self._render_async(
                    headline, body, cta, template, color_scheme,
                    custom_colors, context, output_filename,
                )
            finally:
                await self._close()

        return _run_async(_render_and_close())

    def render_to_html(
        self,
        headline: str,
        body: str,
        cta: str,
        template: str = "meta_feed",
        color_scheme: str = "light",
        custom_colors: Optional[dict] = None,
        context: Optional[dict] = None,
        brand_base_url: str = "/brand",
    ) -> str:
        """
        Return the fully-substituted HTML string for a template — no screenshot.
        Used by the dashboard template-preview API so the frontend can embed
        the rendered ad HTML in an iframe without Playwright.

        Assets (fonts, logos) are served via HTTP using brand_base_url
        instead of file:// paths, so the browser can load them normally.
        """
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["light"]).copy()
        if custom_colors:
            colors.update(custom_colors)

        template_file = _resolve_template_file(template)
        width, height = TEMPLATE_SIZES.get(template, (1080, 1080))
        html_content = template_file.read_text()

        # Build HTTP-relative logo and font paths instead of file:// URLs
        logo_key = colors.get("logo_variant", "primary_dark")
        logomark_key = colors.get("logomark_variant", "logomark_dark")

        logo_rel = Path(LOGOS.get(logo_key, LOGOS["primary_dark"]))
        logomark_rel = Path(LOGOS.get(logomark_key, LOGOS["logomark_dark"]))
        font_archivo_rel = Path(FONT_FILES["archivo"])
        font_inter_rel = Path(FONT_FILES["inter"])

        logo_url = f"{brand_base_url}/{logo_rel.relative_to(BRAND_DIR)}"
        logomark_url = f"{brand_base_url}/{logomark_rel.relative_to(BRAND_DIR)}"
        font_archivo_url = f"{brand_base_url}/{font_archivo_rel.relative_to(BRAND_DIR)}"
        font_inter_url = f"{brand_base_url}/{font_inter_rel.relative_to(BRAND_DIR)}"

        layout = ""
        if template.startswith("google_"):
            layout = template.replace("google_", "")

        # Truncate body for on-image rendering (full body goes in Meta primary_text)
        image_body = _truncate_body_for_image(body)

        replacements = {
            "{{headline}}": _escape_html(headline),
            "{{body}}": _escape_html(image_body),
            "{{cta}}": _escape_html(cta),
            "{{logo_path}}": logo_url,
            "{{logomark_path}}": logomark_url,
            "{{font_path_archivo}}": font_archivo_url,
            "{{font_path_inter}}": font_inter_url,
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

        return html_content

    def render_batch(
        self,
        variants: list[dict],
        template: str = "meta_feed",
        color_scheme: str = "light",
    ) -> list[str]:
        """
        Render multiple variants in a single browser session.

        Each dict should have at minimum: headline, body|primary_text, cta|cta_button.
        Optional keys: stat_number, stat_unit, attribution, badge_text, color_scheme.
        """
        return _run_async(
            self._render_batch_async(variants, template, color_scheme)
        )

    # ------------------------------------------------------------------
    # Async internals
    # ------------------------------------------------------------------

    async def _render_async(
        self,
        headline: str,
        body: str,
        cta: str,
        template: str,
        color_scheme: str,
        custom_colors: Optional[dict],
        context: Optional[dict],
        output_filename: Optional[str],
    ) -> str:
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["light"]).copy()
        if custom_colors:
            colors.update(custom_colors)

        template_file = _resolve_template_file(template)
        width, height = TEMPLATE_SIZES.get(template, (1080, 1080))

        html_content = template_file.read_text()

        # Resolve asset paths
        logo_path = Path(LOGOS.get(colors["logo_variant"], LOGOS["primary_dark"])).resolve()
        logomark_path = Path(LOGOS.get(
            colors.get("logomark_variant", "logomark_dark"),
            LOGOS["logomark_dark"],
        )).resolve()
        font_archivo = Path(FONT_FILES["archivo"]).resolve()
        font_inter = Path(FONT_FILES["inter"]).resolve()

        # Google display needs a layout param
        layout = ""
        if template.startswith("google_"):
            layout = template.replace("google_", "")

        # Truncate body at word boundary so the template never shows CSS ellipsis
        body = _truncate_body(body)

        # Truncate body for on-image rendering (full body goes in Meta primary_text)
        image_body = _truncate_body_for_image(body)

        # Build replacement map
        replacements = {
            "{{headline}}": _escape_html(headline),
            "{{body}}": _escape_html(image_body),
            "{{cta}}": _escape_html(cta),
            "{{logo_path}}": f"file://{logo_path}",
            "{{logomark_path}}": f"file://{logomark_path}",
            "{{font_path_archivo}}": f"file://{font_archivo}",
            "{{font_path_inter}}": f"file://{font_inter}",
            "{{width}}": str(width),
            "{{height}}": str(height),
            "{{layout}}": layout,
        }

        # Color variables
        for key, value in colors.items():
            if key in ("logo_variant", "logomark_variant"):
                continue
            replacements[f"{{{{{key}}}}}"] = value

        # Extended context with defaults
        merged_context = {**_DEFAULT_CONTEXT, **(context or {})}
        for key, value in merged_context.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder not in replacements:
                replacements[placeholder] = _escape_html(str(value))

        for placeholder, value in replacements.items():
            html_content = html_content.replace(placeholder, value)

        # Render via temp file so file:// asset URLs (logos, fonts) load correctly.
        # set_content() uses about:blank as base, which Chromium blocks file:// from.
        browser = await self._get_browser()
        page = await browser.new_page(viewport={"width": width, "height": height})
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(html_content)
            tmp_path = tmp.name
        await page.goto(f"file://{tmp_path}")
        await page.wait_for_load_state("networkidle")

        if output_filename:
            filename = output_filename if output_filename.endswith(".png") else f"{output_filename}.png"
        else:
            safe_template = template.replace("/", "_")
            filename = f"{safe_template}_{uuid.uuid4().hex[:8]}.png"

        output_path = ASSETS_DIR / filename
        await page.screenshot(path=str(output_path), type="png")
        await page.close()

        # Clean up temp HTML file
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass

        return str(output_path)

    async def _render_batch_async(
        self,
        variants: list[dict],
        template: str,
        color_scheme: str,
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
                output_filename=None,
            )
            paths.append(path)

        await self._close()
        return paths

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_available_templates(self) -> list[str]:
        return list(TEMPLATE_SIZES.keys())

    def get_available_color_schemes(self) -> list[str]:
        return list(COLOR_SCHEMES.keys())


def _escape_html(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _truncate_body_for_image(text: str, max_chars: int = 80) -> str:
    """
    Truncate body copy for on-image rendering. Keep only the first 1-2 short
    sentences. The full body goes in Meta's primary_text field below the image;
    the rendered image should be clean and minimal.
    """
    if not text or len(text) <= max_chars:
        return text

    # Try to end at a sentence boundary
    for sep in [". ", "! ", "? ", "\n"]:
        idx = text.find(sep)
        if 0 < idx < max_chars:
            return text[:idx + 1].strip()

    # No sentence break found — cut at word boundary
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated.rstrip(".,;:") + "."


def _truncate_body(text: str, max_chars: int = 280) -> str:
    """Truncate body copy to fit the template. Prefer ending at a complete sentence."""
    if len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    # Try to end at a sentence boundary (., !, ?)
    for punct in [".", "!", "?"]:
        last_sent = chunk.rfind(punct)
        if last_sent > max_chars // 2:
            return chunk[:last_sent + 1]
    # Fall back to word boundary
    last_space = chunk.rfind(" ")
    if last_space > max_chars // 2:
        return chunk[:last_space].rstrip(" ,;:")


# ------------------------------------------------------------------
# Convenience function
# ------------------------------------------------------------------

def render_sync(
    headline: str,
    body: str,
    cta: str,
    template: str = "meta_feed",
    color_scheme: str = "light",
    context: Optional[dict] = None,
) -> str:
    """One-off render. Creates renderer, renders, cleans up."""
    renderer = TemplateRenderer()
    try:
        return renderer.render(headline, body, cta, template, color_scheme, context=context)
    finally:
        _run_async(renderer._close())
