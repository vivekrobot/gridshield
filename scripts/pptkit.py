"""Small helper layer over python-pptx for the GridShield report deck."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Inches, Pt

INK = RGBColor(0x0F, 0x17, 0x2A)
INK2 = RGBColor(0x1E, 0x29, 0x3B)
ACCENT = RGBColor(0x02, 0x84, 0xC7)
ACCENT_L = RGBColor(0x38, 0xBD, 0xF8)
MUTED = RGBColor(0x64, 0x74, 0x8B)
LINE = RGBColor(0xE2, 0xE8, 0xF0)
PANEL = RGBColor(0xF8, 0xFA, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
AMBER = RGBColor(0xD9, 0x77, 0x06)
GREEN = RGBColor(0x05, 0x96, 0x69)
RED = RGBColor(0xDC, 0x26, 0x26)
FONT = "Segoe UI"

W = 13.333
H = 7.5


def deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    return prs


def blank(prs: Presentation, bg=WHITE):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = bg
    return slide


def rect(slide, x, y, w, h, fill=None, line=None, lw=1.0, radius=None, shape=None):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    shp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            shp.adjustments[0] = radius
        except IndexError:
            pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(lw)
    shp.shadow.inherit = False
    shp.text_frame.word_wrap = True
    return shp


def text(slide, x, y, w, h, body, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=FONT, spacing=None, italic=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    lines = body.split("\n") if isinstance(body, str) else list(body)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        f = run.font
        f.name = font
        f.size = Pt(size)
        f.bold = bold
        f.italic = italic
        f.color.rgb = color
    if spacing:
        for p in tf.paragraphs:
            p.line_spacing = spacing
    return box


def _ppr(p, bullet, bcolor, before, after, indent_in):
    mar = int(Inches(indent_in))
    xml = (
        f'<a:pPr {nsdecls("a")} marL="{mar}" indent="{-mar}">'
        f'<a:spcBef><a:spcPts val="{int(before * 100)}"/></a:spcBef>'
        f'<a:spcAft><a:spcPts val="{int(after * 100)}"/></a:spcAft>'
        f'<a:buClr><a:srgbClr val="{bcolor}"/></a:buClr>'
        f'<a:buSzPct val="85000"/><a:buFont typeface="Arial"/>'
        f'<a:buChar char="{bullet}"/></a:pPr>'
    )
    new = parse_xml(xml)
    old = p._p.find(qn("a:pPr"))
    if old is not None:
        p._p.remove(old)
    p._p.insert(0, new)


def bullets(slide, x, y, w, h, items, size=15, color=INK, bullet="▪",
            bcolor="0284C7", gap=10, line_spacing=1.15):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.margin_right = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = line_spacing
        _ppr(p, bullet, bcolor, 0, gap, 0.26)
        if isinstance(item, tuple):
            head, rest = item
            r = p.add_run()
            r.text = head
            r.font.bold = True
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.color.rgb = INK2
            r2 = p.add_run()
            r2.text = rest
            r2.font.name = FONT
            r2.font.size = Pt(size)
            r2.font.color.rgb = color
        else:
            r = p.add_run()
            r.text = item
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.color.rgb = color
    return box


def header(slide, n, kicker, title, sub=None):
    rect(slide, 0.7, 0.62, 0.055, 0.34, fill=ACCENT)
    text(slide, 0.88, 0.58, 8, 0.3, kicker.upper(), 10.5, MUTED, bold=True)
    text(slide, 0.7, 0.92, 11.8, 0.65, title, 28, INK, bold=True)
    if sub:
        text(slide, 0.7, 1.55, 11.6, 0.3, sub, 12.5, MUTED)
        rect(slide, 0.7, 1.95, 11.93, 0.012, fill=LINE)
    else:
        rect(slide, 0.7, 1.68, 11.93, 0.012, fill=LINE)
    footer(slide, n)


def footer(slide, n, label="GridShield · edge-AI power quality · 2026"):
    text(slide, 0.7, 7.06, 8, 0.25, label, 9, MUTED)
    text(slide, 11.6, 7.06, 1.03, 0.25, f"{n:02d}", 9, MUTED, align=PP_ALIGN.RIGHT)


def kpi(slide, x, y, w, h, value, label, color=INK, sub=None):
    rect(slide, x, y, w, h, fill=PANEL, line=LINE, radius=0.08)
    text(slide, x + 0.22, y + 0.12, w - 0.4, 0.46, value, 24, color, bold=True)
    text(slide, x + 0.22, y + 0.56, w - 0.4, 0.26, label, 10.5, MUTED)
    if sub:
        text(slide, x + 0.22, y + 0.78, w - 0.4, 0.24, sub, 9, MUTED)


def pill(slide, x, y, w, h, label, fill=PANEL, color=INK, size=11, line=LINE):
    rect(slide, x, y, w, h, fill=fill, line=line, radius=0.5)
    text(slide, x, y + (h - 0.2) / 2 - 0.02, w, 0.22, label, size, color,
         align=PP_ALIGN.CENTER, bold=True)


def picture(slide, path, x, y, w, h):
    path = Path(path)
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    left = x + (w - pw) / 2
    top = y + (h - ph) / 2
    return slide.shapes.add_picture(str(path), Inches(left), Inches(top),
                                    Inches(pw), Inches(ph))


def reference(slide, x, y, w, h, number, lead, rest, size=8.8, gap=0.0):
    """One numbered bibliography entry with a bold lead and muted detail."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.line_spacing = 1.08
    if gap:
        p.space_after = Pt(gap)
    r0 = p.add_run()
    r0.text = f"[{number}] "
    r0.font.name = FONT
    r0.font.size = Pt(size)
    r0.font.bold = True
    r0.font.color.rgb = ACCENT
    r1 = p.add_run()
    r1.text = lead
    r1.font.name = FONT
    r1.font.size = Pt(size)
    r1.font.bold = True
    r1.font.color.rgb = INK2
    r2 = p.add_run()
    r2.text = rest
    r2.font.name = FONT
    r2.font.size = Pt(size)
    r2.font.color.rgb = MUTED
    return box


def table(slide, x, y, w, rows, col_widths, font=11, header_fill=INK2,
          stripe=PANEL, row_h=0.34):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y),
                                   Inches(w), Inches(row_h * len(rows)))
    tbl = shape.table
    tbl.first_row = True
    tbl.horz_banding = False
    # neutral table style
    tblPr = tbl._tbl.tblPr
    for el in tblPr.findall(qn("a:tableStyleId")):
        tblPr.remove(el)
    tblPr.append(parse_xml(
        f'<a:tableStyleId {nsdecls("a")}>{{2D5ABB26-0587-4C30-8999-92F81FD0307C}}</a:tableStyleId>'
    ))
    total = sum(col_widths)
    for i, width in enumerate(col_widths):
        tbl.columns[i].width = Inches(w * width / total)
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(row_h)
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.09)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if r % 2 else stripe
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(value)
            run.font.name = FONT
            run.font.size = Pt(font)
            run.font.bold = r == 0
            run.font.color.rgb = WHITE if r == 0 else INK
    return shape
