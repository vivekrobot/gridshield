"""Generate the GridShield reference schematics as standalone SVG files.

Run:  python scripts/make_schematics.py
Out:  docs/circuit-sheet-1-power.svg
      docs/circuit-sheet-2-isolation.svg
      docs/circuit-sheet-3-mcu-io.svg

These are block-level reference drawings for a prototype. They are not a
certified design and must not be used to build a mains product as-is.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"

CSS = """
  text{fill:#111827;font-family:'Segoe UI',Arial,sans-serif}
  .w{stroke:#111827;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .m{stroke:#b91c1c;stroke-width:2.6;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .bx{fill:none;stroke:#111827;stroke-width:2}
  .bf{fill:#ffffff;stroke:#111827;stroke-width:2}
  .d{stroke:#6b7280;stroke-width:1.5;fill:none;stroke-dasharray:6 5}
  .j{fill:#111827;stroke:none}
  .g{fill:#4b5563}
  .sm{font-size:12px}
"""


class Sheet:
    def __init__(self) -> None:
        self.p: list[str] = []

    # -- primitives -------------------------------------------------------
    def raw(self, s: str) -> None:
        self.p.append(s)

    def line(self, x1, y1, x2, y2, cls="w"):
        self.raw(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}"/>')

    def poly(self, pts, cls="w"):
        d = "M" + " L".join(f"{x} {y}" for x, y in pts)
        self.raw(f'<path d="{d}" class="{cls}"/>')

    def rect(self, x, y, w, h, cls="bf", rx=3):
        self.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"/>')

    def txt(self, x, y, t, size=13, anchor="start", cls="", weight=None):
        extra = f' font-weight="{weight}"' if weight else ""
        self.raw(
            f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}"'
            f' class="{cls}"{extra}>{t}</text>'
        )

    def lines(self, x, y, rows, size=12, lead=18, cls="", anchor="start"):
        for i, t in enumerate(rows):
            self.txt(x, y + i * lead, t, size, anchor, cls)

    def dot(self, x, y, r=4.5):
        self.raw(f'<circle cx="{x}" cy="{y}" r="{r}" class="j"/>')

    def hop(self, x, y, vertical=True, r=9):
        """Wire jump (no connection) drawn as a small arc."""
        if vertical:
            self.p.append(
                f'<path d="M{x} {y - r} A {r} {r} 0 0 1 {x} {y + r}" class="w"/>'
            )
        else:
            self.p.append(
                f'<path d="M{x - r} {y} A {r} {r} 0 0 1 {x + r} {y}" class="w"/>'
            )

    # -- symbols ----------------------------------------------------------
    def res_h(self, x, y):
        """Horizontal resistor, 50 px long, starting at (x, y)."""
        self.raw(
            f'<path d="M{x} {y} l5 0 l10 -9 l10 18 l10 -18 l10 18 l5 -9" class="w"/>'
        )
        return x + 50

    def res_v(self, x, y):
        """Vertical resistor, 50 px long, starting at (x, y) going down."""
        self.raw(
            f'<path d="M{x} {y} l0 5 l-9 10 l18 10 l-18 10 l18 10 l-9 5" class="w"/>'
        )
        return y + 50

    def cap_v(self, x, y):
        """Vertical capacitor between y and y+8 at x."""
        self.line(x - 12, y, x + 12, y)
        self.line(x - 12, y + 9, x + 12, y + 9)
        return y + 9

    def gnd(self, x, y):
        self.line(x, y, x, y + 9)
        self.line(x - 12, y + 9, x + 12, y + 9)
        self.line(x - 7, y + 15, x + 7, y + 15)
        self.line(x - 2, y + 21, x + 2, y + 21)

    def pwr(self, x, y, label):
        """Supply flag pointing up from (x, y)."""
        self.line(x, y, x, y - 12)
        self.line(x - 9, y - 12, x + 9, y - 12)
        self.txt(x, y - 20, label, 11, "middle")

    def diode_v(self, x, y, down=True):
        """Diode pointing down (anode top) between y and y+16."""
        if down:
            self.raw(f'<path d="M{x - 9} {y} L{x + 9} {y} L{x} {y + 16} Z" class="w"/>')
            self.line(x - 9, y + 16, x + 9, y + 16)
        else:
            self.raw(f'<path d="M{x - 9} {y + 16} L{x + 9} {y + 16} L{x} {y} Z" class="w"/>')
            self.line(x - 9, y, x + 9, y)

    def npn(self, cx, cy):
        self.raw(f'<circle cx="{cx}" cy="{cy}" r="27" class="bx"/>')
        self.line(cx - 9, cy - 16, cx - 9, cy + 16)
        self.line(cx - 27, cy, cx - 9, cy)
        self.poly([(cx - 9, cy - 7), (cx + 10, cy - 24), (cx + 10, cy - 44)])
        self.poly([(cx - 9, cy + 7), (cx + 10, cy + 24), (cx + 10, cy + 44)])
        self.raw(
            f'<path d="M{cx + 2} {cy + 26} L{cx + 12} {cy + 22} L{cx + 7} {cy + 33} Z" class="j"/>'
        )

    def titleblock(self, sheet, sub):
        self.rect(24, 952, 1552, 72, cls="bx", rx=4)
        self.line(1150, 952, 1150, 1024)
        self.line(1330, 952, 1330, 1024)
        self.txt(48, 982, "GridShield — 230 V single-phase edge node", 16, weight="600")
        self.txt(48, 1006, sub, 11, cls="g")
        self.txt(1170, 982, f"Sheet {sheet} of 3", 13)
        self.txt(1170, 1006, "Rev A · 2026-11-02", 11, cls="g")
        self.txt(1350, 982, "Prototype", 13)
        self.txt(1350, 1006, "not certified", 11, cls="g")

    def save(self, path: Path, sheet, title, sub):
        self.titleblock(sheet, sub)
        head = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1060"'
            ' width="1600" height="1060">\n<style>' + CSS + "</style>\n"
            '<rect x="24" y="24" width="1552" height="1000" rx="4" class="bx"/>\n'
            f'<text x="56" y="74" font-size="26" font-weight="600">{title}</text>\n'
        )
        body = "\n".join(self.p)
        path.write_text(head + body + "\n</svg>\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


# === SHEET 1 ==============================================================
def sheet1() -> Sheet:
    s = Sheet()
    red = "m"

    # ---- inlet
    s.txt(110, 236, "MAINS INLET", 13, "middle", weight="600")
    s.txt(110, 256, "230 V AC · 50 Hz · 12 A", 11, "middle", cls="g")
    for y, lbl in ((320, "L"), (440, "N"), (560, "PE")):
        s.raw(f'<circle cx="110" cy="{y}" r="7" class="bf"/>')
        s.txt(94, y + 5, lbl, 14, "end", weight="600")

    # ---- L rail: MCB -> RCD
    s.line(117, 320, 170, 320, red)
    s.rect(170, 294, 80, 52, rx=3)
    s.txt(210, 316, "MCB", 13, "middle", weight="600")
    s.txt(210, 334, "10 A", 11, "middle")
    s.line(250, 320, 290, 320, red)

    s.rect(290, 286, 110, 200, cls="bx", rx=3)
    s.line(290, 320, 400, 320, red)
    s.line(290, 440, 400, 440, red)
    s.txt(345, 378, "RCD", 13, "middle", weight="600")
    s.txt(345, 396, "30 mA", 11, "middle")

    # ---- MOV
    s.line(400, 320, 560, 320, red)
    s.line(400, 440, 1010, 440, red)
    s.dot(470, 320)
    s.dot(470, 440)
    s.line(470, 320, 470, 360, red)
    s.rect(455, 360, 30, 40, rx=2)
    s.poly([(462, 392), (478, 368)])
    s.raw('<path d="M474 366 L482 362 L478 372 Z" class="j"/>')
    s.line(470, 400, 470, 440, red)
    s.txt(496, 378, "MOV", 12, weight="600")
    s.txt(496, 394, "275 V", 11, cls="g")

    # ---- PZEM #1 (load)
    s.rect(560, 160, 270, 260, rx=3)
    s.txt(695, 194, "PZEM-004T v3 #1", 16, "middle", weight="600")
    s.txt(695, 216, "LOAD METER · addr 0x01", 11, "middle", cls="g")
    s.lines(600, 262, ["U, I, P, E, f, PF via", "Modbus RTU 9600 8N1", "100 A internal shunt", "no waveform output"], 11, 18, "g")
    s.line(640, 420, 640, 440, red)
    s.dot(640, 440)
    s.txt(636, 466, "N", 11, "middle", cls="g")

    # PZEM #1 TTL header (above the module)
    s.rect(610, 120, 190, 40, rx=2)
    s.txt(705, 145, "TTL: 5V GND TX RX", 11, "middle", cls="g")
    for x, y in ((640, 56), (690, 78), (740, 96), (790, 114)):
        s.line(x, 120, x, y)
        s.line(x, y, 1300, y)
    s.rect(1300, 40, 120, 92, rx=2)
    s.txt(1360, 74, "PZEM #1", 11, "middle", weight="600")
    s.txt(1360, 92, "to ISO1", 10, "middle", cls="g")
    s.txt(1360, 108, "(Sheet 2, J1)", 10, "middle", cls="g")

    # ---- relay + load
    s.line(830, 320, 880, 320, red)
    s.dot(845, 320)
    s.rect(880, 270, 100, 100, rx=3)
    s.txt(930, 292, "K1", 13, "middle", weight="600")
    s.raw('<circle cx="905" cy="320" r="4" class="bf"/>')
    s.raw('<circle cx="955" cy="320" r="4" class="bf"/>')
    s.line(909, 318, 957, 306)
    s.txt(930, 352, "NO 10 A", 11, "middle")
    s.line(980, 320, 1010, 320, red)
    s.txt(930, 388, "energise-to-close", 10, "middle", cls="g")

    s.rect(1010, 270, 130, 200, rx=3)
    s.txt(1075, 302, "LOAD", 15, "middle", weight="600")
    s.txt(1075, 324, "0–12 A", 11, "middle")
    s.txt(1075, 342, "relay-switched", 10, "middle", cls="g")
    s.raw('<circle cx="1010" cy="320" r="6" class="bf"/>')
    s.raw('<circle cx="1010" cy="440" r="6" class="bf"/>')

    # ---- branch to the solar meter
    s.line(845, 320, 845, 430, red)
    s.hop(845, 440)
    s.line(845, 450, 845, 700, red)
    s.line(845, 700, 780, 700, red)
    s.dot(890, 440)
    s.line(890, 440, 890, 770, red)
    s.line(890, 770, 780, 770, red)

    # ---- PZEM #2 (solar)
    s.rect(500, 560, 280, 240, rx=3)
    s.txt(640, 594, "PZEM-004T v3 #2", 16, "middle", weight="600")
    s.txt(640, 616, "SOLAR METER · addr 0x02", 11, "middle", cls="g")
    s.lines(530, 654, ["net metering:", "import / export split", "inverter AC output", "is metered here"], 11, 18, "g")
    s.raw('<circle cx="500" cy="700" r="6" class="bf"/>')
    s.raw('<circle cx="500" cy="770" r="6" class="bf"/>')
    s.raw('<circle cx="780" cy="700" r="6" class="bf"/>')
    s.raw('<circle cx="780" cy="770" r="6" class="bf"/>')

    # ---- inverter
    s.rect(260, 640, 220, 220, rx=3)
    s.txt(370, 678, "SOLAR", 15, "middle", weight="600")
    s.txt(370, 700, "GRID-TIE", 12, "middle")
    s.txt(370, 720, "INVERTER", 12, "middle")
    s.txt(370, 744, "≤ 3 kW", 11, "middle", cls="g")
    s.line(480, 700, 500, 700, red)
    s.line(480, 770, 500, 770, red)

    # ---- PZEM #2 TTL header (below the module)
    s.rect(540, 800, 220, 40, rx=2)
    s.txt(650, 825, "TTL: 5V GND TX RX", 11, "middle", cls="g")
    for x, y in ((570, 860), (620, 878), (670, 896), (720, 914)):
        s.line(x, 840, x, y)
        s.line(x, y, 1300, y)
    s.rect(1300, 845, 120, 92, rx=2)
    s.txt(1360, 879, "PZEM #2", 11, "middle", weight="600")
    s.txt(1360, 897, "to ISO2", 10, "middle", cls="g")
    s.txt(1360, 913, "(Sheet 2, J2)", 10, "middle", cls="g")

    # ---- PE
    s.line(110, 567, 110, 640)
    s.line(86, 640, 134, 640)
    s.line(93, 647, 127, 647)
    s.line(100, 654, 120, 654)
    s.txt(146, 646, "PE / enclosure bond", 11, cls="g")

    # ---- notes
    s.rect(1180, 180, 360, 620, cls="bx", rx=3)
    s.txt(1200, 210, "NOTES", 13, weight="600")
    notes = [
        "1. MCB 6–10 A and a 30 mA RCD are",
        "   mandatory upstream of everything.",
        "",
        "2. K1 is an additional load switch, not",
        "   a protective device. Use a certified",
        "   contactor for a real installation.",
        "",
        "3. The PZEM TTL header may be mains-",
        "   referenced depending on the clone.",
        "   Verify isolation before touching it;",
        "   power and UART go through ISO1/ISO2",
        "   on Sheet 2.",
        "",
        "4. Load current flows through the",
        "   PZEM #1 internal shunt. Wire L in",
        "   series, N as a voltage reference.",
        "",
        "5. Use 300 V / 10 A terminals, 6 mm",
        "   creepage, and an enclosure barrier.",
        "",
        "6. A wire crossing without a dot is",
        "   not a connection.",
    ]
    s.lines(1200, 240, notes, 11, 20, "g")

    s.save(OUT / "circuit-sheet-1-power.svg", 1,
           "GridShield edge node — mains power path",
           "230 V single-phase supply, energy metering and load switching")
    return s


# === SHEET 2 ==============================================================
def sheet2() -> Sheet:
    s = Sheet()

    # ---- isolation band (drawn first, wires pass over it)
    s.rect(884, 168, 34, 610, cls="bx", rx=0)
    s.raw('<rect x="884" y="168" width="34" height="610" fill="#fef3c7" opacity="0.55"/>')
    s.raw('<line x1="884" y1="168" x2="884" y2="778" class="d"/>')
    s.raw('<line x1="918" y1="168" x2="918" y2="778" class="d"/>')
    s.raw(
        '<text x="901" y="470" font-size="11" fill="#92400e" text-anchor="middle"'
        ' transform="rotate(-90 901 470)">ISOLATION BARRIER · 1 kV</text>'
    )

    # ---- ESP32
    s.rect(80, 180, 220, 520, rx=3)
    s.txt(190, 216, "ESP32 DevKit v1", 15, "middle", weight="600")
    s.txt(190, 240, "3.3 V logic · Wi-Fi 2.4 GHz", 10, "middle", cls="g")
    pins = [
        (250, "5V", "5 V in"),
        (290, "GND", ""),
        (400, "GPIO17", "UART2 TX2"),
        (430, "GPIO16", "UART2 RX2"),
        (540, "GPIO19", "UART1 TX1"),
        (570, "GPIO18", "UART1 RX1"),
    ]
    for y, name, sub in pins:
        s.line(300, y, 360, y)
        s.txt(292, y - 4, name, 11, "end", weight="600")
        if sub:
            s.txt(292, y + 10, sub, 9, "end", cls="g")

    # ---- power trunks
    s.line(360, 250, 660, 250)
    s.line(660, 250, 660, 282)
    s.hop(660, 290)
    s.line(660, 298, 660, 520)
    s.line(360, 290, 620, 290)
    s.line(620, 290, 620, 560)

    # ---- channel 1 DC-DC
    s.rect(700, 210, 160, 100, rx=3)
    s.txt(780, 234, "PS2 · B0505S-1W", 12, "middle", weight="600")
    s.txt(780, 252, "5 V → 5 V isolated", 10, "middle", cls="g")
    s.txt(780, 268, "1 W, 200 mA", 10, "middle", cls="g")
    s.line(660, 250, 700, 250)
    s.dot(660, 250)
    s.line(620, 290, 700, 290)
    s.dot(620, 290)
    s.txt(692, 246, "IN+", 9, "end", cls="g")
    s.txt(692, 286, "IN−", 9, "end", cls="g")
    s.line(860, 250, 1080, 250)
    s.line(860, 290, 1040, 290)

    # ---- channel 1 isolator
    s.rect(700, 380, 160, 80, rx=3)
    s.txt(780, 404, "ISO1 · ADuM1201", 12, "middle", weight="600")
    s.txt(780, 422, "2-channel digital", 10, "middle", cls="g")
    s.txt(780, 438, "isolator", 10, "middle", cls="g")
    s.poly([(360, 400), (560, 400), (560, 410), (700, 410)])
    s.poly([(700, 440), (570, 440), (570, 430), (360, 430)])
    s.line(860, 410, 1000, 410)
    s.line(860, 440, 1000, 440)

    # ---- J1
    s.rect(1000, 330, 180, 140, rx=3)
    s.txt(1090, 356, "J1", 13, "middle", weight="600")
    s.txt(1090, 376, "PZEM #1 TTL", 11, "middle")
    s.txt(1090, 442, "5V GND TX RX", 9, "middle", cls="g")
    s.txt(1090, 460, "→ Sheet 1", 9, "middle", cls="g")
    s.line(1080, 250, 1080, 330)
    s.line(1040, 290, 1040, 330)
    s.txt(1080, 324, "5V", 9, "middle", cls="g")
    s.txt(1040, 324, "GND", 9, "middle", cls="g")

    # ---- channel 2 DC-DC
    s.rect(700, 470, 160, 100, rx=3)
    s.txt(780, 494, "PS3 · B0505S-1W", 12, "middle", weight="600")
    s.txt(780, 512, "5 V → 5 V isolated", 10, "middle", cls="g")
    s.txt(780, 528, "1 W, 200 mA", 10, "middle", cls="g")
    s.line(660, 520, 700, 520)
    s.dot(660, 520)
    s.line(620, 560, 700, 560)
    s.dot(620, 560)
    s.line(860, 520, 1040, 520)
    s.line(860, 560, 1080, 560)
    s.line(1040, 520, 1040, 600)
    s.line(1080, 560, 1080, 600)

    # ---- channel 2 isolator
    s.rect(700, 640, 160, 80, rx=3)
    s.txt(780, 664, "ISO2 · ADuM1201", 12, "middle", weight="600")
    s.txt(780, 682, "2-channel digital", 10, "middle", cls="g")
    s.txt(780, 698, "isolator", 10, "middle", cls="g")
    s.poly([(360, 540), (520, 540), (520, 680), (700, 680)])
    s.poly([(700, 710), (540, 710), (540, 570), (360, 570)])
    s.line(860, 680, 1000, 680)
    s.line(860, 710, 1000, 710)

    # ---- J2
    s.rect(1000, 600, 180, 140, rx=3)
    s.txt(1090, 626, "J2", 13, "middle", weight="600")
    s.txt(1090, 646, "PZEM #2 TTL", 11, "middle")
    s.txt(1090, 712, "5V GND TX RX", 9, "middle", cls="g")
    s.txt(1090, 730, "→ Sheet 1", 9, "middle", cls="g")
    s.txt(1040, 594, "5V", 9, "middle", cls="g")
    s.txt(1080, 594, "GND", 9, "middle", cls="g")

    # ---- notes
    s.rect(1210, 180, 330, 560, cls="bx", rx=3)
    s.txt(1232, 210, "ISOLATION NOTES", 13, weight="600")
    s.txt(1232, 238, "Never bridge GND and GND_ISO.", 11, cls="g")
    s.txt(1232, 256, "Each PZEM gets its own isolated 5 V.", 11, cls="g")
    s.txt(1232, 286, "Without the barrier:", 11, weight="600")
    for i, t in enumerate([
        "· the ESP32, USB port and laptop",
        "  reference mains; do not touch.",
        "· a 1 k / 2 k divider on PZEM TX",
        "  protects the pin, but is NOT",
        "  galvanic isolation.",
    ]):
        s.txt(1232, 306 + i * 18, t, 11, cls="g")
    s.txt(1232, 412, "Barrier parts:", 11, weight="600")
    for i, t in enumerate([
        "· 1 W isolated DC-DC (B0505S-1W)",
        "· 2-channel digital isolator",
        "  (ADuM1201 / Si862x, ≥1 kV)",
        "· or a certified RS485 meter",
        "  (Eastron SDM120 + isolated",
        "  RS485 transceiver).",
    ]):
        s.txt(1232, 432 + i * 18, t, 11, cls="g")
    s.txt(1232, 562, "UART: 9600 8N1, Modbus RTU.", 11, cls="g")
    s.txt(1232, 580, "Keep the isolated side's ground", 11, cls="g")
    s.txt(1232, 598, "separate from the SELV ground.", 11, cls="g")
    s.txt(1232, 628, "Psst: 3.3 V TX is accepted as", 11, cls="g")
    s.txt(1232, 646, "HIGH by the PZEM's 5 V input.", 11, cls="g")

    # ---- power budget
    s.rect(80, 760, 760, 172, cls="bx", rx=3)
    s.txt(100, 786, "POWER BUDGET — 5 V SELV RAIL", 12, weight="600")
    rows = [
        ("ESP32 + Wi-Fi", "100 mA typ · 240 mA peak (TX)"),
        ("PZEM #1 + #2", "40 mA total, plus DC-DC losses"),
        ("K1 relay coil", "70 mA while energised"),
        ("LEDs + buzzer", "15 mA typ · 40 mA peak"),
        ("Supply", "5 V / 1 A isolated, 470 µF bulk at the ESP32"),
    ]
    for i, (a, b) in enumerate(rows):
        s.txt(100, 814 + i * 24, a, 11, weight="600")
        s.txt(280, 814 + i * 24, b, 11, cls="g")

    s.save(OUT / "circuit-sheet-2-isolation.svg", 2,
           "GridShield edge node — isolation and power",
           "PZEM UART/power barrier, isolated supplies and connector pinout")
    return s


# === SHEET 3 ==============================================================
def sheet3() -> Sheet:
    s = Sheet()

    # ---- MCU
    s.rect(640, 160, 360, 560, rx=3)
    s.txt(820, 196, "ESP32-WROOM-32 DevKit v1", 15, "middle", weight="600")
    s.txt(820, 220, "240 MHz · 4 MB flash · Wi-Fi 2.4 GHz", 10, "middle", cls="g")
    s.pwr(760, 160, "5V")
    s.pwr(830, 160, "3V3")
    s.pwr(900, 160, "GND")

    for y, name, sub in [
        (280, "GPIO34", "ADC1_CH6 · voltage"),
        (480, "GPIO35", "ADC1_CH7 · current"),
        (660, "GPIO14", "reset button"),
    ]:
        s.line(580, y, 640, y)
        s.txt(632, y - 5, name, 11, "end", weight="600")
        s.txt(632, y + 10, sub, 9, "end", cls="g")

    for y, name, sub in [
        (280, "GPIO25", "relay drive"),
        (400, "GPIO27", "buzzer"),
        (500, "GPIO32", "green LED"),
        (560, "GPIO33", "red LED"),
    ]:
        s.line(1000, y, 1060, y)
        s.txt(1008, y - 5, name, 11, weight="600")
        s.txt(1008, y + 10, sub, 9, cls="g")

    # ---- voltage front end
    s.rect(150, 220, 180, 120, rx=3)
    s.txt(240, 250, "ZMPT101B", 13, "middle", weight="600")
    s.txt(240, 272, "230 V → 1.0 V RMS", 10, "middle", cls="g")
    s.txt(240, 290, "adjustable gain", 10, "middle", cls="g")
    s.line(330, 280, 360, 280)
    s.res_h(360, 280)
    s.txt(385, 266, "R1 1 k", 10, "middle", cls="g")
    s.line(410, 280, 520, 280)
    for x in (440, 500):
        s.dot(x, 280)
    # bias to 3V3
    s.line(440, 280, 440, 270)
    s.res_v(440, 220)
    s.line(440, 220, 440, 208)
    s.pwr(440, 208, "3V3")
    s.txt(452, 248, "R2 10 k", 10, cls="g")
    # filter cap
    s.line(440, 280, 440, 300)
    s.cap_v(440, 300)
    s.line(440, 309, 440, 330)
    s.gnd(440, 330)
    s.txt(456, 320, "C1 220 nF", 10, cls="g")
    # lower bias leg
    s.line(500, 280, 500, 296)
    s.res_v(500, 296)
    s.line(500, 346, 500, 356)
    s.gnd(500, 356)
    s.txt(512, 324, "R3 10 k", 10, cls="g")
    # clamps
    s.line(500, 280, 580, 280)
    s.dot(580, 280)
    s.line(580, 280, 580, 266)
    s.diode_v(580, 250, down=False)
    s.line(580, 250, 580, 238)
    s.pwr(580, 238, "3V3")
    s.line(580, 280, 580, 296)
    s.diode_v(580, 296, down=True)
    s.line(580, 312, 580, 330)
    s.gnd(580, 330)
    s.txt(596, 258, "D1", 10, cls="g")
    s.txt(596, 318, "D2", 10, cls="g")
    s.txt(596, 344, "BAT54S", 10, cls="g")
    s.line(580, 280, 640, 280)
    s.txt(360, 372, "signal window: 160 samples @ 2 kHz (80 ms)", 10, cls="g")

    # ---- current front end
    s.rect(150, 420, 180, 120, rx=3)
    s.txt(240, 450, "SCT-013-030", 13, "middle", weight="600")
    s.txt(240, 472, "30 A → 1 V RMS", 10, "middle", cls="g")
    s.txt(240, 490, "voltage output", 10, "middle", cls="g")
    s.line(330, 480, 360, 480)
    s.res_h(360, 480)
    s.txt(385, 466, "R4 1 k", 10, "middle", cls="g")
    s.line(410, 480, 520, 480)
    for x in (440, 500):
        s.dot(x, 480)
    s.line(440, 480, 440, 470)
    s.res_v(440, 420)
    s.line(440, 420, 440, 408)
    s.pwr(440, 408, "3V3")
    s.txt(452, 448, "R5 10 k", 10, cls="g")
    s.line(440, 480, 440, 500)
    s.cap_v(440, 500)
    s.line(440, 509, 440, 530)
    s.gnd(440, 530)
    s.txt(456, 520, "C2 220 nF", 10, cls="g")
    s.line(500, 480, 500, 496)
    s.res_v(500, 496)
    s.line(500, 546, 500, 556)
    s.gnd(500, 556)
    s.txt(512, 524, "R6 10 k", 10, cls="g")
    s.line(500, 480, 580, 480)
    s.dot(580, 480)
    s.line(580, 480, 580, 466)
    s.diode_v(580, 450, down=False)
    s.line(580, 450, 580, 438)
    s.pwr(580, 438, "3V3")
    s.line(580, 480, 580, 496)
    s.diode_v(580, 496, down=True)
    s.line(580, 512, 580, 530)
    s.gnd(580, 530)
    s.txt(596, 458, "D3", 10, cls="g")
    s.txt(596, 518, "D4", 10, cls="g")
    s.line(580, 480, 640, 480)

    # ---- reset button
    s.line(640, 660, 610, 660)
    s.raw('<circle cx="596" cy="660" r="5" class="bf"/>')
    s.raw('<circle cx="566" cy="660" r="5" class="bf"/>')
    s.line(562, 648, 600, 648)
    s.line(581, 648, 581, 636)
    s.line(566, 660, 520, 660)
    s.gnd(520, 660)
    s.txt(581, 690, "SW1 reset", 10, "middle", cls="g")
    s.txt(581, 706, "internal pull-up · 40 ms", 9, "middle", cls="g")

    # ---- relay driver
    s.res_h(1060, 280)
    s.txt(1085, 266, "R7 1 k", 10, "middle", cls="g")
    s.line(1110, 280, 1145, 280)
    s.npn(1172, 280)
    s.txt(1108, 340, "Q1 · 2N2222", 10, "middle", cls="g")
    s.gnd(1182, 324)
    # coil + flyback
    s.line(1182, 236, 1182, 220)
    s.rect(1168, 196, 28, 24, rx=2)
    s.txt(1160, 214, "K1 coil", 10, "end", cls="g")
    s.line(1182, 196, 1182, 180)
    s.line(1182, 180, 1224, 180)
    s.pwr(1182, 180, "5V")
    s.line(1224, 180, 1224, 200)
    s.diode_v(1224, 200, down=False)
    s.line(1224, 216, 1224, 236)
    s.line(1224, 236, 1182, 236)
    s.txt(1240, 206, "D5 1N4007", 10, cls="g")
    s.txt(1060, 372, "energise-to-close · active-LOW module", 9, cls="g")

    # ---- buzzer
    s.line(1060, 400, 1100, 400)
    s.raw('<circle cx="1118" cy="400" r="16" class="bf"/>')
    s.raw('<path d="M1146 386 A 20 20 0 0 1 1146 414" class="w"/>')
    s.raw('<path d="M1154 380 A 28 28 0 0 1 1154 420" class="w"/>')
    s.line(1134, 400, 1160, 400)
    s.line(1160, 400, 1178, 400)
    s.gnd(1178, 400)
    s.txt(1118, 440, "BZ1 active buzzer", 10, "middle", cls="g")
    s.txt(1118, 456, "≤ 20 mA direct, else NPN", 9, "middle", cls="g")

    # ---- LEDs
    for y, res, led, lbl, col in (
        (500, "R8 220", "D6", "green · OK", "#16a34a"),
        (560, "R9 220", "D7", "red · TRIP", "#dc2626"),
    ):
        s.line(1060, y, 1068, y)
        s.res_h(1068, y)
        s.txt(1093, y - 14, res, 9, "middle", cls="g")
        s.line(1118, y, 1130, y)
        s.raw(f'<path d="M1130 {y - 10} L1130 {y + 10} L1150 {y} Z" fill="{col}" stroke="#111827" stroke-width="2"/>')
        s.line(1150, y - 10, 1150, y + 10)
        s.line(1150, y, 1180, y)
        s.gnd(1180, y)
        s.txt(1128, y + 32, f"{led} {lbl}", 9, "middle", cls="g")

    # ---- notes
    s.rect(80, 745, 1440, 190, cls="bx", rx=3)
    s.txt(100, 770, "FIRMWARE NOTES", 12, weight="600")
    left = [
        "ADC1 only (GPIO32–39); ADC2 is unavailable while Wi-Fi is active.",
        "GPIO34/35 are input-only — the external bias tee sets 1.65 V.",
        "Remove the per-window mean before RMS/THD; never normalise the CNN input.",
        "2 kHz sampler pinned to core 1; a Wi-Fi stall discards the partial window.",
    ]
    right = [
        "safety::begin() drives the relay open before pinMode(OUTPUT).",
        "Boot keeps it open until 3 consecutive healthy evaluations.",
        "Reset only requests re-arm; it cannot force the relay closed.",
        "A welded contact is not detectable — use a certified contactor.",
    ]
    for i, t in enumerate(left):
        s.txt(100, 798 + i * 22, "· " + t, 10.5, cls="g")
    for i, t in enumerate(right):
        s.txt(820, 798 + i * 22, "· " + t, 10.5, cls="g")
    s.txt(100, 906, "Full rationale and acceptance tests: docs/hardware-design.md · wiring.md", 10, cls="g")

    s.save(OUT / "circuit-sheet-3-mcu-io.svg", 3,
           "GridShield edge node — MCU, sensing and actuation",
           "ESP32 pin map, ADC front-end, relay driver, indicators and reset")
    return s


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sheet1()
    sheet2()
    sheet3()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
