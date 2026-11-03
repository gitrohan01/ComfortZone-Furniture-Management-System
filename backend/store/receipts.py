"""Deterministic PDF rendering from immutable verified receipt snapshots."""
from decimal import Decimal
from io import BytesIO
import re
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


GREEN = colors.HexColor('#234d3c')
GOLD = colors.HexColor('#c49a5a')
MUTED = colors.HexColor('#687168')
PALE = colors.HexColor('#f1f5ef')


def _text(value):
    """Restrict dynamic text to XML-valid WinAnsi characters before escaping."""
    value = str(value or '')
    valid = ''.join(char for char in value if char in '\t\n\r' or ord(char) >= 32)
    return escape(valid.encode('cp1252', errors='replace').decode('cp1252')).replace('\n', '<br/>')


def _inr(amount):
    amount = Decimal(amount).quantize(Decimal('0.01'))
    whole, fraction = f'{amount:.2f}'.split('.')
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ','.join(groups + [tail])
    return f'INR {whole}.{fraction}'


def render_payment_receipt(receipt):
    """Return PDF bytes using only fields stored on the immutable receipt row."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm, title='Manual UPI Payment Receipt',
        author='Comfort Zone', pageCompression=0,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReceiptBrand', parent=styles['Title'], fontName='Helvetica-Bold',
        fontSize=20, leading=25, textColor=GREEN, alignment=TA_CENTER, spaceAfter=3 * mm))
    styles.add(ParagraphStyle(name='ReceiptSubtitle', parent=styles['Normal'], fontName='Helvetica',
        fontSize=9, leading=13, textColor=MUTED, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='ReceiptLabel', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=8, leading=11, textColor=MUTED))
    styles.add(ParagraphStyle(name='ReceiptValue', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=14, textColor=colors.HexColor('#202a22')))
    styles.add(ParagraphStyle(name='ReceiptAmount', parent=styles['Normal'], fontName='Helvetica-Bold',
        fontSize=18, leading=23, textColor=GREEN, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='ReceiptFoot', parent=styles['Normal'], fontName='Helvetica',
        fontSize=8, leading=12, textColor=MUTED, alignment=TA_CENTER))

    def p(value, style):
        return Paragraph(_text(value), styles[style])

    verified_at = timezone.localtime(receipt.verified_at).strftime('%d %b %Y, %I:%M %p %Z')
    story = [
        p(receipt.showroom_name_snapshot, 'ReceiptBrand'),
        p('MANUAL UPI PAYMENT RECEIPT', 'ReceiptSubtitle'),
        Spacer(1, 8 * mm),
    ]
    identifiers = [
        [p('RECEIPT NUMBER', 'ReceiptLabel'), p('ORDER REFERENCE', 'ReceiptLabel')],
        [p(receipt.receipt_number, 'ReceiptValue'), p(receipt.order_reference_snapshot or '—', 'ReceiptValue')],
    ]
    header = Table(identifiers, colWidths=[81 * mm, 81 * mm])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .6, colors.HexColor('#dce6da')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10), ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 3), ('TOPPADDING', (0, 1), (-1, 1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 11),
    ]))
    story.extend([header, Spacer(1, 8 * mm), p('PAYMENT SUMMARY', 'Heading3')])
    details = [
        ('Payment status', 'Paid / Verified'),
        ('Amount received', _inr(receipt.amount)),
        ('UPI transaction reference', receipt.transaction_reference_snapshot),
        ('UPI ID', receipt.upi_id_snapshot),
        ('Verified on', verified_at),
    ]
    rows = [[p(label, 'ReceiptLabel'), p(value, 'ReceiptAmount' if label == 'Amount received' else 'ReceiptValue')]
            for label, value in details]
    summary = Table(rows, colWidths=[54 * mm, 108 * mm])
    summary.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LINEBELOW', (0, 0), (-1, -2), .4, colors.HexColor('#e7ebe5')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.extend([summary, Spacer(1, 8 * mm), p('CUSTOMER', 'Heading3')])
    customer_rows = [
        [p('Name', 'ReceiptLabel'), p(receipt.customer_name_snapshot, 'ReceiptValue')],
    ]
    if receipt.customer_email_snapshot:
        customer_rows.append([p('Email', 'ReceiptLabel'), p(receipt.customer_email_snapshot, 'ReceiptValue')])
    customer_table = Table(customer_rows, colWidths=[54 * mm, 108 * mm])
    customer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([customer_table, Spacer(1, 8 * mm), p('VERIFICATION', 'Heading3')])
    reviewer = Table([[p('Authorized reviewer', 'ReceiptLabel'), p(receipt.reviewer_name_snapshot, 'ReceiptValue')]],
                     colWidths=[54 * mm, 108 * mm])
    reviewer.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.extend([reviewer, Spacer(1, 14 * mm),
        p('This receipt confirms that the showroom manually verified the UPI transaction against its bank or UPI records. It is not a payment gateway receipt.', 'ReceiptFoot')])

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(1.2)
        canvas.line(doc.leftMargin, A4[1] - 13 * mm, A4[0] - doc.rightMargin, A4[1] - 13 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 8)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, 'Comfort Zone  •  Manual UPI payment record')
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


def receipt_filename(receipt):
    return f'ComfortZone-Payment-Receipt-{re.sub("[^A-Za-z0-9-]", "", str(receipt.receipt_number))}.pdf'
