"""Build a single PDF containing the whole GridShield project.

Pipeline:  Markdown -> HTML -> headless Chrome (print to PDF).
The reference schematics are embedded as vector SVG on landscape pages.

Run:  python scripts/build_pdf.py
Out:  build/GridShield-Project.pdf
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
OUT_PDF = BUILD / "GridShield-Project.pdf"
HTML_FILE = BUILD / "GridShield-Project.html"

CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

DOCS = [
    ("Readme", "README.md", "Project overview, results and how to run"),
    ("Architecture", "docs/architecture.md", "Components, data flow and timing"),
    ("Hardware design", "docs/hardware-design.md", "Blocks, power budget, PCB guidance"),
    ("Wiring", "docs/wiring.md", "Pin map, front-end, PZEM isolation, calibration"),
    ("ML pipeline", "docs/ml-pipeline.md", "Dataset, 1D-CNN, training and quantisation"),
    ("Data contract", "docs/data-contract.md", "MQTT payload, validation, database schema"),
    ("Safety", "docs/safety.md", "Interlock policy and reset semantics"),
    ("Paper corrections", "docs/paper-corrections.md", "Deliberate departures from the paper"),
]

SHEETS = [
    ("Sheet 1 — Mains power path", "docs/circuit-sheet-1-power.svg"),
    ("Sheet 2 — Isolation and power", "docs/circuit-sheet-2-isolation.svg"),
    ("Sheet 3 — MCU, sensing and actuation", "docs/circuit-sheet-3-mcu-io.svg"),
]

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "data", "build", "models", "reports"}

CSS = """
@page { size: A4; margin: 17mm 15mm 16mm 15mm; }
@page land { size: A4 landscape; margin: 8mm; }
@page cover { size: A4; margin: 0; }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.2pt; line-height: 1.55;
       color: #111827; margin: 0; }

