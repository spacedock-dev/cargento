from __future__ import annotations

from cargento_runtime.web import page as frontend_page

from .page_harness import PageJsHarness

NEXT_WEB_DIR = frontend_page.WEB_DIR / "next"
NEXT_APP_JS = frontend_page.load_next_script()
NEXT_STYLES = (NEXT_WEB_DIR / "styles.css").read_text(encoding="utf-8")
NEXT_PAGE_TEXT = (
    (NEXT_WEB_DIR / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{CARGENTO_STYLES}}", NEXT_STYLES)
    .replace("{{CARGENTO_APP}}", NEXT_APP_JS)
)


class NextPageJsHarness(PageJsHarness):
    """Run the independently assembled next-UI script under the shared DOM stubs."""

    APP_JS = NEXT_APP_JS
