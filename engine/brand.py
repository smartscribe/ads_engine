"""
JotPsych Brand Configuration — extracted from Brand Guidelines v1 2026.

Single source of truth for brand colors, typography, voice, and asset paths.
Used by copy agents (voice/tone), image generator (color direction), and
any future template rendering.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Asset Paths (relative to repo root)
# ---------------------------------------------------------------------------

BRAND_DIR = Path("brand")
LOGO_DIR = BRAND_DIR / "logos"

LOGOS = {
    "primary_dark": LOGO_DIR / "png/JotPsych - Primary Logo Dark.png",
    "primary_light": LOGO_DIR / "png/JotPsych - Primary Logo Light.png",
    "secondary_dark": LOGO_DIR / "png/JotPsych - Secondary Logo Dark.png",
    "secondary_light": LOGO_DIR / "png/JotPsych - Secondary Logo Light.png",
    "logomark_dark": LOGO_DIR / "png/Logomark Dark.png",
    "logomark_light": LOGO_DIR / "png/Logomark Light.png",
    "logomark_dark_square": LOGO_DIR / "png/Logomark Dark - Square Background.png",
    "logomark_light_square": LOGO_DIR / "png/Logomark Light - Square Background.png",
}

LOGOS_SVG = {
    "primary_dark": LOGO_DIR / "svg/JotPsych - Primary Logo Dark.svg",
    "primary_light": LOGO_DIR / "svg/JotPsych - Primary Logo Light.svg",
    "logomark_dark": LOGO_DIR / "svg/Logomark Dark.svg",
    "logomark_light": LOGO_DIR / "svg/Logomark Light.svg",
}

# ---------------------------------------------------------------------------
# Colors — from Brand Guidelines pp. 16-19
# ---------------------------------------------------------------------------

# Primary colors (used in logo and across all media)
COLORS = {
    "midnight": "#1C1E85",       # Deep blue — primary brand color
    "sunset_glow": "#FD96C9",    # Pink accent — secondary brand color
    "warm_light": "#FFF2F5",     # Very light pink — backgrounds, whitespace

    # Secondary colors (accents, used 3x less than primary)
    "deep_night": "#1E125E",     # Dark purple — text, deep backgrounds
    "daylight": "#FFF3C4",       # Warm cream — accents, highlights
    "afterglow": "#813FE8",      # Purple — accent, CTAs, interactive elements
}

# Color usage rules from guidelines
COLOR_USAGE = """
- Primary colors (midnight, sunset_glow, warm_light) should be used 3x more than accent colors
- Only pair colors that provide sufficient contrast between background and foreground
- Good pairings: midnight on warm_light, deep_night on daylight, white on midnight
- Never use colors outside of brand palette on logos
"""

# For image generation — color mood descriptions
COLOR_MOODS = {
    "brand_primary": "Deep midnight blue (#1C1E85) with soft pink accents (#FD96C9), light warm backgrounds (#FFF2F5)",
    "warm_earth": "Warm cream (#FFF3C4) tones with deep purple-blue (#1E125E) accents, grounded and human",
    "cool_clinical": "Clean white and midnight blue (#1C1E85), professional and trustworthy",
    "high_contrast": "Deep night (#1E125E) backgrounds with sunset glow pink (#FD96C9) highlights",
}

# ---------------------------------------------------------------------------
# Typography — from Brand Guidelines pp. 11-14
# ---------------------------------------------------------------------------

TYPOGRAPHY = {
    "heading_font": "Archivo",
    "heading_weights": ["Regular", "Medium", "Italic"],
    "heading_usage": "Headlines, subheadings, display text",

    "body_font": "Inter",
    "body_weights": ["Regular", "Medium", "Semibold"],
    "body_usage": "Paragraph text, body copy, UI text",
}

FONT_FILES = {
    "archivo": BRAND_DIR / "fonts/Archivo-VariableFont_wdth,wght.ttf",
    "archivo_italic": BRAND_DIR / "fonts/Archivo-Italic-VariableFont_wdth,wght.ttf",
    "inter": BRAND_DIR / "fonts/Inter-VariableFont_opsz,wght.ttf",
    "inter_italic": BRAND_DIR / "fonts/Inter-Italic-VariableFont_opsz,wght.ttf",
}

# ---------------------------------------------------------------------------
# Brand Voice & Identity
# ---------------------------------------------------------------------------

BRAND_VOICE = """JotPsych is a clinical AI documentation tool for behavioral health clinicians.

