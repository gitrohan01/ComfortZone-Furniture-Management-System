import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from django.utils import timezone
from .models import (CustomerOrder, OrderPaymentInstructions, PaymentConfiguration,
                    PaymentAttempt, PaymentReviewEvent, PaymentReceipt, CustomerOrderItem,
                    Product, VendorPurchase, InventoryMovement, OrderCancellation,
                    OrderPaymentReconciliation, PaymentRefund,
                    _authorized_payment_status_write, _authorized_payment_attempt_review)
from .models import (
    _authorized_inventory_write, _authorized_vendor_receive_write,
    _authorized_order_cancellation_write, _authorized_refund_write,
    _authorized_reconciliation_write,
)


def _require_payment_permission(user, permission):
    if not user or not user.is_authenticated or not user.is_staff or not user.has_perm(permission):
        raise PermissionDenied('An explicitly authorized staff account is required.')


def _require_workflow_permission(user, permission):
    if not user or not user.is_authenticated or not user.is_staff or not user.has_perm(permission):
        raise PermissionDenied('An explicitly authorized staff account is required.')


@transaction.atomic
def _apply_inventory_movement(*, product_id, movement_type, direction, quantity, source_key,
                              reason, actor=None, order=None, order_item=None,
                              vendor_purchase=None, cancellation=None):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError({'quantity': 'Inventory movement quantity must be a positive integer.'})
    if not source_key or len(source_key) > 180:
        raise ValidationError({'source_key': 'A valid inventory idempotency key is required.'})
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'An inventory movement reason is required.'})

    existing = InventoryMovement.objects.filter(source_key=source_key).first()
    if existing:
        expected = (
            existing.product_id == product_id
            and existing.movement_type == movement_type
            and existing.direction == direction
            and existing.quantity == quantity
            and existing.order_id == getattr(order, 'pk', None)
            and existing.order_item_id == getattr(order_item, 'pk', None)
            and existing.vendor_purchase_id == getattr(vendor_purchase, 'pk', None)
            and existing.cancellation_id == getattr(cancellation, 'pk', None)
        )
        if not expected:
            raise ValidationError({'source_key': 'This inventory idempotency key was already used for another event.'})
        return existing

    product = Product.objects.select_for_update().get(pk=product_id)
    if direction == InventoryMovement.DIRECTION_OUT:
        if product.stock < quantity:
            raise ValidationError({'quantity': 'Insufficient stock for this inventory movement.'})
        resulting_stock = product.stock - quantity
    elif direction == InventoryMovement.DIRECTION_IN:
        resulting_stock = product.stock + quantity
    else:
        raise ValidationError({'direction': 'Invalid inventory movement direction.'})

    with _authorized_inventory_write():
        Product.objects.filter(pk=product.pk).update(stock=resulting_stock)
        return InventoryMovement.objects.create(
            product=product, movement_type=movement_type, direction=direction,
            quantity=quantity, resulting_stock=resulting_stock, order=order,
            order_item=order_item, vendor_purchase=vendor_purchase,
            cancellation=cancellation, actor=actor, reason=reason,
            source_key=source_key,
        )


def allocate_order_item_stock(order_item, actor):
    return _apply_inventory_movement(
        product_id=order_item.product_id,
        movement_type=InventoryMovement.TYPE_ORDER_ALLOCATION,
        direction=InventoryMovement.DIRECTION_OUT,
        quantity=order_item.quantity,
        source_key=f'order:{order_item.order_id}:allocation:{order_item.pk}',
        reason=f'Checkout allocation for order {order_item.order_id}.',
        actor=actor, order=order_item.order, order_item=order_item,
    )


