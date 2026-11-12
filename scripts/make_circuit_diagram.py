"""Build one consolidated circuit diagram for the GridShield hardware model.

Run:  python scripts/make_circuit_diagram.py
Out:  docs/circuit-complete.svg
      build/circuit-complete.pdf
      build/circuit-complete.png

The drawing summarises the three detailed sheets in one landscape page.  It is
a reference prototype, not a certified mains design.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_schematics import Sheet  # noqa: E402

OUT_SVG = ROOT / "docs" / "circuit-complete.svg"
OUT_PDF = ROOT / "build" / "circuit-complete.pdf"
OUT_PNG = ROOT / "build" / "circuit-complete.png"

W, H = 2400, 1600

CSS = """
  text{fill:#111827;font-family:'Segoe UI',Arial,sans-serif}
  .w{stroke:#111827;stroke-width:2.2;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .m{stroke:#b91c1c;stroke-width:3;fill:none;stroke-linecap:round;stroke-linejoin:round}
  .bx{fill:none;stroke:#111827;stroke-width:2}
  .bf{fill:#ffffff;stroke:#111827;stroke-width:2}
  .d{stroke:#6b7280;stroke-width:1.8;fill:none;stroke-dasharray:8 6}
  .j{fill:#111827;stroke:none}
  .g{fill:#4b5563}
  .panel{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1.5}
  .chip{fill:#ffffff;stroke:#94a3b8;stroke-width:1.8}
  .net{fill:#0284c7;font-weight:600}
  .warn{fill:#b91c1c;font-weight:600}
  .safe{fill:#047857;font-weight:600}
  .barrier{fill:#fef3c7;stroke:#d97706;stroke-width:1.5}
  .sm{font-size:12px}
"""


class Diagram(Sheet):
    """Sheet primitives with a 2400 x 1600 landscape frame."""

    def txt(self, x, y, t, size=13, anchor="start", cls="", weight=None):
        t = str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        super().txt(x, y, t, size, anchor, cls, weight)

    def panel(self, x, y, w, h, title, sub=None, sub_y=58):
        self.rect(x, y, w, h, cls="panel", rx=10)
        self.rect(x, y, 8, h, cls="bf", rx=3)
        self.txt(x + 24, y + 36, title, 18, weight="600")
        if sub:
            self.txt(x + 24, y + sub_y, sub, 11, cls="g")

    def chip(self, x, y, w, h, title, rows=(), size=12, row_size=9.8, fill=None):
        self.rect(x, y, w, h, cls="chip", rx=5)
        if fill:
            self.raw(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" '
                f'fill="{fill}" opacity="0.55"/>'
            )
        self.txt(x + w / 2, y + 24, title, size, "middle", weight="600")
        for i, row in enumerate(rows):
            self.txt(x + 12, y + 44 + i * 16, row, row_size, cls="g")

    def arrow(self, x1, y1, x2, y2, cls="w"):
        self.line(x1, y1, x2, y2, cls)
        dx, dy = x2 - x1, y2 - y1
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        ax, ay = x2 - ux * 12, y2 - uy * 12
        self.raw(
            f'<path d="M{x2} {y2} L{ax + px * 5} {ay + py * 5} '
            f'L{ax - px * 5} {ay - py * 5} Z" class="j"/>'
        )

    def dotline(self, x1, y1, x2, y2):
        self.line(x1, y1, x2, y2, "d")

    def res_v_short(self, x, y):
        """Vertical resistor, 30 px tall, starting at (x, y)."""
        self.raw(
            f'<path d="M{x} {y} l0 3 l-8 6 l16 6 l-16 6 l16 6 l-8 3" class="w"/>'
        )
        return y + 30

    def titleblock(self, sheet, sub):
        y = H - 108
        self.rect(24, y, W - 48, 72, cls="bx", rx=4)
        self.line(W - 450, y, W - 450, y + 72)
        self.line(W - 270, y, W - 270, y + 72)
        self.txt(48, y + 30, "GridShield — complete hardware circuit", 16, weight="600")
        self.txt(48, y + 54, sub, 11, cls="g")
        self.txt(W - 430, y + 30, f"Sheet {sheet} of 4", 13)
        self.txt(W - 430, y + 54, "Rev A · 2026-11-12", 11, cls="g")
        self.txt(W - 250, y + 30, "Prototype", 13)
        self.txt(W - 250, y + 54, "not certified", 11, cls="g")

    def save(self, path: Path, sheet, title, sub):
        self.titleblock(sheet, sub)
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}">\n<style>' + CSS + "</style>\n"
            f'<rect x="24" y="24" width="{W - 48}" height="{H - 48}" rx="4" class="bx"/>\n'
            f'<text x="56" y="74" font-size="32" font-weight="600">{title}</text>\n'
            f'<text x="56" y="106" font-size="14" fill="#4b5563">'
            "ESP32 edge node · 230 V single-phase · dual PZEM metering · "
            "isolated UART · fail-safe relay · Rev A</text>\n"
        )
        body = "\n".join(self.p)
        path.write_text(head + body + "\n</svg>\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


def mains(s: Diagram) -> None:
    s.panel(60, 140, 1340, 560,
            "A · 230 V AC POWER PATH",
            "MCB + RCD + MOV → PZEM #1 → relay K1 → load; solar branch metered by PZEM #2")

    # inlet
    for y, lbl in ((300, "L"), (430, "N"), (540, "PE")):
        s.raw(f'<circle cx="110" cy="{y}" r="8" class="bf"/>')
        s.txt(92, y + 5, lbl, 14, "end", weight="600")
    s.txt(80, 232, "MAINS IN", 10, cls="g")
    s.txt(80, 248, "230 V · 50 Hz · 12 A", 9.5, cls="g")

    # MCB + RCD
    s.line(118, 300, 170, 300, "m")
    s.rect(170, 266, 110, 68, rx=4)
    s.txt(225, 294, "MCB", 14, "middle", weight="600")
    s.txt(225, 314, "6–10 A", 10, "middle")
    s.line(280, 300, 330, 300, "m")

    s.rect(330, 266, 170, 204, cls="bx", rx=4)
    s.line(330, 300, 500, 300, "m")
    s.line(330, 430, 500, 430, "m")
    s.txt(415, 342, "RCD", 14, "middle", weight="600")
    s.txt(415, 362, "30 mA", 10, "middle")

    # MOV
    s.line(500, 300, 650, 300, "m")
    s.line(500, 430, 650, 430, "m")
    s.dot(560, 300)
    s.dot(560, 430)
    s.line(560, 300, 560, 336, "m")
    s.rect(545, 336, 30, 48, rx=3)
    s.poly([(552, 376), (568, 344)])
    s.raw('<path d="M564 342 L572 338 L568 348 Z" class="j"/>')
    s.line(560, 384, 560, 430, "m")
    s.txt(590, 368, "MOV", 11, weight="600")
    s.txt(590, 384, "275 V", 9.5, cls="g")

    # PZEM 1
    s.rect(650, 240, 310, 160, rx=4)
    s.txt(805, 268, "PZEM-004T v3 #1", 15, "middle", weight="600")
    s.txt(805, 288, "LOAD METER · addr 0x01", 10, "middle", cls="g")
    s.txt(670, 318, "U, I, P, E, f, PF · Modbus RTU 9600 8N1", 9.5, cls="g")
    s.txt(670, 334, "100 A internal shunt · no waveform output", 9.5, cls="g")
    s.line(650, 300, 650, 300, "m")
    s.line(960, 300, 1030, 300, "m")
    s.line(805, 400, 805, 430, "m")
    s.dot(805, 430)

    # PZEM 1 TTL header
    s.rect(690, 212, 230, 28, rx=3)
    s.txt(805, 231, "5V   GND   TX   RX", 10, "middle", cls="g")
    s.arrow(920, 226, 960, 226)
    s.txt(966, 230, "J1 · panel B", 10, cls="net")

    # relay K1
    s.line(1030, 300, 1030, 300, "m")
    s.rect(1030, 250, 130, 120, rx=4)
    s.txt(1095, 283, "K1", 15, "middle", weight="600")
    s.txt(1095, 303, "RELAY", 10, "middle")
    s.txt(1095, 319, "10 A NO", 10, "middle")
    s.line(1160, 300, 1250, 300, "m")

    # dashed control stub to panel E (net-name connection)
    s.dotline(1095, 370, 1095, 410)
    s.txt(1108, 420, "IN ← GPIO25 (panel E)", 10, cls="net")

    # load
    s.rect(1250, 250, 110, 180, rx=4)
    s.txt(1305, 310, "LOAD", 14, "middle", weight="600")
    s.txt(1305, 332, "0–12 A", 10, "middle")
    s.txt(1305, 350, "relay-switched", 9, "middle", cls="g")
    s.raw('<circle cx="1250" cy="300" r="6" class="bf"/>')
    s.raw('<circle cx="1250" cy="430" r="6" class="bf"/>')
    s.line(650, 430, 1250, 430, "m")

    # solar branch
    s.dot(590, 300)
    s.line(590, 300, 590, 560, "m")
    s.line(590, 560, 650, 560, "m")
    s.dot(610, 430)
    s.line(610, 430, 610, 650, "m")
    s.line(610, 650, 650, 650, "m")

    s.rect(650, 540, 150, 120, rx=4)
    s.txt(725, 573, "SOLAR", 14, "middle", weight="600")
    s.txt(725, 593, "GRID-TIE", 10, "middle")
    s.txt(725, 609, "INVERTER", 10, "middle")
    s.txt(725, 631, "≤ 3 kW", 9.5, "middle", cls="g")
    s.line(800, 560, 840, 560, "m")
    s.line(800, 650, 840, 650, "m")

    s.rect(840, 540, 310, 120, rx=4)
    s.txt(995, 568, "PZEM-004T v3 #2", 14, "middle", weight="600")
    s.txt(995, 588, "SOLAR METER · addr 0x02", 10, "middle", cls="g")
    s.txt(860, 614, "import / export split · inverter AC output", 9.5, cls="g")
    s.txt(860, 634, "TTL → J2 · 5V GND TX RX", 9.5, cls="net")

    # solar return via net labels: the inverter feeds the bus upstream of K1
    s.txt(968, 288, "L · pre-K1", 8.5, cls="net")
    s.line(1150, 560, 1230, 560, "m")
    s.line(1150, 650, 1230, 650, "m")
    s.txt(1238, 564, "L · pre-K1", 9.5, cls="net")
    s.txt(1238, 654, "N bus", 9.5, cls="g")
    s.txt(930, 682, "solar feeds the L bus upstream of K1; N returns to the neutral bus", 9.5, cls="g")

    # PE bond
    s.line(110, 548, 110, 572, "m")
    s.line(86, 572, 134, 572, "m")
    s.line(93, 580, 127, 580, "m")
    s.line(100, 588, 120, 588, "m")
    s.txt(146, 578, "PE / enclosure bond", 10, cls="g")

    # danger note in the free space right of the relay
    s.rect(1160, 438, 210, 92, cls="bx", rx=5)
    s.raw('<rect x="1160" y="438" width="210" height="92" rx="5" fill="#fef2f2"/>')
    s.txt(1176, 462, "DANGER — 230 V AC", 11, cls="warn")
    s.txt(1176, 482, "Use an enclosure, MCB + RCD", 9.5, cls="g")
    s.txt(1176, 498, "and certified terminals.", 9.5, cls="g")
    s.txt(1176, 514, "K1 is not a protective device.", 9.5, cls="g")


def isolation(s: Diagram) -> None:
    s.panel(1430, 140, 910, 560,
            "B · ISOLATED PZEM LINKS",
            "One B0505S + ADuM1201 per meter · 1 kV barrier; grounds never bridged")

    # barrier
    s.raw('<rect x="1755" y="230" width="34" height="430" class="barrier" rx="2"/>')
    s.raw(
        '<text x="1772" y="345" font-size="11" fill="#92400e" text-anchor="middle"'
        ' transform="rotate(-90 1772 345)" font-weight="600">1 kV</text>'
    )

    rows = [
        (250, "PS2 · B0505S-1W", "5 V → 5 V · 1 W", "ISO1 · ADuM1201",
         "2-channel digital isolator", "J1", "PZEM #1 TTL", 270, 300, 390, 420,
         "+5V", "GND", "GPIO17 TX", "GPIO16 RX"),
        (480, "PS3 · B0505S-1W", "5 V → 5 V · 1 W", "ISO2 · ADuM1201",
         "2-channel digital isolator", "J2", "PZEM #2 TTL", 500, 530, 610, 640,
         "+5V", "GND", "GPIO19 TX", "GPIO18 RX"),
    ]
    for (y, ps_t, ps_s, iso_t, iso_s, jname, jsub, y5, yg, ytx, yrx,
         l5, lg, ltx, lrx) in rows:
        s.chip(1500, y, 170, 70, ps_t, [ps_s])
        s.chip(1500, y + 120, 170, 80, iso_t, [iso_s])

        # SELV side
        s.line(1430, y5, 1500, y5)
        s.line(1430, yg, 1500, yg)
        s.txt(1436, y5 - 6, l5, 9.5, cls="net")
        s.txt(1436, yg - 6, lg, 9.5, cls="g")

        # isolated 5 V
        s.line(1670, y5, 1820, y5)
        s.line(1670, yg, 1820, yg)

        # UART
        s.line(1430, ytx, 1500, ytx)
        s.line(1430, yrx, 1500, yrx)
        s.txt(1436, ytx - 6, ltx, 9.5, cls="net")
        s.txt(1436, yrx - 6, lrx, 9.5, cls="net")
        s.line(1670, ytx, 1820, ytx)
        s.line(1670, yrx, 1820, yrx)

        # connector
        s.rect(1820, y, 190, 200, cls="chip", rx=5)
        s.txt(1915, y + 26, jname, 15, "middle", weight="600")
        s.txt(1915, y + 46, jsub, 10, "middle", cls="g")
        for yy, pin in ((y5, "1 · 5V"), (yg, "2 · GND"),
                        (ytx, "3 · TX"), (yrx, "4 · RX")):
            s.txt(1836, yy + 4, pin, 9.5, cls="g")

    s.txt(1454, 694,
          "Never bridge GND/GND_ISO · PZEM TX: isolator or 1k/2k divider.",
          9.5, cls="g")


def sensors(s: Diagram) -> None:
    s.panel(60, 740, 640, 410,
            "C · ADC FRONT END",
            "Bias to 1.65 V, clamp to 0–3.3 V, sample at 2 kHz", sub_y=54)

    def channel(y, module, module_sub, r_series, cap, net, label):
        s.txt(90, y - 2, label, 9.5, cls="g", weight="600")
        s.chip(90, y, 160, 92, module, [module_sub[0], module_sub[1]], size=12.5)
        s.line(250, y + 40, 300, y + 40)
        s.res_h(300, y + 40)
        s.txt(325, y + 26, r_series, 9, "middle", cls="g")
        s.line(350, y + 40, 390, y + 40)
        node = y + 40

        # bias tee
        s.dot(390, node)
        s.line(390, node, 390, node - 8)
        s.res_v_short(390, node - 38)
        s.line(390, node - 38, 390, node - 44)
        s.pwr(390, node - 44, "3V3")
        s.txt(404, node - 26, "10k", 9, cls="g")
        s.line(390, node, 390, node + 18)
        s.cap_v(390, node + 18)
        s.line(390, node + 27, 390, node + 40)
        s.gnd(390, node + 40)
        s.txt(404, node + 28, cap, 9, cls="g")

        # lower leg
        s.line(440, node, 440, node + 14)
        s.res_v_short(440, node + 14)
        s.gnd(440, node + 44)
        s.txt(454, node + 36, "10k", 9, cls="g")

        # clamps
        s.line(440, node, 520, node)
        s.dot(520, node)
        s.line(520, node, 520, node - 12)
        s.diode_v(520, node - 28, down=False)
        s.line(520, node - 28, 520, node - 38)
        s.pwr(520, node - 38, "3V3")
        s.line(520, node, 520, node + 12)
        s.diode_v(520, node + 12, down=True)
        s.line(520, node + 28, 520, node + 38)
        s.gnd(520, node + 38)
        s.txt(536, node - 18, "BAT54S", 9, cls="g")
        s.arrow(520, node, 620, node)
        s.txt(626, node + 4, net, 11, cls="net")

    channel(840, "ZMPT101B", ["230 V → 1.0 V RMS", "adjustable gain"],
            "R1 1k", "C1 220n", "→ GPIO34", "VOLTAGE CHANNEL")
    channel(1020, "SCT-013-030", ["30 A → 1 V RMS", "voltage output"],
            "R4 1k", "C2 220n", "→ GPIO35", "CURRENT CHANNEL")

    s.txt(84, 1142,
          "ADC1 only · GPIO34/35 are input-only · external bias sets the DC operating point",
          9.5, cls="g")


def controller(s: Diagram) -> None:
    s.panel(740, 740, 520, 410,
            "D · ESP32 DEVKIT V1",
            "240 MHz · 4 MB flash · Wi-Fi 2.4 GHz · 3.3 V logic")

    s.rect(790, 820, 420, 290, cls="chip", rx=6)
    s.txt(1000, 850, "ESP32-WROOM-32", 15, "middle", weight="600")
    s.txt(1000, 870, "DevKit v1 · ADC1 only", 9.5, "middle", cls="g")

    left = [
        (900, "5V", "5V"),
        (930, "GND", "GND"),
        (980, "GPIO34", "← V"),
        (1010, "GPIO35", "← I"),
        (1050, "GPIO14", "← SW1"),
    ]
    for y, pin, net in left:
        s.line(740, y, 790, y)
        s.txt(802, y + 4, pin, 10.5, weight="600")
        s.txt(744, y - 6, net, 9.5, cls="net")

    right = [
        (920, "GPIO25", "K1"),
        (950, "GPIO27", "BZ1"),
        (980, "GPIO32", "D6"),
        (1010, "GPIO33", "D7"),
        (1050, "GPIO17/16", "J1"),
        (1080, "GPIO19/18", "J2"),
    ]
    for y, pin, net in right:
        s.line(1210, y, 1260, y)
        s.txt(1198, y + 4, pin, 9.5, "end", weight="600")
        s.txt(1214, y - 6, "→" + net, 9.5, cls="net")

    s.txt(1000, 1098, "Wi-Fi STA → MQTT broker → Streamlit SCADA", 9.5, "middle", cls="g")


def actuation(s: Diagram) -> None:
    s.panel(1280, 740, 420, 410,
            "E · RELAY DRIVER",
            "Opto-isolated 5 V module · active-LOW · fail-safe")

    s.chip(1340, 840, 270, 170, "K1 RELAY MODULE",
           ["1-channel · 5 V coil · 10 A NO",
            "opto-isolated input", "screw terminals COM / NO"])
    for y, label in ((900, "+5V"), (930, "GND"), (960, "GPIO25")):
        s.line(1280, y, 1340, y)
        s.txt(1286, y - 6, label, 9.5, cls="net")

    s.line(1610, 920, 1670, 920)
    s.line(1610, 950, 1670, 950)
    s.txt(1616, 912, "COM → L", 9.5, cls="m")
    s.txt(1616, 972, "NO → LOAD L", 9.5, cls="m")
    s.txt(1304, 1040, "IN = LOW closes · RELAY_CLOSED_LEVEL = LOW", 9.8, cls="g")
    s.txt(1304, 1064, "Boot drives open before pinMode; reset cannot force close", 9.8, cls="g")
    s.txt(1304, 1088, "Bare coil alternative: NPN + 1N4007 flyback", 9.8, cls="g")
    s.txt(1304, 1112, "Add an RC snubber for inductive loads", 9.8, cls="g")


def indicators(s: Diagram) -> None:
    s.panel(1740, 740, 600, 410,
            "F · INDICATORS, BUZZER & RESET",
            "GPIO27 · GPIO32 · GPIO33 · GPIO14")

    # buzzer
    s.line(1740, 850, 1800, 850)
    s.txt(1746, 842, "GPIO27", 9.5, cls="net")
    s.raw('<circle cx="1818" cy="850" r="18" class="bf"/>')
    s.raw('<path d="M1846 836 A 20 20 0 0 1 1846 864" class="w"/>')
    s.raw('<path d="M1854 830 A 28 28 0 0 1 1854 870" class="w"/>')
    s.line(1836, 850, 1872, 850)
    s.gnd(1872, 850)
    s.txt(1764, 892, "BZ1 active buzzer · ≤ 20 mA direct", 9.8, cls="g")
    s.txt(1764, 910, "use an NPN driver above 20 mA", 9.8, cls="g")

    # LEDs
    for y, res, led, label, colour in (
        (970, "R8 220", "D6", "green · OK · GPIO32", "#16a34a"),
        (1040, "R9 220", "D7", "red · TRIP · GPIO33", "#dc2626"),
    ):
        s.line(1740, y, 1800, y)
        s.res_h(1800, y)
        s.txt(1825, y - 14, res, 9, "middle", cls="g")
        s.line(1850, y, 1870, y)
        s.raw(
            f'<path d="M1870 {y - 11} L1870 {y + 11} L1892 {y} Z" '
            f'fill="{colour}" stroke="#111827" stroke-width="2"/>'
        )
        s.line(1892, y - 11, 1892, y + 11)
        s.line(1892, y, 1920, y)
        s.gnd(1920, y)
        s.txt(1764, y + 32, f"{led} {label}", 9.8, cls="g")

    # reset
    s.line(1740, 1096, 1800, 1096)
    s.raw('<circle cx="1800" cy="1096" r="5" class="bf"/>')
    s.raw('<circle cx="1830" cy="1096" r="5" class="bf"/>')
    s.line(1804, 1086, 1826, 1086)
    s.line(1830, 1101, 1830, 1106)
    s.gnd(1830, 1106)
    s.txt(1764, 1140, "SW1 reset → GPIO14 · internal pull-up · active-LOW", 9.8, cls="g")


def power(s: Diagram) -> None:
    s.panel(60, 1200, 960, 260,
            "G · POWER DISTRIBUTION",
            "5 V / 2 A SELV supply; the PZEM rails are separately isolated")

    s.chip(90, 1290, 220, 110, "PS1 · 5 V / 2 A",
           ["HLK-PM01 or SELV adapter", "100–240 V AC input", "5 V SELV output"],
           size=13)

    s.line(310, 1320, 960, 1320)
    s.line(310, 1400, 960, 1400)
    s.txt(312, 1312, "+5V", 10, cls="net")
    s.txt(312, 1420, "GND", 10, cls="g")

    loads = [
        (380, "ESP32 + Wi-Fi", "100 mA · 240 mA peak", "470 µF bulk"),
        (540, "K1 relay", "70 mA while closed", "separate feed"),
        (700, "ZMPT + SCT", "20 mA total", "3V3 from devkit"),
        (860, "LEDs + BZ1", "15 mA · 40 mA peak", "pulsed"),
    ]
    for x, name, load, note in loads:
        s.dot(x, 1320)
        s.line(x, 1320, x, 1350)
        s.txt(x + 10, 1300, name, 9.5, weight="600")
        s.txt(x + 10, 1316, load, 9, cls="g")
        s.txt(x + 10, 1354, note, 9, cls="g")

    s.txt(84, 1444,
          "Each PZEM has its own B0505S-1W rail (panel B); never join GND to GND_ISO.",
          9.5, cls="g")


def notes(s: Diagram) -> None:
    s.panel(1040, 1200, 1300, 260,
            "H · WIRING NOTES & SAFETY",
            "Reference prototype — not a certified protective device")

    left = [
        "MCB 6–10 A + 30 mA RCD upstream; K1 is not protection.",
        "PZEM TTL may be mains-referenced on some clones.",
        "Never bridge GND and GND_ISO; verify before USB.",
        "PZEM TX is 5 V: isolator or 1k/2k divider.",
    ]
    right = [
        "ADC1 only; GPIO34/35 are input-only.",
        "160 samples @ 2 kHz = 80 ms; remove the window mean.",
        "Relay active-LOW; boot drives open before pinMode.",
        "≥ 6 mm creepage, 300 V terminals, enclosure barrier.",
    ]
    for i, t in enumerate(left):
        s.txt(1064, 1294 + i * 24, "• " + t, 10.2, cls="g")
    for i, t in enumerate(right):
        s.txt(1700, 1294 + i * 24, "• " + t, 10.2, cls="g")

    s.txt(1064, 1428,
          "Full rationale: docs/hardware-design.md · docs/wiring.md · docs/safety.md",
          9.5, cls="g")


def build_svg() -> Path:
    s = Diagram()
    mains(s)
    isolation(s)
    sensors(s)
    controller(s)
    actuation(s)
    indicators(s)
    power(s)
    notes(s)
    s.save(OUT_SVG, 4,
           "GridShield — complete hardware circuit",
           "ESP32 edge node · dual PZEM · isolated UART · fail-safe relay")
    return OUT_SVG


def render(svg: Path) -> None:
    from playwright.sync_api import sync_playwright

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>@page{size:2400px 1600px;margin:0}"
        "html,body{margin:0;padding:0;background:#fff}"
        "svg{display:block}</style></head><body>"
        + svg.read_text(encoding="utf-8")
        + "</body></html>"
    )
    tmp = ROOT / "build" / "circuit-complete.html"
    tmp.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1.5)
        page.goto(tmp.as_uri(), wait_until="load")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_PNG), full_page=True)
        page.pdf(path=str(OUT_PDF), width=f"{W}px", height=f"{H}px",
                 print_background=True, margin={"top": "0", "bottom": "0",
                                                "left": "0", "right": "0"})
        browser.close()
    print(f"wrote {OUT_PNG.relative_to(ROOT)}")
    print(f"wrote {OUT_PDF.relative_to(ROOT)}")


def main() -> int:
    OUT_PDF.parent.mkdir(exist_ok=True)
    svg = build_svg()
    render(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