TONE:
- Warm but professional, like a trusted colleague, not a salesperson
- Empathetic to clinician burnout, we understand the paperwork burden
- Specific and concrete: "save 2 hours" not "save time", real scenarios not abstractions
- Confident without being pushy, we know the product works, let the value speak

AVOID:
- Em dashes. Never use em dashes in ad copy. Use periods, commas, or colons instead.
- Corporate buzzwords: "revolutionize", "leverage", "streamline", "cutting-edge", "innovative"
- AI hype: "powered by AI", "next-generation", "transform your workflow"
- Generic healthcare marketing: "in today's fast-paced healthcare environment"
- Pressure tactics: "limited time", "don't miss out", "act now"

GOOD EXAMPLES:
- "Your session ends. Your notes don't have to."
- "What would you do with 10 extra hours per week?"
- "2 hours of charting. Or 3 minutes with JotPsych."

TARGET AUDIENCE:
- Behavioral health clinicians: therapists, psychologists, psychiatrists, counselors
- SMB clinic decision-makers: practice owners, clinical directors
- Pain: drowning in documentation, taking notes home, weekend catch-up, burnout
- Desire: presence with patients, leaving on time, audit-ready notes without effort
"""

PRODUCT_DESCRIPTION = """JotPsych is an AI-powered clinical documentation tool that listens to therapy
sessions and generates complete, audit-ready clinical notes automatically.

KEY FEATURES:
- Records sessions (phone or in-room)
- Generates structured clinical notes (SOAP, DAP, progress notes)
- Applies CPT codes and ICD codes automatically
- Flags documentation risks before submission
- HIPAA-compliant end-to-end

KEY VALUE PROPS:
- Saves 1-2 hours of documentation time per day
- Notes are done before the clinician leaves the office
- Audit-ready documentation with proper coding
- Clinicians can be fully present with patients (no laptop in session)
- Reduces burnout from administrative burden
"""

# ---------------------------------------------------------------------------
# Visual Style — from Brand Guidelines pp. 20-26
# ---------------------------------------------------------------------------

VISUAL_STYLE = """
ILLUSTRATION STYLE:
- Clean, modern product UI screenshots with brand colors
- Custom illustrations/diagrams to explain complex systems simply
- Warm, approachable — not cold or corporate

BRAND PATTERNS:
- Duo-tone cube pattern (small and repeating variants)
- Repeating transparent cube pattern
- Used across web, slides, print for visual continuity

PHOTOGRAPHY DIRECTION (for ads):
- Documentary-style, not posed stock photography
- Warm lighting (golden hour, desk lamps, natural afternoon light)
- Real clinical environments: therapy rooms, home offices, small clinics
- Diverse clinicians across age, gender, ethnicity
- Color palette in environments should echo brand: warm tones, deep blues, soft pinks
- Props should include realistic clinical details (EHR screens, intake forms, clocks)

LOGO USAGE IN ADS:
- Logomark (helix) can be used as subtle watermark or corner placement
- Minimum size: 32px height for logomark, 160px width for primary logo
- Always maintain clearspace (half the logomark height)
- Dark logomark on light backgrounds, light logomark on dark backgrounds
"""


def get_brand_context_for_image_prompt() -> str:
    """Return brand-relevant context for image generation prompts."""
    return f"""BRAND COLOR DIRECTION:
Primary palette: midnight blue ({COLORS['midnight']}), sunset glow pink ({COLORS['sunset_glow']}), warm light ({COLORS['warm_light']})
Accent palette: deep night ({COLORS['deep_night']}), daylight cream ({COLORS['daylight']}), afterglow purple ({COLORS['afterglow']})
Color mood: Warm, approachable, professional. Deep blues and warm pinks. Avoid cold greys or harsh whites.

BRAND VISUAL STYLE:
- Warm, documentary-style photography
- Natural lighting: golden hour, desk lamps, soft afternoon light
- Real clinical environments, not sterile stock-photo offices
- Color grading should lean warm — amber, cream, soft blues, touch of pink
- Avoid: corporate glass offices, harsh fluorescents, cold blue-white lighting"""


def get_brand_context_for_copy_prompt() -> str:
    """Return brand-relevant context for copy generation prompts."""
    return f"""BRAND VOICE:
{BRAND_VOICE}

PRODUCT:
{PRODUCT_DESCRIPTION}"""
