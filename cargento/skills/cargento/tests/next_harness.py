from __future__ import annotations

import json

from cargento_runtime.web import page as frontend_page

from .page_harness import PageJsHarness

NEXT_WEB_DIR = frontend_page.WEB_DIR
NEXT_APP_JS = frontend_page.load_script()
NEXT_STYLES = (NEXT_WEB_DIR / "styles.css").read_text(encoding="utf-8")
NEXT_PAGE_TEXT = (
    (NEXT_WEB_DIR / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{CARGENTO_STYLES}}", NEXT_STYLES)
    .replace("{{CARGENTO_APP}}", NEXT_APP_JS)
)


def storage_prelude(seed: dict[str, str], *, location_hash: str = "") -> str:
    """Install observable browser storage before the dashboard bundle loads."""
    return f"""
let __store = {json.dumps(seed)};
let __storageReads = [];
let __storageWrites = [];
const localStorage = {{
  getItem(k){{
    __storageReads.push(k);
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  }},
  setItem(k, v){{
    __storageWrites.push(k);
    __store[k] = String(v);
  }},
  removeItem(k){{
    __storageWrites.push(k);
    delete __store[k];
  }}
}};
const navigator = {{}};
location.hash = {json.dumps(location_hash)};
"""


class NextPageJsHarness(PageJsHarness):
    """Run the independently assembled next-UI script under the shared DOM stubs."""

    APP_JS = NEXT_APP_JS
