"""Bounded CSV and PDF exports for the staff reporting APIs."""
import csv
import html
import io
from decimal import Decimal

from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.response import Response

from . import reporting
from .report_views import (
    ATTEMPT_STATUSES, CanViewPaymentReport, CanViewReports, ORDER_STATUSES,
    PAYMENT_STATUSES, PURCHASE_STATUSES, REVIEW_ACTIONS, _choice, _date_range,
    _positive_id, _search,
)
CSV_LIMIT = 10_000
PDF_LIMIT = 2_000

# Column definitions keep exported fields deliberate and prevent private model
# fields (addresses, image paths, credentials) from leaking into downloads.
REPORTS = {
    'sales': {
        'title': 'Sales report',
        'headers': ['Record type', 'Date / date basis', 'Orders', 'Order value (INR)', 'Cancelled orders',
                    'Cancelled value (INR)', 'Pending payment value (INR)', 'Gross verified payments (INR)',
                    'Confirmed refunds (INR)', 'Net verified payments (INR)', 'Rejected attempts',
                    'Paid orders without receipts', 'Paid orders without receipts value (INR)'],
        'keys': ['record_type', 'date', 'order_count', 'order_value', 'cancelled_order_count',
                 'cancelled_order_value', 'pending_payment_value', 'verified_revenue',
                 'confirmed_refunds', 'net_verified_revenue', 'rejected_attempt_count',
                 'paid_orders_without_receipts_count',
                 'paid_orders_without_receipts_value'],
        'numeric': {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12},
    },
    'orders': {
        'title': 'Orders report',
        'headers': ['Order reference', 'Customer', 'Linked account', 'Date', 'Items', 'Total (INR)', 'Payment status', 'Fulfilment status'],
        'keys': ['order_reference', 'customer_name', 'linked_account', 'created_at', 'item_summary', 'total_amount', 'payment_status', 'fulfillment_status'],
        'numeric': {5},
    },
    'inventory': {
        'title': 'Inventory report',
        'headers': ['Product', 'Category', 'Available stock', 'Price (INR)', 'Active'],
        'keys': ['name', 'category__name', 'stock', 'price', 'is_active'], 'numeric': {2, 3},
    },
    'low-stock': {
        'title': 'Low-stock report',
        'headers': ['Product', 'Category', 'Current stock', 'Threshold', 'Active'],
        'keys': ['name', 'category__name', 'stock', 'threshold', 'is_active'], 'numeric': {2, 3},
    },
    'customers': {
        'title': 'Customer report',
        'headers': ['Customer ID', 'Username', 'Customer name', 'Email', 'Orders', 'Verified payments (INR)', 'Pending order value (INR)', 'Last order date'],
        'keys': ['customer_id', 'username', 'customer_name', 'email', 'order_count', 'verified_payment_total', 'pending_order_value', 'last_order_date'],
        'numeric': {0, 4, 5, 6},
    },
    'vendor-purchases': {
        'title': 'Vendor purchases report',
        'headers': ['Vendor', 'Purchase ID', 'Product', 'Quantity', 'Unit cost (INR)', 'Purchase value (INR)', 'Status', 'Purchase date'],
        'keys': ['vendor__name', 'id', 'product__name', 'quantity', 'unit_cost', 'purchase_value', 'status', 'purchased_at'],
        'numeric': {1, 3, 4, 5},
    },
    'payment-verification': {
        'title': 'Payment verification report',
        'headers': ['Order reference', 'Customer', 'Attempt ID', 'Transaction reference', 'Expected amount (INR)', 'Status', 'Submitted', 'Reviewer', 'Review date', 'Rejection remarks'],
        'keys': ['order_reference', 'customer_name', 'attempt_id', 'transaction_reference', 'expected_amount', 'status', 'submitted_at', 'reviewer', 'reviewed_at', 'rejection_remarks'],
        'numeric': {2, 4},
    },
}


