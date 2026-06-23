"""
Receipt numbering and PDF generation.
"""
import io
import os
import uuid
from datetime import date

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from flask import current_app
from app.db import get_db

NAVY  = colors.HexColor('#0f172a')
GOLD  = colors.HexColor('#f59e0b')
LIGHT = colors.HexColor('#f8fafc')
GREY  = colors.HexColor('#64748b')


def next_receipt_number(db) -> str:
    """Return next TCC-YYYY-NNNN number, resetting sequence each calendar year."""
    year = date.today().year
    prefix = f'TCC-{year}-'
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM receipts WHERE receipt_number LIKE ?",
        [f'{prefix}%'],
    ).fetchone()
    return f'{prefix}{row["cnt"] + 1:04d}'


def generate_pdf(receipt_row, sale_row, client_row, product_row,
                 payments_rows) -> str:
    """
    Build the receipt PDF and save to RECEIPTS_FOLDER.
    Returns the relative path string stored in receipts.pdf_path.
    """
    folder = current_app.config['RECEIPTS_FOLDER']
    os.makedirs(folder, exist_ok=True)
    filename = f'{receipt_row["receipt_number"]}-{uuid.uuid4().hex[:6]}.pdf'
    filepath = os.path.join(folder, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=10 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style  = ParagraphStyle('Title',  fontSize=20, textColor=colors.white,
                                  fontName='Helvetica-Bold', alignment=TA_LEFT)
    sub_style    = ParagraphStyle('Sub',    fontSize=10, textColor=GOLD,
                                  fontName='Helvetica', alignment=TA_LEFT)
    head_style   = ParagraphStyle('Head',   fontSize=11, textColor=NAVY,
                                  fontName='Helvetica-Bold')
    body_style   = ParagraphStyle('Body',   fontSize=10, textColor=NAVY,
                                  fontName='Helvetica')
    small_style  = ParagraphStyle('Small',  fontSize=9, textColor=GREY,
                                  fontName='Helvetica')
    right_style  = ParagraphStyle('Right',  fontSize=10, textColor=NAVY,
                                  fontName='Helvetica-Bold', alignment=TA_RIGHT)

    W = A4[0] - 30 * mm  # usable width

    # ── Header bar ────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph('<b>TEAMSYLLA</b>', title_style),
        Paragraph(
            f'<b>OFFICIAL RECEIPT</b><br/>{receipt_row["receipt_number"]}',
            ParagraphStyle('RH', fontSize=14, textColor=colors.white,
                           fontName='Helvetica-Bold', alignment=TA_RIGHT),
        ),
    ]]
    header_table = Table(header_data, colWidths=[W * 0.6, W * 0.4])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [NAVY]),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING',   (0, 0), (0, -1), 10),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 10),
    ]))

    # ── Metadata row ──────────────────────────────────────────────────────────
    issue_date   = receipt_row['issue_date'] or str(date.today())
    pay_method   = (sale_row['payment_method'] or '').replace('_', ' ').title()
    meta_data = [[
        Paragraph(f'<b>Date:</b> {issue_date}', body_style),
        Paragraph(f'<b>Method:</b> {pay_method}', body_style),
    ]]
    meta_table = Table(meta_data, colWidths=[W * 0.5, W * 0.5])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))

    # ── Client / Product info ──────────────────────────────────────────────
    client_name = client_row['name'] if client_row else '—'
    client_org  = client_row['organization'] or '' if client_row else ''
    client_ph   = client_row['phone'] or '' if client_row else ''
    product_name = product_row['name'] if product_row else '—'

    info_data = [
        [Paragraph('<b>Issued To</b>', head_style),
         Paragraph('<b>Product / Service</b>', head_style)],
        [Paragraph(client_name, body_style),
         Paragraph(product_name, body_style)],
        [Paragraph(client_org, small_style),
         Paragraph(f'Category: {(product_row["category"] or "").replace("_", " ").title()}' if product_row else '', small_style)],
        [Paragraph(client_ph, small_style), Paragraph('', small_style)],
    ]
    info_table = Table(info_data, colWidths=[W * 0.5, W * 0.5])
    info_table.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, 0), 1, GOLD),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))

    # ── Financial summary ──────────────────────────────────────────────────────
    sale_amount  = sale_row['sale_amount']
    discount     = sale_row['discount'] or 0
    net_amount   = sale_amount - discount
    amount_paid  = sum(p['amount'] for p in payments_rows)
    balance      = net_amount - amount_paid

    def gnf(v):
        return f'GNF {int(v):,}'

    fin_data = [
        ['Description', 'Amount'],
        [product_name, gnf(sale_amount)],
        ['Discount', f'- {gnf(discount)}'],
        ['Net Amount Due', gnf(net_amount)],
    ]
    fin_table = Table(fin_data, colWidths=[W * 0.7, W * 0.3])
    fin_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 10),
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, LIGHT]),
        ('GRID',          (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 10),
        ('LINEABOVE',     (0, -1), (-1, -1), 1, GOLD),
    ]))

    # ── Payments log ────────────────────────────────────────────────────────────
    pay_data = [['Payment Date', 'Method', 'Amount']]
    for p in payments_rows:
        pay_data.append([
            str(p['payment_date']),
            (p['payment_method'] or '').replace('_', ' ').title(),
            gnf(p['amount']),
        ])
    pay_data.append(['', 'Total Paid', gnf(amount_paid)])
    pay_data.append(['', 'Outstanding Balance', gnf(balance)])

    pay_table = Table(pay_data, colWidths=[W * 0.3, W * 0.4, W * 0.3])
    pay_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('ALIGN',         (2, 0), (2, -1), 'RIGHT'),
        ('ROWBACKGROUNDS',(0, 1), (-1, -3), [colors.white, LIGHT]),
        ('GRID',          (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 8),
        ('FONTNAME',      (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND',    (0, -2), (-1, -1), colors.HexColor('#fef9ee')),
        ('LINEABOVE',     (0, -2), (-1, -2), 1, GOLD),
        ('TEXTCOLOR',     (1, -1), (2, -1),
         colors.HexColor('#dc2626') if balance > 0 else colors.HexColor('#059669')),
    ]))

    # ── QR code ──────────────────────────────────────────────────────────────────
    qr_img = _qr_image(receipt_row['qr_payload'], size=30 * mm)

    footer_data = [[
        Paragraph(
            '<i>Thank you for your business with Teamsylla.<br/>'
            'Build · Deploy · Track · Grow</i>',
            ParagraphStyle('Footer', fontSize=9, textColor=GREY,
                           fontName='Helvetica-Oblique'),
        ),
        qr_img,
    ]]
    footer_table = Table(footer_data, colWidths=[W * 0.75, W * 0.25])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, 0), (-1, 0), 1, GOLD),
    ]))

    story = [
        header_table,
        Spacer(1, 4 * mm),
        meta_table,
        Spacer(1, 4 * mm),
        info_table,
        Spacer(1, 6 * mm),
        Paragraph('<b>Sale Summary</b>', head_style),
        Spacer(1, 2 * mm),
        fin_table,
        Spacer(1, 6 * mm),
        Paragraph('<b>Payment History</b>', head_style),
        Spacer(1, 2 * mm),
        pay_table,
        Spacer(1, 8 * mm),
        footer_table,
    ]
    doc.build(story)
    return filename


def _qr_image(payload: str, size: float) -> Image:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=size, height=size)