.cover { page: cover; height: 297mm; padding: 42mm 24mm; box-sizing: border-box;
         background: #0f172a; color: #f8fafc; break-after: page; }
.cover .kicker { font-size: 10pt; letter-spacing: 3px; text-transform: uppercase;
                 color: #38bdf8; }
.cover h1 { font-size: 46pt; margin: 10mm 0 3mm; letter-spacing: -1px; border: 0; }
.cover .sub { font-size: 15pt; color: #cbd5e1; max-width: 150mm; line-height: 1.4; }
.cover .rule { height: 3px; background: #38bdf8; width: 60mm; margin: 12mm 0; }
.cover .meta { font-size: 9.5pt; color: #94a3b8; line-height: 1.9; margin-top: 18mm; }
.cover .meta b { color: #e2e8f0; font-weight: 600; }
.cover .warn { margin-top: 16mm; font-size: 9pt; color: #fca5a5;
               border-left: 3px solid #f87171; padding-left: 5mm; max-width: 140mm; }

h1 { font-size: 19pt; margin: 0 0 6mm; padding-bottom: 3mm;
     border-bottom: 2.5px solid #0f172a; break-before: page; break-after: avoid; }
h1 .num { color: #0284c7; margin-right: 3mm; }
h2 { font-size: 13pt; margin: 7mm 0 2.5mm; color: #0f172a; break-after: avoid; }
h3 { font-size: 11pt; margin: 5mm 0 2mm; break-after: avoid; }
p { margin: 0 0 2.6mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
a { color: #0369a1; text-decoration: none; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 6mm 0; }

table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm; font-size: 8.6pt; }
th, td { border: 1px solid #d1d5db; padding: 1.6mm 2.2mm; vertical-align: top; text-align: left; }
th { background: #f1f5f9; font-weight: 600; }
tr { break-inside: avoid; }

code { font-family: Consolas, "Courier New", monospace; font-size: 8.4pt;
       background: #f1f5f9; padding: 0.3mm 1.2mm; border-radius: 2px; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 3px solid #94a3b8;
      padding: 3mm 4mm; font-size: 7.8pt; line-height: 1.4; white-space: pre-wrap;
      word-break: break-word; break-inside: avoid; margin: 3mm 0 5mm; }
pre code { background: none; padding: 0; font-size: 7.8pt; }

blockquote { margin: 3mm 0 5mm; padding: 2.5mm 4mm; background: #fffbeb;
             border-left: 3px solid #f59e0b; break-inside: avoid; }
blockquote p { margin: 0 0 1.5mm; }
blockquote p:last-child { margin-bottom: 0; }

.toc { break-after: page; }
.toc h1 { break-before: auto; }
.toc ol { list-style: none; padding: 0; }
.toc li { display: flex; justify-content: space-between; border-bottom: 1px dotted #cbd5e1;
          padding: 2.2mm 0; font-size: 10.5pt; }
.toc .d { color: #64748b; font-size: 8.6pt; }

.land { page: land; break-before: page; }
.land h1 { break-before: auto; font-size: 14pt; margin: 0 0 2mm; border: 0; }
.land svg { display: block; height: 163mm; width: auto; margin: 0 auto; }
.caption { font-size: 7.5pt; color: #64748b; margin: 1.5mm 0 0; text-align: center; }
"""


def find_chrome() -> Path:
    for p in CHROME_CANDIDATES:
        if p.exists():
            return p
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    sys.exit("Chrome or Edge not found; install one or pass --chrome PATH")


def convert(path: Path) -> str:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"]
    )
    return md.convert(path.read_text(encoding="utf-8"))


def number_heading(body: str, anchor: str, num: int) -> str:
    return re.sub(
        r"<h1[^>]*>",
        f'<h1 id="{anchor}"><span class="num">{num}</span>',
        body,
        count=1,
    )


def rewrite_links(body: str, anchors: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        target = m.group(1)
        name = Path(target).name.lower()
        if name in anchors:
            return f'href="#{anchors[name]}"'
        return m.group(0)

    return re.sub(r'href="([^"]+?\.md)(?:#[^"]*)?"', repl, body)


def tree() -> str:
    rows = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file() and p.suffix.lower() in {".pyc", ".db"}:
            continue
        depth = len(rel.parts) - 1
        name = ("    " * depth) + rel.name + ("/" if p.is_dir() else "")
        size = "" if p.is_dir() else f"{p.stat().st_size / 1024:.0f} kB"
        rows.append((name, size))
    lis = "\n".join(
        f'<tr><td><code>{html.escape(n)}</code></td><td class="r">{s}</td></tr>' for n, s in rows
    )
    return f'<table class="files"><thead><tr><th>Path</th><th>Size</th></tr></thead><tbody>{lis}</tbody></table>'


def build_html() -> str:
    anchors = {Path(p).name.lower(): f"doc-{name.lower().replace(' ', '-')}" for name, p, _ in DOCS}

    parts: list[str] = []

    # ---- cover
    parts.append(
        f"""
<div class="cover">
  <div class="kicker">Technical documentation</div>
  <h1 style="border:0;margin:8mm 0 2mm">GridShield</h1>
  <div class="rule"></div>
  <div class="sub">AI-based power-quality monitoring, protection and predictive
  maintenance for low-voltage distribution networks.</div>
  <div class="meta">
    <b>Edge node</b> ESP32 · 1D-CNN · PZEM-004T · fail-safe relay<br>
    <b>Cloud side</b> MQTT · SQLite · Streamlit + Folium SCADA · Isolation Forest<br>
    <b>Revision</b> A · 2026-11-02 · {len(DOCS)} documents, 3 schematic sheets<br>
    <b>Source</b> <code style="background:#1e293b;color:#e2e8f0">{html.escape(str(ROOT))}</code>
  </div>
  <div class="warn">Reference prototype. The node switches 230 V AC. It is not a
  certified protective device — use an MCB, an RCD and a certified contactor for a
  real installation.</div>
</div>
"""
    )

    # ---- contents
    items = "".join(
        f'<li><a href="#{anchors[Path(p).name.lower()]}">{html.escape(t)}</a>'
        f'<span class="d">{html.escape(d)}</span></li>'
        for t, p, d in DOCS
    )
    sheets = "".join(
        f'<li><a href="#sheet-{i}">{html.escape(t)}</a><span class="d">landscape</span></li>'
        for i, (t, _) in enumerate(SHEETS, 1)
    )
    parts.append(
        f'<section class="toc"><h1 style="border:0">Contents</h1><ol>{items}{sheets}'
        f'<li><a href="#appendix">Appendix — file inventory</a>'
        f'<span class="d">repository listing</span></li></ol></section>'
    )

    # ---- documents
    for i, (title, rel, desc) in enumerate(DOCS, 1):
        path = ROOT / rel
        if not path.exists():
            print(f"  ! missing {rel}, skipped")
            continue
        body = rewrite_links(convert(path), anchors)
        body = number_heading(body, anchors[path.name.lower()], i)
        parts.append(f'<section class="doc">{body}</section>')

    # ---- schematics
    for i, (title, rel) in enumerate(SHEETS, 1):
        svg = (ROOT / rel).read_text(encoding="utf-8")
        svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
        parts.append(
            f'<section class="land" id="sheet-{i}"><h1>{html.escape(title)}</h1>'
            f"{svg}<div class=\"caption\">Vector reference schematic — "
            f"{html.escape(rel)}. Not a certified design; see the hardware design "
            f"document for the isolation and safety requirements.</div></section>"
        )

    # ---- appendix
    parts.append(
        f'<section id="appendix"><h1>Appendix — file inventory</h1>'
        f'<p>Generated listing of the project tree ({html.escape(str(ROOT))}).</p>'
        f"{tree()}</section>"
    )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>GridShield — Project Documentation</title>"
        f"<style>{CSS}</style></head><body>" + "\n".join(parts) + "</body></html>"
    )


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    doc = build_html()
    HTML_FILE.write_text(doc, encoding="utf-8")
    print(f"wrote {HTML_FILE.relative_to(ROOT)} ({len(doc) / 1024:.0f} kB)")

    chrome = find_chrome()
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-pdf-header-footer",
        "--virtual-time-budget=15000",
        f"--print-to-pdf={OUT_PDF}",
        HTML_FILE.as_uri(),
    ]
    print("rendering with", chrome.name)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0 or not OUT_PDF.exists():
        print(res.stdout[-2000:])
        print(res.stderr[-2000:])
        return 1
    print(f"wrote {OUT_PDF.relative_to(ROOT)} ({OUT_PDF.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
