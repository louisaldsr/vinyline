#!/usr/bin/env python3
"""Génère le PDF des cartes à imprimer en recto/verso.

Pages impaires : recto (QR codes). Pages paires : verso (année, œuvre,
morceau). Le verso est inversé gauche/droite pour tomber pile en face
avec une impression recto/verso « bord long ».

    pip3 install reportlab
    python3 scripts/make_cards.py                    # toutes les cartes
    python3 scripts/make_cards.py --de 131 --a 260   # une plage d'IDs (nouvelles cartes)
    python3 scripts/make_cards.py --test          # une seule planche pour tester
    python3 scripts/make_cards.py --taille 55     # cartes de 5,5 cm (15 par page)
"""
import argparse
import csv
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "cartes.csv"
FONTS = ROOT / "fonts"
BASE_URL = "https://louisaldsr.github.io/vinyline/?c="

pdfmetrics.registerFont(TTFont("Sans", str(FONTS / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", str(FONTS / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Cond", str(FONTS / "DejaVuSansCondensed.ttf")))

INK = (0.1, 0.1, 0.1)
GREY = (0.45, 0.45, 0.45)
CROP = (0.6, 0.6, 0.6)


def load(de, a):
    cards = []
    with CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            n = int(row["id"])
            if (de and n < de) or (a and n > a):
                continue
            cards.append(row)
    return sorted(cards, key=lambda r: int(r["id"]))


def layout(size):
    pw, ph = A4
    cols = int((pw - 10 * mm) // size)
    rows = int((ph - 20 * mm) // size)
    x0 = (pw - cols * size) / 2
    y0 = (ph - rows * size) / 2
    return cols, rows, x0, y0


def crop_marks(c, cols, rows, x0, y0, size):
    """Traits de coupe dans les marges, prolongeant chaque ligne de découpe."""
    c.setStrokeColorRGB(*CROP)
    c.setLineWidth(0.3)
    L, gap = 5 * mm, 1.5 * mm
    top, right = y0 + rows * size, x0 + cols * size
    for i in range(cols + 1):
        x = x0 + i * size
        c.line(x, y0 - gap - L, x, y0 - gap)
        c.line(x, top + gap, x, top + gap + L)
    for j in range(rows + 1):
        y = y0 + j * size
        c.line(x0 - gap - L, y, x0 - gap, y)
        c.line(right + gap, y, right + gap + L, y)


def draw_front(c, card, x, y, size, base_url):
    qr_size = size * 0.70
    w = QrCodeWidget(base_url + card["id"], barLevel="M", barBorder=0)
    bx0, by0, bx1, by1 = w.getBounds()
    d = Drawing(qr_size, qr_size, transform=[qr_size / (bx1 - bx0), 0, 0, qr_size / (by1 - by0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x + (size - qr_size) / 2, y + (size - qr_size) / 2)


def fit_lines(text, font, max_size, min_size, width, max_lines):
    """Plus grande taille de police où le texte tient sur max_lines lignes."""
    s = max_size
    while s >= min_size:
        lines = simpleSplit(text, font, s, width)
        if len(lines) <= max_lines:
            return lines, s
        s -= 0.25
    lines = simpleSplit(text, font, min_size, width)[:max_lines]
    return lines, min_size


def draw_back(c, card, x, y, size):
    pad = size * 0.09
    inner = size - 2 * pad
    cx = x + size / 2
    k = size / (65 * mm)  # facteur d'échelle par rapport à une carte de 6,5 cm

    # Type en haut
    c.setFillColorRGB(*GREY)
    c.setFont("Sans-Bold", 6.5 * k)
    c.drawCentredString(cx, y + size - pad - 5 * k, card["type"].upper())

    # Œuvre
    lines, fs = fit_lines(card["oeuvre"], "Sans-Bold", 9 * k, 6 * k, inner, 3)
    c.setFillColorRGB(*INK)
    c.setFont("Sans-Bold", fs)
    ty = y + size - pad - 15 * k
    for ln in lines:
        c.drawCentredString(cx, ty, ln)
        ty -= fs * 1.2

    # Année, au centre
    c.setFont("Sans-Bold", 30 * k)
    c.drawCentredString(cx, y + size * 0.40, card["annee"])

    # Morceau puis artiste, en bas
    by = y + pad + 2 * k
    a_lines, afs = fit_lines(card["artiste"], "Sans-Cond", 6.5 * k, 5 * k, inner, 2)
    m_lines, mfs = fit_lines(card["morceau"], "Sans", 7.5 * k, 5.5 * k, inner, 2)
    c.setFillColorRGB(*GREY)
    c.setFont("Sans-Cond", afs)
    for ln in reversed(a_lines):
        c.drawCentredString(cx, by, ln)
        by += afs * 1.2
    by += 1 * k
    c.setFillColorRGB(*INK)
    c.setFont("Sans", mfs)
    for ln in reversed(m_lines):
        c.drawCentredString(cx, by, ln)
        by += mfs * 1.2

    # ID de la carte, discret, en bas à droite
    c.setFillColorRGB(*CROP)
    c.setFont("Sans", 4.5 * k)
    c.drawRightString(x + size - size * 0.05, y + size * 0.045, card["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", type=int, help="premier ID à inclure")
    ap.add_argument("--a", type=int, help="dernier ID à inclure")
    ap.add_argument("--taille", type=float, default=65, help="côté d'une carte en mm")
    ap.add_argument("--url", default=BASE_URL, help="début de l'URL encodée dans les QR")
    ap.add_argument("--test", action="store_true", help="seulement la première planche")
    ap.add_argument("--out", help="fichier de sortie")
    args = ap.parse_args()

    cards = load(args.de, args.a)
    if not cards:
        raise SystemExit("Aucune carte trouvée.")
    size = args.taille * mm
    cols, rows, x0, y0 = layout(size)
    per_page = cols * rows
    if args.test:
        cards = cards[:per_page]

    out = Path(args.out) if args.out else ROOT / f"cartes_{cards[0]['id']}-{cards[-1]['id']}{'_test' if args.test else ''}.pdf"
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle("Vinyline")

    for p in range(0, len(cards), per_page):
        sheet = cards[p : p + per_page]
        for side in ("front", "back"):
            crop_marks(c, cols, rows, x0, y0, size)
            for i, card in enumerate(sheet):
                col, row = i % cols, i // cols
                if side == "back":
                    col = cols - 1 - col  # miroir pour le recto/verso bord long
                x = x0 + col * size
                y = y0 + (rows - 1 - row) * size
                if side == "front":
                    draw_front(c, card, x, y, size, args.url)
                else:
                    draw_back(c, card, x, y, size)
            c.showPage()

    c.save()
    pages = -(-len(cards) // per_page)
    print(f"{len(cards)} cartes, {pages} planches ({pages * 2} pages) → {out.name}")


if __name__ == "__main__":
    main()
