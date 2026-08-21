from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent

# The dashboard script, split by responsibility and concatenated in this
# order into index.html's one script slot. The parts share a single script
# scope, so order carries meaning: shared state and the component tables
# come before the listeners and the render loop that read them.
APP_PARTS: tuple[str, ...] = (
    "spark.js",  # shared page state, rate buffers, the sparkline
    "regular.js",  # regular-mode components: badges, tiles, cards, rows
    "mode.js",  # display-mode state, its switch, and the calm ledger's mutable state
    "usage.js",  # the usage band, configure, and the disclosure modal
    "controls.js",  # the stop control, stopped panel, and mode bar
    "calm.js",  # the calm ledger: tables, actions, listeners, renderers
    "session.js",  # the session view: one session's dispatch tree and goal line
    "notify.js",  # desktop notifications
    "main.js",  # render() and refresh()
    "live.js",  # leader election, the SSE stream, and the fallback poll
)


def asset_path(name: str) -> Path:
    return WEB_DIR / name


def load_script() -> str:
    """Every script part, in order, as the one text the page executes."""
    return "".join(asset_path(name).read_text(encoding="utf-8") for name in APP_PARTS)


def load_page() -> bytes:
    template = asset_path("index.html").read_text(encoding="utf-8")
    styles = asset_path("styles.css").read_text(encoding="utf-8")
    script = load_script()
    if template.count("{{CARGENTO_STYLES}}") != 1:
        msg = "index.html must contain one CARGENTO_STYLES slot"
        raise RuntimeError(msg)
    if template.count("{{CARGENTO_APP}}") != 1:
        msg = "index.html must contain one CARGENTO_APP slot"
        raise RuntimeError(msg)
    return (
        template.replace("{{CARGENTO_STYLES}}", styles)
        .replace("{{CARGENTO_APP}}", script)
        .encode("utf-8")
    )
