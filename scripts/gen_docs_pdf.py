#!/usr/bin/env python3
"""Regenerate the styled PDF guides from their Markdown sources.

Pipeline: Markdown --(pandoc)--> standalone HTML (embedded CSS)
                   --(Chrome headless)--> PDF.

No Python dependencies — relies on `pandoc` and Google Chrome being installed.
Run after editing any `docs/*.md` guide:

    python scripts/gen_docs_pdf.py

Ported from OptionsAI's `_gen_html_docs.py`, extended to emit PDF directly.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (markdown source, document title) — output PDF is the source with .pdf suffix
GUIDES = [
    ("docs/user-guide.md", "FinView — Guía del Usuario"),
    ("docs/admin-guide.md", "FinView — Guía de Administración"),
]

CSS = """
:root { --accent: #5b7fff; --text: #1a1a2e; --muted: #64748b; --border: #e2e8f0; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       color: var(--text); line-height: 1.7; max-width: 820px; margin: 0 auto;
       padding: 16px 24px; font-size: 14px; }
h1 { font-size: 1.8rem; margin: 0 0 4px; }
h2 { font-size: 1.35rem; margin: 1.8em 0 0.6em; color: var(--accent);
     border-bottom: 2px solid var(--accent); padding-bottom: 4px; }
h3 { font-size: 1.1rem; margin: 1.4em 0 0.4em; }
p, li { margin-bottom: 0.5em; }
ul, ol { padding-left: 1.5em; }
table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 0.88rem; }
th, td { border: 1px solid var(--border); padding: 8px 12px; text-align: left;
         vertical-align: top; }
th { background: #f1f5f9; font-weight: 600; }
blockquote { border-left: 4px solid var(--accent); background: #f8fafc;
             padding: 12px 16px; margin: 1em 0; color: var(--muted); }
code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.88em; }
pre { background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px;
      overflow-x: auto; margin: 1em 0; }
pre code { background: none; color: inherit; padding: 0; }
a { color: var(--accent); text-decoration: none; }
hr { border: none; border-top: 1px solid var(--border); margin: 2em 0; }
@page { margin: 18mm 14mm; }
"""

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]


def _find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    sys.exit("ERROR: Google Chrome / Chromium not found — needed to render PDF.")


def main() -> None:
    if not shutil.which("pandoc"):
        sys.exit("ERROR: pandoc not found. Install it (brew install pandoc).")
    chrome = _find_chrome()

    with tempfile.TemporaryDirectory() as tmp:
        css_file = Path(tmp) / "style.css"
        css_file.write_text(CSS)

        for rel_src, title in GUIDES:
            src = ROOT / rel_src
            if not src.exists():
                print(f"skip (missing): {rel_src}")
                continue

            html_file = Path(tmp) / (src.stem + ".html")
            pdf_out = src.with_suffix(".pdf")

            # 1. Markdown → standalone HTML with embedded CSS
            subprocess.run(
                [
                    "pandoc", str(src),
                    "--standalone",
                    "--embed-resources",
                    "--metadata", f"title={title}",
                    "--css", str(css_file),
                    "-o", str(html_file),
                ],
                check=True,
            )

            # 2. HTML → PDF via Chrome headless
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--no-pdf-header-footer",
                    "--disable-gpu",
                    f"--print-to-pdf={pdf_out}",
                    html_file.as_uri(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            size = pdf_out.stat().st_size
            print(f"generated {pdf_out.relative_to(ROOT)} ({size:,} bytes)")


if __name__ == "__main__":
    main()