@transaction.atomic
def adjust_product_stock(product_id, *, target_stock, actor, reason, source_key=None):
    _require_workflow_permission(actor, 'store.adjust_stock')
    if isinstance(target_stock, bool) or not isinstance(target_stock, int) or target_stock < 0:
        raise ValidationError({'stock': 'Target stock must be a non-negative integer.'})
    if not reason or not reason.strip():
        raise ValidationError({'stock_reason': 'An adjustment reason is required.'})
    source_key = (source_key or f'manual-adjustment:{uuid.uuid4()}').strip()
    existing = InventoryMovement.objects.filter(source_key=source_key).first()
    if existing:
        if (existing.product_id == product_id
                and existing.movement_type == InventoryMovement.TYPE_MANUAL_ADJUSTMENT
                and existing.resulting_stock == target_stock):
            return existing
        raise ValidationError({'stock_source_key': 'This inventory idempotency key was already used.'})

    product = Product.objects.select_for_update().get(pk=product_id)
    difference = target_stock - product.stock
    if difference == 0:
        return None
    return _apply_inventory_movement(
        product_id=product.pk,
        movement_type=InventoryMovement.TYPE_MANUAL_ADJUSTMENT,
        direction=(InventoryMovement.DIRECTION_IN if difference > 0 else InventoryMovement.DIRECTION_OUT),
        quantity=abs(difference), source_key=source_key, reason=reason.strip(), actor=actor,
    )


@transaction.atomic
def receive_vendor_purchase(purchase_id, actor):
    _require_workflow_permission(actor, 'store.receive_vendorpurchase')
    purchase = VendorPurchase.objects.select_for_update().get(pk=purchase_id)
    if purchase.status == 'Received':
        raise ValueError('This vendor purchase has already been received.')
    if purchase.status != 'Approved':
        raise ValueError('Only approved vendor purchases can be received.')
    if purchase.quantity <= 0:
        raise ValidationError({'quantity': 'Purchase quantity must be positive.'})

    _apply_inventory_movement(
        product_id=purchase.product_id,
        movement_type=InventoryMovement.TYPE_VENDOR_RECEIPT,
        direction=InventoryMovement.DIRECTION_IN,
        quantity=purchase.quantity,
        source_key=f'vendor-purchase:{purchase.pk}:receipt',
        reason=f'Receipt of vendor purchase {purchase.pk}.',
        actor=actor, vendor_purchase=purchase,
    )
    purchase.status = 'Received'
    purchase.received_by = actor
    purchase.received_at = timezone.now()
    with _authorized_vendor_receive_write():
        purchase.save(update_fields=['status', 'received_by', 'received_at'])
    return purchase


def _reconciliation_for(order):
    return order.payment_reconciliations.order_by('-reconciled_at', '-pk').first()


def _confirmed_payment_amount(order):
    if order.payment_status == 'Paid':
        receipt = PaymentReceipt.objects.select_for_update().filter(
            attempt__order=order, attempt__status=PaymentAttempt.STATUS_VERIFIED,
        ).select_related('attempt').first()
        if receipt:
            return receipt.amount, receipt.attempt, receipt
    if order.payment_status in ('Paid', None):
        reconciliation = _reconciliation_for(order)
        if reconciliation and reconciliation.outcome == OrderPaymentReconciliation.OUTCOME_PAID:
            return reconciliation.confirmed_amount, None, None
    return None, None, None


