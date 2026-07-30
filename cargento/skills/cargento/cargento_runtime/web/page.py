from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    return WEB_DIR / name


def load_page() -> bytes:
    template = asset_path("index.html").read_text(encoding="utf-8")
    styles = asset_path("styles.css").read_text(encoding="utf-8")
    script = asset_path("app.js").read_text(encoding="utf-8")
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
