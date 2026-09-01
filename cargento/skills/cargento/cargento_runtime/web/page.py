import base64
import binascii
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent

# The dashboard script is split by responsibility and concatenated in this
# order into index.html's one script slot. The parts share a single script
# scope, so order carries meaning.
APP_PARTS: tuple[str, ...] = (
    "next-boot.js",
    "next-attention.js",
    "next-notify.js",
    "next-chrome.js",
    "next-sessions.js",
    "next-projects.js",
    "next-project.js",
    "next-activity.js",
    "next-session.js",
    "next-workstream.js",
    "next-delegation.js",
    "next-controls.js",
    "next-render.js",
    "next-live.js",  # namespaced leader election starts the refresh loop last
)

# The page remains one self-contained response. Encoding the packaged font
# subsets into it avoids adding a second HTTP asset surface.
FONT_ASSETS: tuple[tuple[str, str], ...] = (
    (
        "fonts/space-grotesk-v22-vietnamese.woff2.b64",
        "{{CARGENTO_FONT_SPACE_GROTESK_V22_VIETNAMESE}}",
    ),
    (
        "fonts/space-grotesk-v22-latin-ext.woff2.b64",
        "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN_EXT}}",
    ),
    (
        "fonts/space-grotesk-v22-latin.woff2.b64",
        "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN}}",
    ),
    (
        "fonts/space-mono-v17-regular-vietnamese.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_VIETNAMESE}}",
    ),
    (
        "fonts/space-mono-v17-regular-latin-ext.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_LATIN_EXT}}",
    ),
    (
        "fonts/space-mono-v17-regular-latin.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_LATIN}}",
    ),
    (
        "fonts/space-mono-v17-bold-vietnamese.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_VIETNAMESE}}",
    ),
    (
        "fonts/space-mono-v17-bold-latin-ext.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_LATIN_EXT}}",
    ),
    (
        "fonts/space-mono-v17-bold-latin.woff2.b64",
        "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_LATIN}}",
    ),
)


def asset_path(name: str) -> Path:
    return WEB_DIR / name


def load_script() -> str:
    """Return every script part, in execution order, as one text."""
    return "".join(asset_path(name).read_text(encoding="utf-8") for name in APP_PARTS)


def load_styles() -> str:
    """Return the stylesheet with every pinned local font embedded."""
    styles = asset_path("styles.css").read_text(encoding="utf-8")
    for name, slot in FONT_ASSETS:
        if styles.count(slot) != 1:
            msg = f"styles.css must contain one {slot} slot"
            raise RuntimeError(msg)
        encoded = "".join(asset_path(name).read_text(encoding="ascii").splitlines())
        try:
            payload = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            msg = f"font asset {name} must be base64 WOFF2"
            raise RuntimeError(msg) from exc
        if not payload.startswith(b"wOF2"):
            msg = f"font asset {name} must be base64 WOFF2"
            raise RuntimeError(msg)
        styles = styles.replace(slot, f"data:font/woff2;base64,{encoded}")
    return styles


def load_page() -> bytes:
    template = asset_path("index.html").read_text(encoding="utf-8")
    if template.count("{{CARGENTO_STYLES}}") != 1:
        msg = "index.html must contain one CARGENTO_STYLES slot"
        raise RuntimeError(msg)
    if template.count("{{CARGENTO_APP}}") != 1:
        msg = "index.html must contain one CARGENTO_APP slot"
        raise RuntimeError(msg)
    styles = load_styles()
    script = load_script()
    return (
        template.replace("{{CARGENTO_STYLES}}", styles)
        .replace("{{CARGENTO_APP}}", script)
        .encode("utf-8")
    )