def _format_value(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat(sep=' ') if hasattr(value, 'hour') else value.isoformat()
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    return str(value)


def _safe_csv_text(value):
    """Quote formula-like text, including strings with leading whitespace."""
    rendered = _format_value(value)
    if isinstance(value, (int, float, Decimal, bool)):
        return rendered
    if rendered.lstrip()[:1] in ('=', '+', '-', '@'):
        return "'" + rendered
    return rendered


class _Echo:
    def write(self, value):
        return value


def _csv_response(report_key, rows, count, *, start=None, end=None, summary=None):
    spec = REPORTS[report_key]
    if count > CSV_LIMIT:
        return Response({'detail': f'Export exceeds the {CSV_LIMIT} row CSV limit.'}, status=400)

    def generate():
        writer = csv.writer(_Echo(), lineterminator='\r\n')
        yield '\ufeff'
        yield writer.writerow(spec['headers'])
        export_rows = rows
        if report_key == 'sales' and summary is not None:
            summary_row = {
                'record_type': 'Period summary; order/pending by created_at, revenue by verified_at, rejections by reviewed_at',
                'date': '',
                **{key: value for key, value in summary.items() if key != 'date_basis'},
            }
            export_rows = [*rows, summary_row]
        for row in export_rows:
            values = []
            for index, key in enumerate(spec['keys']):
                value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
                # Boolean and numeric columns remain unmodified numeric values.
                if index in spec['numeric']:
                    values.append(_format_value(value))
                elif isinstance(value, bool):
                    values.append(_format_value(value))
                else:
                    values.append(_safe_csv_text(value))
            yield writer.writerow(values)

    suffix = f'_{start.isoformat()}_{end.isoformat()}' if start and end else ''
    response = StreamingHttpResponse(generate(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{report_key}_report{suffix}.csv"'
    _private_headers(response)
    return response


class _NumberedCanvas:
    """Canvas factory that adds a page number after ReportLab lays out pages."""
    def __new__(cls, *args, **kwargs):
        from reportlab.pdfgen.canvas import Canvas

        class Numbered(Canvas):
            def __init__(self, *cargs, **ckwargs):
                super().__init__(*cargs, **ckwargs)
                self._saved_pages = []

            def showPage(self):
                self._saved_pages.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._saved_pages)
                for state in self._saved_pages:
                    self.__dict__.update(state)
                    self.setFont('Helvetica', 8)
                    self.setFillColor(colors.HexColor('#64748b'))
                    self.drawRightString(self._pagesize[0] - 12 * mm, 8 * mm, f'Page {self._pageNumber} of {total}')
                    Canvas.showPage(self)
                Canvas.save(self)
        return Numbered(*args, **kwargs)


def _private_headers(response):
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'


def _pdf_response(report_key, rows, count, *, start=None, end=None, context=None):
    if count > PDF_LIMIT:
        return Response({'detail': f'Export exceeds the {PDF_LIMIT} row PDF limit.'}, status=400)
    spec = REPORTS[report_key]
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=20 * mm, bottomMargin=15 * mm, title=spec['title'])
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#17324d'), alignment=TA_LEFT)
    cell_style = ParagraphStyle('ReportCell', parent=styles['BodyText'], fontName='Helvetica', fontSize=7, leading=9, spaceAfter=0)
    story = [Paragraph(html.escape(spec['title']), title_style)]
    if start and end:
        story.append(Paragraph(f'Date range: {start.isoformat()} to {end.isoformat()}', styles['Normal']))
    story.append(Paragraph(f'Generated: {timezone.localtime().strftime("%Y-%m-%d %H:%M %Z")}', styles['Normal']))
    for label, value in (context or {}).items():
        if str(label).startswith('_'):
            continue
        safe_label = html.escape(str(label))
        safe_value = html.escape(str(value))
        story.append(Paragraph(f'{safe_label}: {safe_value}', styles['Normal']))
    story.append(Spacer(1, 5 * mm))
    table_data = [[Paragraph(html.escape(header), ParagraphStyle('Header', parent=cell_style, textColor=colors.white, fontName='Helvetica-Bold')) for header in spec['headers']]]
    for row in rows:
        cells = []
        for key in spec['keys']:
            value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
            rendered = _format_value(value)
            # Bound extreme free text so one maliciously long field cannot create
            # an effectively unpageable table row. CSV preserves the full value.
            if len(rendered) > 1200:
                rendered = rendered[:1200] + '… [truncated]'
            cells.append(Paragraph(html.escape(rendered).replace('\n', '<br/>'), cell_style))
        table_data.append(cells)
    available_width = landscape(A4)[0] - 24 * mm
    column_width = available_width / len(spec['headers'])
    table = Table(table_data, colWidths=[column_width] * len(spec['headers']), repeatRows=1, splitByRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17324d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    doc.build(story, canvasmaker=_NumberedCanvas)
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    suffix = f'_{start.isoformat()}_{end.isoformat()}' if start and end else ''
    response['Content-Disposition'] = f'attachment; filename="{report_key}_report{suffix}.pdf"'
    _private_headers(response)
    return response


def _export_response(request, report_key, rows, count, *, start=None, end=None, context=None):
    file_format = request.query_params.get('format', 'csv').lower()
    if file_format == 'csv':
        summary = (context or {}).get('_sales_summary')
        exported_row_count = count + 1 if report_key == 'sales' and summary is not None else count
        return _csv_response(report_key, rows, exported_row_count, start=start, end=end, summary=summary)
    if file_format == 'pdf':
        return _pdf_response(report_key, rows, count, start=start, end=end, context=context)
    return Response({'format': ['Choose csv or pdf.']}, status=400)


def _materialize_limited(rows, limit):
    # Each export is bounded before materialization; iterator avoids loading the
    # full queryset when enforcing the cap.
    result = []
    iterator = rows.iterator(chunk_size=200) if hasattr(rows, 'iterator') else iter(rows)
    for row in iterator:
        if len(result) == limit + 1:
            break
        result.append(row)
    return result, len(result)


def _rows_for(request, report_key):
    context = {}
    start = end = None
    if report_key in ('sales', 'orders', 'customers', 'vendor-purchases', 'payment-verification'):
        parsed, _, error = _date_range(request)
        if error:
            return None, None, None, None, error
        start, end, start_dt, stop_dt = parsed
        context['Date basis'] = {
            'sales': 'Orders by creation date; receipts by verification date; rejections by review date',
            'orders': 'Order creation date', 'customers': 'Linked account orders created in range',
            'vendor-purchases': 'Purchase date', 'payment-verification': 'Attempt submission date',
        }[report_key]
    if report_key in ('orders', 'customers', 'vendor-purchases', 'payment-verification', 'inventory', 'low-stock'):
        search, error = _search(request)
        if error:
            return None, None, None, None, error
    else:
        search = ''
    if report_key == 'sales':
        rows = reporting.sales_daily(start_dt, stop_dt)
        summary = reporting.sales_summary(start_dt, stop_dt)
        context.update({
            'Orders': summary['order_count'],
            'Order value (non-cancelled)': f"INR {summary['order_value']:.2f}",
            'Cancelled order value': f"INR {summary['cancelled_order_value']:.2f}",
            'Gross verified payments (receipt verification date)': f"INR {summary['verified_revenue']:.2f}",
            'Confirmed refunds (refund confirmation date)': f"INR {summary['confirmed_refunds']:.2f}",
            'Net verified payments': f"INR {summary['net_verified_revenue']:.2f}",
            'Pending payment value': f"INR {summary['pending_payment_value']:.2f}",
            'Cancelled orders': summary['cancelled_order_count'],
            'Paid orders without receipts': summary['paid_orders_without_receipts_count'],
            'Paid orders without receipts value': f"INR {summary['paid_orders_without_receipts_value']:.2f}",
            'Rejected attempts': summary['rejected_payment_attempt_count'],
            '_sales_summary': summary,
        })
        return rows, len(rows), start, end, None, context
    if report_key == 'orders':
        payment, error = _choice(request, 'payment_status', PAYMENT_STATUSES | {'unrecorded'})
        if error: return None, None, None, None, error
        fulfillment, error = _choice(request, 'fulfillment_status', ORDER_STATUSES)
        if error: return None, None, None, None, error
        qs = reporting.order_rows(start_dt, stop_dt, search=search, payment_status=payment, fulfillment_status=fulfillment)
        converter = reporting.serialize_order
    elif report_key == 'inventory':
        active, error = _choice(request, 'active', {'true', 'false', 'all'}, default='all')
        if error: return None, None, None, None, error
        category_id, error = _positive_id(request, 'category_id')
        if error: return None, None, None, None, error
        qs = reporting.inventory_rows(search=search, category_id=category_id, active='' if active == 'all' else active)
        converter = lambda row: row
    elif report_key == 'low-stock':
        active, error = _choice(request, 'active', {'true', 'false', 'all'}, default='true')
        if error: return None, None, None, None, error
        category_id, error = _positive_id(request, 'category_id')
        if error: return None, None, None, None, error
        threshold, qs = reporting.low_stock_rows(search=search, category_id=category_id, active='' if active == 'all' else active)
        context['Configured threshold'] = threshold
        # Match the report API's current stock threshold field.
        rows, count = _materialize_limited(
            ({**row, 'threshold': threshold} for row in qs), max(CSV_LIMIT, PDF_LIMIT)
        )
        return rows, count, None, None, None, context
    elif report_key == 'customers':
        qs = reporting.customer_rows(start_dt, stop_dt, search=search)
        converter = reporting.serialize_customer
    elif report_key == 'vendor-purchases':
        purchase_status, error = _choice(request, 'status', PURCHASE_STATUSES)
        if error: return None, None, None, None, error
        vendor_id, error = _positive_id(request, 'vendor_id')
        if error: return None, None, None, None, error
        _, qs = reporting.vendor_purchase_rows(start_dt, stop_dt, search=search, purchase_status=purchase_status, vendor_id=vendor_id)
        converter = lambda row: row
    else:
        attempt_status, error = _choice(request, 'status', ATTEMPT_STATUSES)
        if error: return None, None, None, None, error
        review_action, error = _choice(request, 'review_action', REVIEW_ACTIONS | {'unreviewed'})
        if error: return None, None, None, None, error
        qs = reporting.payment_verification_rows(start_dt, stop_dt, search=search, attempt_status=attempt_status, review_action=review_action)
        converter = reporting.serialize_payment_attempt
    # Count plus bounded conversion ensures the API filters and export limit apply
    # to the exact same database queryset.
    limit = max(CSV_LIMIT, PDF_LIMIT)
    materialized, _ = _materialize_limited(qs, limit)
    normalized = [converter(row) for row in materialized]
    return normalized, len(normalized), start, end, None, context


def _handle_export(request, report_key):
    built = _rows_for(request, report_key)
    # Validation failures return a Response as the fifth tuple value.
    if len(built) == 5:
        return built[-1]
    rows, count, start, end, _, context = built
    return _export_response(request, report_key, rows, count, start=start, end=end, context=context)


class ExportContentNegotiation(DefaultContentNegotiation):
    """Keep DRF's renderer format override from consuming export `format`."""
    def filter_renderers(self, renderers, format):
        # The export handler owns this parameter and validates csv/pdf itself.
        # Leaving the normal renderers available prevents DRF from raising its
        # default Http404 for formats that are not renderer names.
        return renderers


def _disable_drf_format_override(view):
    """Reserve the `format` query parameter for csv/pdf export selection."""
    view.cls.content_negotiation_class = ExportContentNegotiation
    return view


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_sales(request):
    return _handle_export(request, 'sales')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_orders(request):
    return _handle_export(request, 'orders')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_inventory(request):
    return _handle_export(request, 'inventory')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_low_stock(request):
    return _handle_export(request, 'low-stock')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_customers(request):
    return _handle_export(request, 'customers')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def export_vendor_purchases(request):
    return _handle_export(request, 'vendor-purchases')


@_disable_drf_format_override
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewPaymentReport])
def export_payment_verification(request):
    return _handle_export(request, 'payment-verification')
