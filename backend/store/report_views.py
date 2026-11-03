"""Authenticated and bounded REST endpoints for showroom business reports."""
from datetime import date, timedelta
import re

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import CustomerOrder, PaymentAttempt, PaymentReviewEvent, VendorPurchase
from .reporting import (
    customer_rows, date_range_datetimes, inventory_rows, low_stock_rows,
    order_rows, payment_verification_rows, sales_daily, sales_summary,
    serialize_order, serialize_customer, serialize_payment_attempt, vendor_purchase_rows,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
ATTEMPT_STATUSES = {value for value, _label in PaymentAttempt.STATUS_CHOICES}
REVIEW_ACTIONS = {PaymentReviewEvent.ACTION_VERIFIED, PaymentReviewEvent.ACTION_REJECTED}
ORDER_STATUSES = {value for value, _label in CustomerOrder.STATUS}
PAYMENT_STATUSES = {value for value, _label in CustomerOrder.PAYMENT_STATUS if value}
PURCHASE_STATUSES = {value for value, _label in VendorPurchase.STATUS}


class CanViewReports(permissions.BasePermission):
    message = 'The store.view_reports permission is required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff
                    and request.user.has_perm('store.view_reports'))


class CanViewPaymentReport(permissions.BasePermission):
    message = 'The store.view_reports and store.verify_payment permissions are required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff
                    and user.has_perm('store.view_reports') and user.has_perm('store.verify_payment'))


def _date_range(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=29)
    raw_start = request.query_params.get('date_from')
    raw_end = request.query_params.get('date_to')
    try:
        if (raw_start and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_start)) or (raw_end and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_end)):
            raise ValueError('Invalid date format')
        start = date.fromisoformat(raw_start) if raw_start else default_start
        end = date.fromisoformat(raw_end) if raw_end else today
    except (TypeError, ValueError):
        return None, None, Response({'detail': 'Dates must use YYYY-MM-DD format.'}, status=400)
    if start > end:
        return None, None, Response({'detail': 'date_from must be on or before date_to.'}, status=400)
    start_dt, stop_dt = date_range_datetimes(start, end)
    return (start, end, start_dt, stop_dt), None, None


def _page_args(request):
    try:
        page = int(request.query_params.get('page', '1'))
        page_size = int(request.query_params.get('page_size', str(DEFAULT_PAGE_SIZE)))
    except (TypeError, ValueError):
        return None, None, Response({'detail': 'page and page_size must be positive integers.'}, status=400)
    if page < 1 or page_size < 1:
        return None, None, Response({'detail': 'page and page_size must be positive integers.'}, status=400)
    if page_size > MAX_PAGE_SIZE:
        return None, None, Response({'detail': f'page_size cannot exceed {MAX_PAGE_SIZE}.'}, status=400)
    return page, page_size, None


def _paginate(queryset, request, serializer):
    page_number, page_size, error = _page_args(request)
    if error:
        return None, error
    paginator = Paginator(queryset, page_size)
    try:
        page = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        return None, Response({'detail': 'Requested page is outside the available results.'}, status=400)
    return {
        'count': paginator.count,
        'page': page.number,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': [serializer(row) for row in page.object_list],
    }, None


def _search(request):
    value = request.query_params.get('search', '').strip()
    if len(value) > 200:
        return None, Response({'search': ['Search text cannot exceed 200 characters.']}, status=400)
    return value, None


def _choice(request, key, choices, *, default=''):
    value = request.query_params.get(key, default)
    if value and value not in choices:
        return None, Response({key: [f'Choose one of: {", ".join(sorted(choices))}.']}, status=400)
    return value, None


def _positive_id(request, key):
    value = request.query_params.get(key)
    if not value:
        return None, None
    try:
        parsed = int(value)
    except ValueError:
        return None, Response({key: ['Enter a positive integer.']}, status=400)
    if parsed < 1:
        return None, Response({key: ['Enter a positive integer.']}, status=400)
    return parsed, None


