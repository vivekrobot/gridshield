"""Generate one simplified single-line circuit for the GridShield hardware model.

Run:  python scripts/make_simple_circuit.py
Out:  docs/circuit-simple.svg
      build/circuit-simple.pdf
      build/circuit-simple.png

This is the "one diagram" overview: only the main power and signal connections.
The detailed reference is docs/circuit-complete.svg.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_schematics import Sheet  # noqa: E402

OUT_SVG = ROOT / "docs" / "circuit-simple.svg"
OUT_PDF = ROOT / "build" / "circuit-simple.pdf"
OUT_PNG = ROOT / "build" / "circuit-simple.png"

W, H = 2400, 1400

CSS = """
  text{fill:#111827;font-family:'Segoe UI',Arial,sans-serif}
  .w{stroke:#111827;stroke-width:3;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .m{stroke:#b91c1c;stroke-width:4;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .bx{fill:none;stroke:#111827;stroke-width:2.5}
  .bf{fill:#ffffff;stroke:#111827;stroke-width:2.5}
  .d{stroke:#6b7280;stroke-width:2.2;fill:none;stroke-dasharray:10 7}
  .j{fill:#111827;stroke:none}
  .g{fill:#4b5563}
  .net{fill:#0369a1;font-weight:600}
  .warn{fill:#b91c1c;font-weight:600}
  .iso{fill:#fef3c7;stroke:#d97706;stroke-width:2.2}
"""


class Simple(Sheet):
    def box(self, x, y, w, h, title, sub=None, sub2=None):
        self.rect(x, y, w, h, cls="bf", rx=6)
        self.txt(x + w / 2, y + 34, title, 17, "middle", weight="600")
        if sub:
            self.txt(x + w / 2, y + 58, sub, 11, "middle", cls="g")
        if sub2:
            self.txt(x + w / 2, y + 76, sub2, 11, "middle", cls="g")

    def arrow(self, x1, y1, x2, y2, cls="w"):
        self.line(x1, y1, x2, y2, cls)
        dx, dy = x2 - x1, y2 - y1
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        ax, ay = x2 - ux * 14, y2 - uy * 14
        self.raw(
            f'<path d="M{x2} {y2} L{ax + px * 6} {ay + py * 6} '
            f'L{ax - px * 6} {ay - py * 6} Z" class="j"/>'
        )

    def titleblock(self):
        y = H - 100
        self.rect(24, y, W - 48, 72, cls="bx", rx=4)
        self.line(W - 450, y, W - 450, y + 72)
        self.line(W - 270, y, W - 270, y + 72)
        self.txt(48, y + 30, "GridShield — simple complete circuit", 16, weight="600")
        self.txt(48, y + 54, "All main power and signal connections on one sheet", 11, cls="g")
        self.txt(W - 430, y + 30, "Single sheet", 13)
        self.txt(W - 430, y + 54, "Rev A · 2026-11-12", 11, cls="g")
        self.txt(W - 250, y + 30, "Prototype", 13)
        self.txt(W - 250, y + 54, "not certified", 11, cls="g")

    def save(self, path: Path, title: str, sub: str) -> Path:
        self.titleblock()
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}">\n<style>' + CSS + "</style>\n"
            f'<rect x="24" y="24" width="{W - 48}" height="{H - 48}" rx="4" class="bx"/>\n'
            f'<text x="56" y="74" font-size="32" font-weight="600">{title}</text>\n'
            f'<text x="56" y="106" font-size="14" fill="#4b5563">{sub}</text>\n'
        )
        body = "\n".join(self.p)
        path.write_text(head + body + "\n</svg>\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
        return path


def draw(s: Simple) -> None:
    # ---- top band: mains power path -------------------------------------
    s.raw('<circle cx="120" cy="330" r="9" class="bf"/>')
    s.txt(120, 250, "230 V AC · 50 Hz", 13, "middle", weight="600")
    s.txt(120, 272, "L / N / PE", 10, "middle", cls="g")
    s.line(120, 339, 120, 352, "m")
    s.line(96, 352, 144, 352, "m")
    s.line(103, 360, 137, 360, "m")
    s.line(110, 368, 130, 368, "m")
    s.txt(146, 362, "PE", 10, cls="g")

    s.box(180, 280, 140, 100, "MCB", "10 A")
    s.box(380, 280, 170, 100, "RCD", "30 mA")
    s.box(610, 270, 280, 120, "PZEM #1", "LOAD METER", "U · I · P · E")
    s.box(950, 270, 180, 120, "K1 RELAY", "10 A NO", "active-LOW")
    s.box(1190, 280, 180, 100, "LOAD", "0–12 A")

    for x1, x2 in ((129, 180), (320, 380), (550, 610), (890, 950), (1130, 1190)):
        s.line(x1, 330, x2, 330, "m")

    # solar branch, joining the live bus before K1
    s.box(1600, 470, 220, 140, "SOLAR", "GRID-TIE", "≤ 3 kW")
    s.box(1230, 470, 330, 140, "PZEM #2", "SOLAR METER", "import / export")
    s.line(1600, 560, 1560, 560, "m")
    s.line(1230, 560, 900, 560, "m")
    s.line(900, 560, 900, 330, "m")
    s.dot(900, 330)
    s.txt(946, 598, "solar joins the live bus before K1", 10, cls="g")

    # ---- isolated PZEM UART --------------------------------------------
    s.line(750, 390, 750, 700, "d")
    s.line(1395, 610, 1395, 700, "d")
    s.rect(1095, 680, 40, 40, cls="iso", rx=3)
    s.line(750, 700, 1395, 700, "d")
    s.txt(1115, 672, "1 kV", 10, "middle", weight="600")
    s.line(1150, 700, 1150, 800, "d")
    s.txt(770, 744, "isolated Modbus UART · 9600 8N1", 11, cls="net")

    # ---- middle band: sensors, controller, outputs ----------------------
    s.box(140, 830, 300, 120, "ZMPT101B", "230 V → 1 V RMS", "GPIO34 voltage")
    s.box(140, 1000, 300, 120, "SCT-013-030", "30 A → 1 V RMS", "GPIO35 current")

    s.rect(960, 800, 440, 320, cls="bf", rx=8)
    s.txt(1180, 844, "ESP32 DevKit v1", 18, "middle", weight="600")
    s.txt(1180, 868, "Wi-Fi · ADC1 · 3.3 V logic", 11, "middle", cls="g")
    for i, line in enumerate((
        "GPIO34  voltage",
        "GPIO35  current",
        "GPIO25  relay",
        "GPIO27/32/33  buzzer, LEDs",
    )):
        s.txt(990, 924 + i * 26, line, 11, cls="g")

    s.box(1500, 840, 240, 100, "K1 COIL", "5 V · active-LOW")
    s.box(1500, 980, 240, 80, "BZ1", "GPIO27 buzzer")
    s.box(1500, 1100, 240, 80, "D6 OK · D7 TRIP", "GPIO32 / 33")

    s.arrow(440, 890, 960, 890)
    s.arrow(440, 1060, 960, 1060)
    s.txt(940, 880, "GPIO34", 11, "end", cls="net")
    s.txt(940, 1050, "GPIO35", 11, "end", cls="net")

    s.arrow(1400, 890, 1500, 890)
    s.arrow(1400, 1020, 1500, 1020)
    s.arrow(1400, 1140, 1500, 1140)
    s.txt(1478, 880, "GPIO25", 11, "end", cls="net")
    s.txt(1478, 1010, "GPIO27", 11, "end", cls="net")
    s.txt(1478, 1130, "GPIO32/33", 11, "end", cls="net")

    s.txt(1420, 320, "MAIN POWER →", 11, cls="net")

    # ---- 5 V supply -----------------------------------------------------
    s.box(140, 1200, 300, 90, "5 V / 2 A PSU", "SELV supply")
    s.line(440, 1245, 1180, 1245)
    s.arrow(1180, 1245, 1180, 1120)
    s.txt(620, 1236, "+5 V", 11, cls="net")

    # ---- safety note ----------------------------------------------------
    s.raw('<rect x="1600" y="210" width="380" height="150" rx="6" fill="#fef2f2"/>')
    s.rect(1600, 210, 380, 150, cls="bx", rx=6)
    s.txt(1620, 244, "PROTOTYPE ONLY", 14, cls="warn")
    s.txt(1620, 270, "230 V AC. Use an enclosure,", 11, cls="g")
    s.txt(1620, 288, "MCB + RCD and certified terminals.", 11, cls="g")
    s.txt(1620, 312, "K1 is not a protective device.", 11, cls="g")

    s.txt(1600, 1250, "Prototype only — not a certified mains design.", 11, cls="g")


def render(svg: Path) -> None:
    from playwright.sync_api import sync_playwright

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>@page{{size:{W}px {H}px;margin:0}}"
        "html,body{margin:0;padding:0;background:#fff}"
        "svg{display:block}</style></head><body>"
        + svg.read_text(encoding="utf-8")
        + "</body></html>"
    )
    tmp = ROOT / "build" / "circuit-simple.html"
    tmp.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1.5)
        page.goto(tmp.as_uri(), wait_until="load")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT_PNG), full_page=True)
        page.pdf(path=str(OUT_PDF), width=f"{W}px", height=f"{H}px",
                 print_background=True, margin={"top": "0", "bottom": "0",
                                                "left": "0", "right": "0"})
        browser.close()
    print(f"wrote {OUT_PNG.relative_to(ROOT)}")
    print(f"wrote {OUT_PDF.relative_to(ROOT)}")


def main() -> int:
    OUT_PDF.parent.mkdir(exist_ok=True)
    s = Simple()
    draw(s)
    svg = s.save(OUT_SVG, "GridShield — simple complete circuit",
                 "230 V power path · ESP32 · sensors · relay · isolated PZEM UART")
    render(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