@transaction.atomic
def request_payment_refund(order_id, *, amount, reason, actor):
    _require_workflow_permission(actor, 'store.request_refund')
    order = CustomerOrder.objects.select_for_update().get(pk=order_id)
    if order.status == 'Cancelled':
        raise ValueError('A cancelled order cannot receive a new refund request.')
    payment_amount, attempt, receipt = _confirmed_payment_amount(order)
    if payment_amount is None:
        raise ValueError('A refund requires a verified receipt or confirmed-paid reconciliation.')
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A refund reason is required.'})
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({'amount': 'Enter a valid refund amount.'}) from exc
    if not amount.is_finite() or amount <= Decimal('0.00'):
        raise ValidationError({'amount': 'Refund amount must be positive.'})

    reserved = PaymentRefund.objects.filter(
        order=order, status__in=[PaymentRefund.STATUS_PENDING, PaymentRefund.STATUS_CONFIRMED],
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if reserved + amount > payment_amount:
        raise ValidationError({'amount': 'Refund requests cannot exceed the verified amount received.'})
    with _authorized_refund_write():
        return PaymentRefund.objects.create(
            order=order, attempt=attempt, receipt=receipt, amount=amount,
            reason=reason.strip(), requested_by=actor,
        )


@transaction.atomic
def review_payment_refund(refund_id, actor, *, confirm, manual_reference='', remarks=''):
    _require_workflow_permission(actor, 'store.confirm_refund')
    refund = PaymentRefund.objects.select_for_update().get(pk=refund_id)
    order = CustomerOrder.objects.select_for_update().get(pk=refund.order_id)
    if refund.status == PaymentRefund.STATUS_CONFIRMED and confirm:
        return refund
    if refund.status != PaymentRefund.STATUS_PENDING:
        raise ValueError('This refund request has already been reviewed.')
    if refund.requested_by_id == actor.pk:
        raise PermissionDenied('The requester cannot review their own refund.')
    if not remarks or not remarks.strip():
        raise ValidationError({'remarks': 'Refund review remarks are required.'})

    amount_received, _attempt, _receipt = _confirmed_payment_amount(order)
    if confirm:
        if not manual_reference or not manual_reference.strip():
            raise ValidationError({'manual_transaction_reference': 'A manual UPI transaction reference is required.'})
        if len(manual_reference.strip()) > 128:
            raise ValidationError({'manual_transaction_reference': 'Reference cannot exceed 128 characters.'})
        if PaymentRefund.objects.filter(
            manual_transaction_reference=manual_reference.strip(),
        ).exclude(pk=refund.pk).exists():
            raise ValidationError({'manual_transaction_reference': 'This refund reference is already recorded.'})
        confirmed = PaymentRefund.objects.filter(
            order=order, status=PaymentRefund.STATUS_CONFIRMED,
        ).exclude(pk=refund.pk).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if amount_received is None or confirmed + refund.amount > amount_received:
            raise ValidationError({'amount': 'Confirmed refunds cannot exceed the verified amount received.'})
        refund.status = PaymentRefund.STATUS_CONFIRMED
        refund.manual_transaction_reference = manual_reference.strip()
    else:
        refund.status = PaymentRefund.STATUS_REJECTED
        refund.manual_transaction_reference = None
    refund.confirmed_by = actor
    refund.confirmed_at = timezone.now()
    refund.reviewer_remarks = remarks.strip()
    with _authorized_refund_write():
        refund.save(update_fields=[
            'status', 'confirmed_by', 'confirmed_at', 'manual_transaction_reference',
            'reviewer_remarks', 'updated_at',
        ])
    return refund


@transaction.atomic
def reconcile_order_payment(order_id, actor, *, outcome, reason, evidence_reference,
                            confirmed_amount=None):
    _require_workflow_permission(actor, 'store.reconcile_order_payment')
    order = CustomerOrder.objects.select_for_update().get(pk=order_id)
    if order.payment_status not in (None, 'Paid'):
        raise ValueError('Only legacy or paid orders requiring reconciliation may be reconciled.')
    if order.payment_status == 'Paid' and PaymentReceipt.objects.filter(attempt__order=order).exists():
        raise ValueError('A paid order with a verified receipt does not require reconciliation.')
    previous = _reconciliation_for(order)
    if previous and previous.outcome != OrderPaymentReconciliation.OUTCOME_UNKNOWN:
        raise ValueError('A confirmed payment reconciliation already exists.')
    if outcome not in {value for value, _label in OrderPaymentReconciliation.OUTCOME_CHOICES}:
        raise ValidationError({'outcome': 'Choose Unknown, Unpaid, or Paid.'})
    with _authorized_reconciliation_write():
        return OrderPaymentReconciliation.objects.create(
            order=order, outcome=outcome, confirmed_amount=confirmed_amount,
            reason=reason, evidence_reference=evidence_reference, actor=actor,
        )


@transaction.atomic
def cancel_customer_order(order_id, actor, *, reason):
    _require_workflow_permission(actor, 'store.cancel_customerorder')
    order = CustomerOrder.objects.select_for_update().get(pk=order_id)
    if order.status == 'Cancelled':
        return OrderCancellation.objects.get(order=order)
    if order.status not in ('Pending', 'Processing'):
        raise ValueError('Shipped or delivered orders cannot be cancelled.')
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A cancellation reason is required.'})
    attempts = PaymentAttempt.objects.select_for_update().filter(order=order)
    if attempts.filter(status=PaymentAttempt.STATUS_PENDING).exists():
        raise ValueError('Resolve the pending payment attempt before cancellation.')

    reconciliation = None
    if order.payment_status in ('Paid', None):
        payment_amount, _attempt, receipt = _confirmed_payment_amount(order)
        if order.payment_status == 'Paid' and receipt is None:
            reconciliation = _reconciliation_for(order)
            if not reconciliation or reconciliation.outcome != OrderPaymentReconciliation.OUTCOME_PAID:
                raise ValueError('A paid order without a receipt requires confirmed-paid reconciliation.')
        elif order.payment_status is None:
            reconciliation = _reconciliation_for(order)
            if not reconciliation or reconciliation.outcome == OrderPaymentReconciliation.OUTCOME_UNKNOWN:
                raise ValueError('Legacy payment status must be explicitly reconciled before cancellation.')
            if reconciliation.outcome == OrderPaymentReconciliation.OUTCOME_PAID:
                payment_amount = reconciliation.confirmed_amount
            else:
                payment_amount = None
        if payment_amount is not None:
            refunded = PaymentRefund.objects.filter(
                order=order, status=PaymentRefund.STATUS_CONFIRMED,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            if refunded < payment_amount:
                raise ValueError('The full verified payment must be refunded before cancellation.')
    elif order.payment_status != 'Pending':
        raise ValueError('Order payment status is unresolved and cannot be cancelled.')

    if attempts.filter(status=PaymentAttempt.STATUS_VERIFIED).exists() and order.payment_status != 'Paid':
        raise ValueError('Verified payment history conflicts with the order payment status.')

    with _authorized_order_cancellation_write():
        cancellation = OrderCancellation.objects.create(
            order=order, actor=actor, reason=reason.strip(),
        )
        order.status = 'Cancelled'
        order.save(update_fields=['status'])

    items = list(order.items.filter(product__isnull=False).select_related('product').order_by('product_id', 'pk'))
    for item in items:
        _apply_inventory_movement(
            product_id=item.product_id,
            movement_type=InventoryMovement.TYPE_ORDER_RESTORATION,
            direction=InventoryMovement.DIRECTION_IN,
            quantity=item.quantity,
            source_key=f'cancellation:{cancellation.pk}:order-item:{item.pk}',
            reason=f'Stock restoration for cancellation of order {order.pk}.',
            actor=actor, order=order, order_item=item, cancellation=cancellation,
        )
    return cancellation


@transaction.atomic
def activate_payment_configuration(configuration, actor):
    """Activate a prepared immutable version while preserving the one-active invariant."""
    _require_payment_permission(actor, 'store.manage_payment_configuration')
    if not configuration.pk:
        raise ValidationError('Save a configuration version before activating it.')

    # Lock in primary-key order so concurrent activations serialize on MySQL.
    configurations = list(PaymentConfiguration.objects.select_for_update().order_by('pk'))
    current = next((row for row in configurations if row.pk == configuration.pk), None)
    if current is None:
        raise ValidationError('Payment configuration does not exist.')
    if not current.display_name.strip() or not current.upi_id.strip() or not current.qr_image.name:
        raise ValidationError('Display name, UPI ID, and QR image are required before activation.')

    PaymentConfiguration.objects.exclude(pk=current.pk).filter(active_slot=1).update(active_slot=None)
    current.active_slot = 1
    current.save(update_fields=['active_slot'])
    return current


@transaction.atomic
def create_order_payment_instructions(order):
    """Return the immutable existing order instructions or snapshot the active version."""
    locked_order = CustomerOrder.objects.select_for_update().get(pk=order.pk)
    if (locked_order.customer_id is None or locked_order.payment_status != 'Pending'
            or locked_order.status == 'Cancelled' or locked_order.total_amount <= 0):
        raise ValidationError('This order is not eligible for payment instructions.')
    existing = OrderPaymentInstructions.objects.filter(order=locked_order).first()
    if existing:
        return existing

    configuration = PaymentConfiguration.objects.select_for_update().filter(active_slot=1).first()
    if configuration is None:
        raise ValidationError('The showroom has not configured UPI payment instructions.')

    snapshot = {
        'order': locked_order,
        'configuration': configuration,
        'configuration_version': configuration.version,
        'display_name': configuration.display_name,
        'upi_id': configuration.upi_id,
        'qr_image_name': configuration.qr_image.name,
        'expected_amount': locked_order.total_amount,
    }
    try:
        with transaction.atomic():
            return OrderPaymentInstructions.objects.create(**snapshot)
    except IntegrityError:
        # The one-to-one order constraint arbitrates any concurrent creation.
        return OrderPaymentInstructions.objects.get(order=locked_order)


@transaction.atomic
def review_payment_attempt(attempt_id, actor, *, approve, remarks='', bank_checked=False):
    _require_payment_permission(actor, 'store.verify_payment')
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    order = CustomerOrder.objects.select_for_update().get(pk=attempt.order_id)
    if attempt.status != PaymentAttempt.STATUS_PENDING:
        raise ValueError('This payment attempt has already been reviewed.')
    if approve:
        if not bank_checked:
            raise ValidationError({'bank_checked': 'Confirm that the actual bank or UPI records were checked.'})
        if order.status == 'Cancelled' or order.payment_status == 'Paid':
            raise ValueError('The order is no longer eligible for approval.')
        if PaymentAttempt.objects.filter(
            normalized_transaction_reference=attempt.normalized_transaction_reference,
            status=PaymentAttempt.STATUS_VERIFIED,
        ).exclude(pk=attempt.pk).exists():
            raise ValueError('This transaction reference has already been verified.')
        attempt.status = PaymentAttempt.STATUS_VERIFIED
        with _authorized_payment_attempt_review():
            attempt.save(update_fields=['status', 'pending_order_key', 'verified_transaction_reference'])
        order.payment_status = 'Paid'
        with _authorized_payment_status_write():
            order.save(update_fields=['payment_status'])
        action = PaymentReviewEvent.ACTION_VERIFIED
    else:
        if not remarks.strip():
            raise ValidationError({'remarks': 'Rejection remarks are required.'})
        attempt.status = PaymentAttempt.STATUS_REJECTED
        with _authorized_payment_attempt_review():
            attempt.save(update_fields=['status', 'pending_order_key', 'verified_transaction_reference'])
        action = PaymentReviewEvent.ACTION_REJECTED
    event = PaymentReviewEvent.objects.create(
        attempt=attempt, reviewer=actor,
        reviewer_name=(actor.get_full_name() or actor.get_username()),
        action=action, remarks=remarks.strip(),
    )
    if approve:
        if PaymentReceipt.objects.filter(attempt=attempt).exists():
            raise ValueError('A receipt already exists for this payment attempt.')
        PaymentReceipt.objects.create(
            attempt=attempt,
            amount=attempt.expected_amount,
            order_reference_snapshot=order.order_reference or '',
            customer_name_snapshot=order.customer_name,
            customer_email_snapshot=order.customer_email,
            showroom_name_snapshot=attempt.instructions.display_name,
            upi_id_snapshot=attempt.instructions.upi_id,
            transaction_reference_snapshot=attempt.transaction_reference,
            reviewer_name_snapshot=event.reviewer_name,
            verified_at=event.reviewed_at,
        )
    return attempt
