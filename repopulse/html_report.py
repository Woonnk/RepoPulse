"""Standalone HTML with escaped data, trusted script hashes, and no requests."""

import base64
import hashlib
from importlib.resources import files
import json
from pathlib import Path


def render_html(report, root):
    root = Path(root).expanduser().resolve()
    source_links = {}
    for item in report["files"]:
        target = (root / item["path"]).resolve()
        if target.is_relative_to(root):
            source_links[item["path"]] = target.as_uri()
    data = json.dumps({**report, "source_links": source_links}, ensure_ascii=True)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    script = files("repopulse").joinpath("report.js").read_text(encoding="utf-8")
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode("ascii")
    template = files("repopulse").joinpath("report.html").read_text(encoding="utf-8")
    # Insert untrusted JSON last so placeholder-like filenames remain literal.
    return template.replace("__SCRIPT_HASH__", digest).replace("__REPORT_SCRIPT__", script).replace("__REPORT_DATA__", data)
