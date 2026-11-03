"""Database-backed report queries. Date ranges are inclusive in showroom local time."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncDate
from django.db.models.functions import Coalesce

from .models import (
    CustomerOrder, PaymentAttempt, PaymentReceipt, PaymentReviewEvent, Product,
    PaymentRefund, VendorPurchase,
)

# Avoid depending on a project's configurable user model in the order queries;
# account identity is selected separately through settings.AUTH_USER_MODEL below.
from django.contrib.auth import get_user_model

ZERO = Decimal('0.00')
MONEY_FIELD = DecimalField(max_digits=16, decimal_places=2)
PURCHASE_VALUE = ExpressionWrapper(F('quantity') * F('unit_cost'), output_field=MONEY_FIELD)


def date_range_datetimes(start_date, end_date):
    """Builds the half-open timestamp range for an inclusive local-date range."""
    from django.utils import timezone
    from datetime import datetime, time
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    stop = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start, stop


def _orders_in_range(start, stop):
    return CustomerOrder.objects.filter(created_at__gte=start, created_at__lt=stop)


def _amount(queryset, field):
    return queryset.aggregate(total=Sum(field))['total'] or ZERO


def sales_summary(start, stop):
    orders = _orders_in_range(start, stop)
    active_orders = orders.exclude(status='Cancelled')
    cancelled_orders = orders.filter(status='Cancelled')
    pending_orders = active_orders.filter(payment_status='Pending')
    receipts = PaymentReceipt.objects.filter(verified_at__gte=start, verified_at__lt=stop)
    refunds = PaymentRefund.objects.filter(
        status=PaymentRefund.STATUS_CONFIRMED, confirmed_at__gte=start, confirmed_at__lt=stop,
    )
    rejected_reviews = PaymentReviewEvent.objects.filter(
        action=PaymentReviewEvent.ACTION_REJECTED,
        reviewed_at__gte=start, reviewed_at__lt=stop,
    )
    receipt_order_ids = PaymentReceipt.objects.values('attempt__order_id')
    paid_without_receipt = orders.filter(payment_status='Paid').exclude(pk__in=receipt_order_ids)
    gross_verified = _amount(receipts, 'amount')
    confirmed_refunds = _amount(refunds, 'amount')
    return {
        'order_count': active_orders.count(),
        'order_value': _amount(active_orders, 'total_amount'),
        'cancelled_order_count': cancelled_orders.count(),
        'cancelled_order_value': _amount(cancelled_orders, 'total_amount'),
        'verified_revenue': gross_verified,
        'confirmed_refunds': confirmed_refunds,
        'net_verified_revenue': gross_verified - confirmed_refunds,
        'pending_payment_value': _amount(pending_orders, 'total_amount'),
        'paid_orders_without_receipts_count': paid_without_receipt.count(),
        'paid_orders_without_receipts_value': _amount(paid_without_receipt, 'total_amount'),
        'rejected_payment_attempt_count': rejected_reviews.count(),
        'date_basis': {
            'order_count_and_values': 'CustomerOrder.created_at',
            'pending_payment_value': 'CustomerOrder.created_at; current payment status',
            'verified_revenue': 'PaymentReceipt.verified_at',
            'confirmed_refunds': 'PaymentRefund.confirmed_at',
            'net_verified_revenue': 'Gross receipts by verification date minus confirmed refunds by confirmation date.',
            'paid_without_receipt': 'CustomerOrder.created_at; current payment status',
            'rejected_payment_attempt_count': 'PaymentReviewEvent.reviewed_at',
        },
    }


def sales_daily(start, stop):
    orders = _orders_in_range(start, stop)
    order_days = orders.annotate(day=TruncDate('created_at')).values('day').annotate(
        order_count=Count('pk', filter=~Q(status='Cancelled')),
        order_value=Sum('total_amount', filter=~Q(status='Cancelled')),
        cancelled_order_count=Count('pk', filter=Q(status='Cancelled')),
        cancelled_order_value=Sum('total_amount', filter=Q(status='Cancelled')),
        pending_payment_value=Sum('total_amount', filter=Q(payment_status='Pending') & ~Q(status='Cancelled')),
    )
    receipt_days = PaymentReceipt.objects.filter(verified_at__gte=start, verified_at__lt=stop).annotate(
        day=TruncDate('verified_at')).values('day').annotate(verified_revenue=Sum('amount'))
    rejected_days = PaymentReviewEvent.objects.filter(
        action=PaymentReviewEvent.ACTION_REJECTED, reviewed_at__gte=start, reviewed_at__lt=stop,
    ).annotate(day=TruncDate('reviewed_at')).values('day').annotate(rejected_attempt_count=Count('pk'))
    refund_days = PaymentRefund.objects.filter(
        status=PaymentRefund.STATUS_CONFIRMED, confirmed_at__gte=start, confirmed_at__lt=stop,
    ).annotate(day=TruncDate('confirmed_at')).values('day').annotate(confirmed_refunds=Sum('amount'))
    rows = defaultdict(lambda: {
        'date': None, 'order_count': 0, 'order_value': ZERO, 'cancelled_order_count': 0,
        'cancelled_order_value': ZERO, 'pending_payment_value': ZERO,
        'verified_revenue': ZERO, 'confirmed_refunds': ZERO,
        'net_verified_revenue': ZERO, 'rejected_attempt_count': 0,
    })
    for source in (order_days, receipt_days, refund_days, rejected_days):
        for item in source:
            row = rows[item['day']]
            row['date'] = item['day']
            for key, value in item.items():
                if key not in ('day', 'date'):
                    row[key] = value if value is not None else ZERO
    for row in rows.values():
        row['net_verified_revenue'] = row['verified_revenue'] - row['confirmed_refunds']
    return [rows[day] for day in sorted(rows)]


def order_rows(start, stop, *, search='', payment_status='', fulfillment_status=''):
    queryset = _orders_in_range(start, stop).select_related('customer').prefetch_related('items')
    if fulfillment_status:
        queryset = queryset.filter(status=fulfillment_status)
    if payment_status == 'unrecorded':
        queryset = queryset.filter(payment_status__isnull=True)
    elif payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    if search:
        queryset = queryset.filter(
            Q(order_reference__icontains=search) | Q(customer_name__icontains=search) |
            Q(items__product_name__icontains=search)
        ).distinct()
    return queryset.order_by('-created_at', '-pk')


def serialize_order(order):
    items = list(order.items.all())
    return {
        'id': order.pk,
        'order_reference': order.order_reference or '',
        'customer_name': order.customer_name,
        'linked_account': order.customer_id is not None,
        'created_at': order.created_at,
        'items': [{'product_name': item.product_name, 'quantity': item.quantity,
                   'unit_price': item.unit_price, 'line_subtotal': item.line_subtotal} for item in items],
        'item_summary': ', '.join(f'{item.product_name} × {item.quantity}' for item in items),
        'total_amount': order.total_amount,
        'payment_status': order.payment_status,
        'fulfillment_status': order.status,
    }


def inventory_rows(*, search='', category_id=None, active=''):
    queryset = Product.objects.select_related('category').all()
    if category_id is not None:
        queryset = queryset.filter(category_id=category_id)
    if active == 'true':
        queryset = queryset.filter(is_active=True)
    elif active == 'false':
        queryset = queryset.filter(is_active=False)
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(category__name__icontains=search))
    return queryset.order_by('name', 'pk').values(
        'id', 'name', 'category_id', 'category__name', 'stock', 'price', 'is_active',
    )


def low_stock_rows(*, search='', category_id=None, active='true'):
    threshold = settings.STORE_LOW_STOCK_THRESHOLD
    queryset = Product.objects.select_related('category').filter(stock__lte=threshold)
    if category_id is not None:
        queryset = queryset.filter(category_id=category_id)
    if active == 'true':
        queryset = queryset.filter(is_active=True)
    elif active == 'false':
        queryset = queryset.filter(is_active=False)
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(category__name__icontains=search))
    return threshold, queryset.order_by('stock', 'name', 'pk').values(
        'id', 'name', 'category_id', 'category__name', 'stock', 'is_active',
    )


def customer_rows(start, stop, *, search=''):
    orders = _orders_in_range(start, stop).filter(customer_id=OuterRef('pk'))
    order_count = orders.order_by().values('customer_id').annotate(value=Count('pk')).values('value')[:1]
    pending_value = orders.order_by().values('customer_id').annotate(value=Sum(
        'total_amount', filter=Q(payment_status='Pending') & ~Q(status='Cancelled'),
    )).values('value')[:1]
    last_order = orders.order_by().values('customer_id').annotate(value=Max('created_at')).values('value')[:1]
    verified = PaymentReceipt.objects.filter(
        attempt__order__customer_id=OuterRef('pk'),
        attempt__order__created_at__gte=start,
        attempt__order__created_at__lt=stop,
    ).order_by().values('attempt__order__customer_id').annotate(value=Sum('amount')).values('value')[:1]
    customer_ids = _orders_in_range(start, stop).filter(customer_id__isnull=False).order_by().values('customer_id').distinct()
    user_model = get_user_model()
    users = user_model.objects.filter(pk__in=Subquery(customer_ids)).annotate(
        report_order_count=Coalesce(Subquery(order_count), 0),
        report_pending_value=Coalesce(Subquery(pending_value), ZERO, output_field=MONEY_FIELD),
        report_last_order=Subquery(last_order),
        report_verified_total=Coalesce(Subquery(verified), ZERO, output_field=MONEY_FIELD),
    ).order_by('pk')
    if search:
        users = users.filter(Q(username__icontains=search) | Q(email__icontains=search) |
                             Q(first_name__icontains=search) | Q(last_name__icontains=search))
    return users


def serialize_customer(user):
    return {
        'customer_id': user.pk,
        'username': user.get_username(),
        'customer_name': (user.get_full_name().strip() or user.get_username()),
        'email': user.email,
        'order_count': user.report_order_count,
        'verified_payment_total': user.report_verified_total,
        'pending_order_value': user.report_pending_value,
        'last_order_date': user.report_last_order,
    }


def vendor_purchase_rows(start, stop, *, search='', purchase_status='', vendor_id=None):
    queryset = VendorPurchase.objects.filter(purchased_at__gte=start, purchased_at__lt=stop)
    if purchase_status:
        queryset = queryset.filter(status=purchase_status)
    if vendor_id is not None:
        queryset = queryset.filter(vendor_id=vendor_id)
    if search:
        queryset = queryset.filter(Q(vendor__name__icontains=search) | Q(product__name__icontains=search))
    queryset = queryset.select_related('vendor', 'product').annotate(purchase_value=PURCHASE_VALUE)
    summary = queryset.values('vendor_id', 'vendor__name').annotate(
        purchase_count=Count('pk'), total_quantity=Sum('quantity'), purchase_value=Sum(PURCHASE_VALUE),
    ).order_by('vendor__name', 'vendor_id')
    rows = queryset.order_by('-purchased_at', '-pk').values(
        'id', 'vendor_id', 'vendor__name', 'product_id', 'product__name', 'quantity',
        'unit_cost', 'purchase_value', 'status', 'purchased_at',
    )
    return summary, rows


def payment_verification_rows(start, stop, *, search='', attempt_status='', review_action=''):
    queryset = PaymentAttempt.objects.filter(submitted_at__gte=start, submitted_at__lt=stop).select_related(
        'order', 'customer', 'review_event', 'review_event__reviewer',
    )
    if attempt_status:
        queryset = queryset.filter(status=attempt_status)
    if review_action == 'unreviewed':
        queryset = queryset.filter(review_event__isnull=True)
    elif review_action:
        queryset = queryset.filter(review_event__action=review_action)
    if search:
        queryset = queryset.filter(
            Q(order__order_reference__icontains=search) |
            Q(transaction_reference__icontains=search) |
            Q(customer__username__icontains=search) |
            Q(order__customer_name__icontains=search)
        )
    return queryset.order_by('-submitted_at', '-pk')


def serialize_payment_attempt(attempt):
    event = getattr(attempt, 'review_event', None)
    return {
            'attempt_id': attempt.pk,
            'order_reference': attempt.order.order_reference or '',
            'customer_id': attempt.customer_id,
            'customer_name': attempt.order.customer_name,
            'linked_account': attempt.customer_id is not None,
            'transaction_reference': attempt.transaction_reference,
            'expected_amount': attempt.expected_amount,
            'status': attempt.status,
            'submitted_at': attempt.submitted_at,
            'reviewer': event.reviewer_name if event else None,
            'review_action': event.action if event else None,
            'reviewed_at': event.reviewed_at if event else None,
            'rejection_remarks': event.remarks if event and event.action == PaymentReviewEvent.ACTION_REJECTED else '',
    }