def _range_payload(start, end):
    return {'date_from': start.isoformat(), 'date_to': end.isoformat()}


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_summary(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    return Response({
        'date_range': _range_payload(start, end),
        'metrics': sales_summary(start_dt, stop_dt),
        'date_basis': 'Metric-specific; see metrics.date_basis.',
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_sales(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    daily, error = _paginate(sales_daily(start_dt, stop_dt), request, lambda row: row)
    if error:
        return error
    return Response({'date_range': _range_payload(start, end), 'summary': sales_summary(start_dt, stop_dt), 'daily': daily})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_orders(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    search, error = _search(request)
    if error:
        return error
    payment, error = _choice(request, 'payment_status', PAYMENT_STATUSES | {'unrecorded'})
    if error:
        return error
    fulfillment, error = _choice(request, 'fulfillment_status', ORDER_STATUSES)
    if error:
        return error
    rows = order_rows(start_dt, stop_dt, search=search, payment_status=payment, fulfillment_status=fulfillment)
    data, error = _paginate(rows, request, serialize_order)
    if error:
        return error
    return Response({'date_range': _range_payload(start, end), 'date_basis': 'CustomerOrder.created_at', **data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_inventory(request):
    search, error = _search(request)
    if error:
        return error
    active, error = _choice(request, 'active', {'true', 'false', 'all'}, default='all')
    if error:
        return error
    category_id, error = _positive_id(request, 'category_id')
    if error:
        return error
    rows = inventory_rows(search=search, category_id=category_id, active='' if active == 'all' else active)
    data, error = _paginate(rows, request, lambda row: {
        'product_id': row['id'], 'product': row['name'], 'category_id': row['category_id'],
        'category': row['category__name'], 'current_stock': row['stock'], 'current_price': row['price'],
        'active': row['is_active'],
    })
    if error:
        return error
    return Response({'date_basis': 'Current product and category values; date filters do not apply.', **data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_low_stock(request):
    search, error = _search(request)
    if error:
        return error
    active, error = _choice(request, 'active', {'true', 'false', 'all'}, default='true')
    if error:
        return error
    category_id, error = _positive_id(request, 'category_id')
    if error:
        return error
    threshold, rows = low_stock_rows(search=search, category_id=category_id,
                                     active='' if active == 'all' else active)
    data, error = _paginate(rows, request, lambda row: {
        'product_id': row['id'], 'product': row['name'], 'category_id': row['category_id'],
        'category': row['category__name'], 'current_stock': row['stock'],
        'threshold': threshold, 'active': row['is_active'], 'reorder_recommendation': None,
    })
    if error:
        return error
    return Response({'threshold': threshold, 'date_basis': 'Current stock; no historical stock snapshots exist.', **data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_customers(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    search, error = _search(request)
    if error:
        return error
    data, error = _paginate(customer_rows(start_dt, stop_dt, search=search), request, serialize_customer)
    if error:
        return error
    return Response({'date_range': _range_payload(start, end),
                     'date_basis': 'Order cohort: linked CustomerOrder.created_at; receipt totals follow that order cohort.', **data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewReports])
def reports_vendor_purchases(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    search, error = _search(request)
    if error:
        return error
    purchase_status, error = _choice(request, 'status', PURCHASE_STATUSES)
    if error:
        return error
    vendor_id, error = _positive_id(request, 'vendor_id')
    if error:
        return error
    summary, rows = vendor_purchase_rows(start_dt, stop_dt, search=search,
                                        purchase_status=purchase_status, vendor_id=vendor_id)
    data, error = _paginate(rows, request, lambda row: {
        'purchase_id': row['id'], 'vendor_id': row['vendor_id'], 'vendor': row['vendor__name'],
        'product_id': row['product_id'], 'product': row['product__name'], 'quantity': row['quantity'],
        'unit_cost': row['unit_cost'], 'purchase_value': row['purchase_value'],
        'status': row['status'], 'purchased_at': row['purchased_at'],
    })
    if error:
        return error
    return Response({'date_range': _range_payload(start, end), 'date_basis': 'VendorPurchase.purchased_at',
                     'summary_by_vendor': list(summary), **data})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, CanViewPaymentReport])
def reports_payment_verification(request):
    parsed, _unused, error = _date_range(request)
    if error:
        return error
    start, end, start_dt, stop_dt = parsed
    search, error = _search(request)
    if error:
        return error
    attempt_status, error = _choice(request, 'status', ATTEMPT_STATUSES)
    if error:
        return error
    review_action, error = _choice(request, 'review_action', REVIEW_ACTIONS | {'unreviewed'})
    if error:
        return error
    rows = payment_verification_rows(start_dt, stop_dt, search=search,
                                     attempt_status=attempt_status, review_action=review_action)
    data, error = _paginate(rows, request, serialize_payment_attempt)
    if error:
        return error
    return Response({'date_range': _range_payload(start, end), 'date_basis': 'PaymentAttempt.submitted_at', **data})
