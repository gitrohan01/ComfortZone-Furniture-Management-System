import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from django.db import models
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.contrib.auth.models import User
from .storage import (
    PrivatePaymentStorage, ValidatedPrivateImageField, payment_proof_upload_to,
    payment_qr_upload_to, product_image_upload_to, validate_payment_image,
    validate_product_image,
)

private_payment_storage = PrivatePaymentStorage()

_payment_status_write = ContextVar('store_payment_status_write', default=False)
_payment_attempt_review = ContextVar('store_payment_attempt_review', default=False)
_inventory_write = ContextVar('store_inventory_write', default=False)
_vendor_receive_write = ContextVar('store_vendor_receive_write', default=False)
_order_cancellation_write = ContextVar('store_order_cancellation_write', default=False)
_refund_write = ContextVar('store_refund_write', default=False)
_reconciliation_write = ContextVar('store_reconciliation_write', default=False)


@contextmanager
def _authorized_payment_status_write():
    """Permit the verified-payment service's single order payment transition."""
    token = _payment_status_write.set(True)
    try:
        yield
    finally:
        _payment_status_write.reset(token)


@contextmanager
def _authorized_payment_attempt_review():
    token = _payment_attempt_review.set(True)
    try:
        yield
    finally:
        _payment_attempt_review.reset(token)


@contextmanager
def _authorized_inventory_write():
    token = _inventory_write.set(True)
    try:
        yield
    finally:
        _inventory_write.reset(token)


@contextmanager
def _authorized_vendor_receive_write():
    token = _vendor_receive_write.set(True)
    try:
        yield
    finally:
        _vendor_receive_write.reset(token)


@contextmanager
def _authorized_order_cancellation_write():
    token = _order_cancellation_write.set(True)
    try:
        yield
    finally:
        _order_cancellation_write.reset(token)


@contextmanager
def _authorized_refund_write():
    token = _refund_write.set(True)
    try:
        yield
    finally:
        _refund_write.reset(token)


@contextmanager
def _authorized_reconciliation_write():
    token = _reconciliation_write.set(True)
    try:
        yield
    finally:
        _reconciliation_write.reset(token)


class ProductQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if 'stock' in kwargs and not _inventory_write.get():
            raise ValidationError('Product stock can only be changed through the inventory service.')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if 'stock' in fields and not _inventory_write.get():
            raise ValidationError('Product stock can only be changed through the inventory service.')
        return super().bulk_update(objs, fields, batch_size=batch_size)


class CustomerOrderQuerySet(models.QuerySet):
    IMMUTABLE_FIELDS = {
        'total_amount', 'payment_status', 'order_reference', 'customer',
        'customer_name', 'customer_email', 'shipping_address',
    }

    def update(self, **kwargs):
        changed = {key.removesuffix('_id') for key in kwargs}
        if changed & self.IMMUTABLE_FIELDS:
            raise ValidationError('Order financial and identity snapshots cannot be bulk-updated.')
        if 'status' in kwargs:
            raise ValidationError('Order fulfillment status cannot be bulk-updated.')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        changed = {field.removesuffix('_id') for field in fields}
        if changed & self.IMMUTABLE_FIELDS:
            raise ValidationError('Order financial and identity snapshots cannot be bulk-updated.')
        if 'status' in changed:
            raise ValidationError('Order fulfillment status cannot be bulk-updated.')
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        if any(obj.status == 'Cancelled' for obj in objs):
            raise ValidationError('Orders cannot be created in the Cancelled state.')
        return super().bulk_create(objs, **kwargs)

    def delete(self):
        raise ProtectedError('Customer orders are retained as historical records.', [])


class CustomerOrderItemQuerySet(models.QuerySet):
    IMMUTABLE_FIELDS = {'order', 'product', 'product_name', 'unit_price', 'quantity', 'line_subtotal'}

    def update(self, **kwargs):
        changed = {key.removesuffix('_id') for key in kwargs}
        if changed & self.IMMUTABLE_FIELDS:
            raise ValidationError('Order item snapshots cannot be bulk-updated.')
        return super().update(**kwargs)

    def delete(self):
        raise ProtectedError('Historical order items are retained.', [])

    def bulk_update(self, objs, fields, batch_size=None):
        changed = {field.removesuffix('_id') for field in fields}
        if changed & self.IMMUTABLE_FIELDS:
            raise ValidationError('Order item snapshots cannot be bulk-updated.')
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Vendor(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=25, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    def __str__(self): return self.name

class Product(models.Model):
    name = models.CharField(max_length=160)
    demo_key = models.CharField(max_length=100, blank=True, null=True, unique=True, editable=False)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True)
    image = models.ImageField(
        upload_to=product_image_upload_to, blank=True, validators=[validate_product_image],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ProductQuerySet.as_manager()
    class Meta:
        permissions = [('adjust_stock', 'Can adjust product stock')]

    def save(self, *args, **kwargs):
        if self.pk and not _inventory_write.get():
            previous = type(self).objects.get(pk=self.pk)
            update_fields = kwargs.get('update_fields')
            stock_written = update_fields is None or 'stock' in update_fields
            if stock_written and previous.stock != self.stock:
                raise ValidationError('Product stock can only be changed through the inventory service.')
        super().save(*args, **kwargs)

    def __str__(self): return self.name


class StoreReportPermission(Product):
    """Proxy model used to define a dedicated store-wide reporting permission."""
    class Meta:
        proxy = True
        default_permissions = ()
        permissions = [
            ('view_reports', 'Can view showroom business reports'),
            ('view_dashboard', 'Can view showroom dashboard'),
        ]


class StoreAccountPermission(User):
    """Proxy used to define store-specific account administration permission."""
    class Meta:
        proxy = True
        app_label = 'store'
        default_permissions = ()
        permissions = [('manage_staff_accounts', 'Can manage staff accounts and privileges')]

class CustomerOrder(models.Model):
    STATUS = [('Pending','Pending'),('Processing','Processing'),('Shipped','Shipped'),('Delivered','Delivered'),('Cancelled','Cancelled')]
    PAYMENT_STATUS = [('Pending', 'Pending'), ('Paid', 'Paid')]
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='store_orders')
    order_reference = models.CharField(max_length=36, unique=True, null=True, blank=True, default=uuid.uuid4)
    customer_name = models.CharField(max_length=120)
    customer_email = models.EmailField(blank=True)
    shipping_address = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default='Pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='Pending', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = CustomerOrderQuerySet.as_manager()
    IMMUTABLE_FIELDS = ('total_amount', 'order_reference', 'customer_id', 'customer_name',
                        'customer_email', 'shipping_address')

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            update_fields = kwargs.get('update_fields')
            for field in self.IMMUTABLE_FIELDS:
                field_name = field.removesuffix('_id')
                if update_fields is not None and field_name not in update_fields and field not in update_fields:
                    continue
                if getattr(previous, field) != getattr(self, field):
                    raise ValidationError(f'{field_name} is an immutable order snapshot.')
            payment_written = update_fields is None or 'payment_status' in update_fields
            if (payment_written and previous.payment_status != self.payment_status
                    and not _payment_status_write.get()):
                raise ValidationError('Payment status can only be changed by payment verification.')
            status_written = update_fields is None or 'status' in update_fields
            if (status_written and previous.status != self.status and self.status == 'Cancelled'):
                if not _order_cancellation_write.get():
                    raise ValidationError('Order cancellation requires the authorized cancellation service.')
        elif self.status == 'Cancelled':
            raise ValidationError('Orders cannot be created in the Cancelled state.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Customer orders are retained as historical records.', [self])

    class Meta:
        permissions = [('change_order_fulfillment', 'Can change order fulfillment status')]
    def __str__(self): return f'Order #{self.pk} - {self.customer_name}'


class PaymentConfiguration(models.Model):
    """Immutable version of showroom UPI instructions; activation is mutable."""
    version = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    display_name = models.CharField(max_length=160)
    upi_id = models.CharField(max_length=255)
    qr_image = ValidatedPrivateImageField(
        upload_to=payment_qr_upload_to, storage=private_payment_storage,
        validators=[validate_payment_image], max_length=100,
    )
    # A nullable unique slot gives portable "at most one active" enforcement:
    # SQLite and MySQL both permit multiple NULL values in a unique index.
    active_slot = models.PositiveSmallIntegerField(null=True, blank=True, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_payment_configurations')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_active(self):
        return self.active_slot == 1

    def activate(self, actor):
        from .services import activate_payment_configuration
        return activate_payment_configuration(self, actor)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ('version', 'display_name', 'upi_id', 'qr_image', 'created_by', 'created_at')
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Payment configuration versions are immutable; create a new version.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Payment configuration versions and QR images are retained.', [self])

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('manage_payment_configuration', 'Can manage payment configuration'),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.version})'


class OrderPaymentInstructions(models.Model):
    """Immutable payment terms shown for one order, including configuration snapshot."""
    order = models.OneToOneField(CustomerOrder, on_delete=models.PROTECT, related_name='payment_instructions')
    configuration = models.ForeignKey(PaymentConfiguration, on_delete=models.PROTECT, related_name='order_instructions')
    configuration_version = models.UUIDField()
    display_name = models.CharField(max_length=160)
    upi_id = models.CharField(max_length=255)
    qr_image_name = models.CharField(max_length=512)
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Order payment instructions are immutable.')
        if self.expected_amount <= Decimal('0.00'):
            raise ValidationError({'expected_amount': 'Payment instructions require a positive order total.'})
        if (self.order.customer_id is None or self.order.payment_status != 'Pending'
                or self.order.status == 'Cancelled' or self.expected_amount != self.order.total_amount):
            raise ValidationError('Instructions must snapshot a payable customer order at its exact total.')
        if (self.configuration_version != self.configuration.version
                or self.display_name != self.configuration.display_name
                or self.upi_id != self.configuration.upi_id
                or self.qr_image_name != self.configuration.qr_image.name):
            raise ValidationError('Instruction values must match the selected immutable configuration version.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Order payment instructions are retained.', [self])

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(expected_amount__gt=0), name='payment_instruction_amount_positive'),
        ]


class PaymentAttemptQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Payment attempts can only be changed through payment review.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Payment attempts can only be changed through payment review.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Payment attempts must be validated and saved individually.')

    def delete(self):
        raise ProtectedError('Payment attempts are retained for audit.', [])


class PaymentAttempt(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_VERIFIED = 'Verified'
    STATUS_REJECTED = 'Rejected'
    STATUS_CHOICES = [(STATUS_PENDING, 'Pending'), (STATUS_VERIFIED, 'Verified'), (STATUS_REJECTED, 'Rejected')]

    order = models.ForeignKey(CustomerOrder, on_delete=models.PROTECT, related_name='payment_attempts')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_attempts')
    instructions = models.ForeignKey(OrderPaymentInstructions, on_delete=models.PROTECT, related_name='attempts')
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_reference = models.CharField(max_length=128)
    normalized_transaction_reference = models.CharField(max_length=128, editable=False, unique=True)
    verified_transaction_reference = models.CharField(max_length=128, null=True, blank=True, unique=True, editable=False)
    pending_order_key = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)
    proof_image = ValidatedPrivateImageField(
        upload_to=payment_proof_upload_to, storage=private_payment_storage,
        validators=[validate_payment_image], max_length=100,
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    objects = PaymentAttemptQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.status != self.STATUS_PENDING:
                raise ValidationError({'status': 'New payment attempts must start Pending.'})
            if self.instructions.order_id != self.order_id or self.customer_id != self.order.customer_id:
                raise ValidationError('The attempt customer and order must match its instruction snapshot.')
            if self.expected_amount != self.instructions.expected_amount:
                raise ValidationError({'expected_amount': 'Attempt amount must equal the immutable instruction amount.'})
            if self.order.payment_status != 'Pending' or self.order.status == 'Cancelled':
                raise ValidationError('This order is not eligible for payment submission.')
            if not self.transaction_reference.strip():
                raise ValidationError({'transaction_reference': 'A transaction reference is required.'})
        else:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ('order_id', 'customer_id', 'instructions_id', 'expected_amount',
                         'transaction_reference', 'proof_image', 'submitted_at')
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Payment submissions are immutable; submit a new attempt instead.')
            if self.status not in (previous.status, self.STATUS_VERIFIED, self.STATUS_REJECTED) or (
                previous.status != self.STATUS_PENDING and self.status != previous.status
            ):
                raise ValidationError('A reviewed payment attempt cannot be changed or reopened.')
            if previous.status != self.status and not _payment_attempt_review.get():
                raise ValidationError('Payment attempt status can only change through payment review.')

        self.normalized_transaction_reference = self.transaction_reference.strip().upper()
        self.pending_order_key = self.order_id if self.status == self.STATUS_PENDING else None
        self.verified_transaction_reference = (
            self.normalized_transaction_reference if self.status == self.STATUS_VERIFIED else None
        )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Payment attempts are retained for audit.', [self])

    class Meta:
        ordering = ['-submitted_at', '-pk']
        indexes = [models.Index(fields=['status', 'submitted_at'], name='pay_attempt_status_date_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(expected_amount__gt=0), name='payment_attempt_amount_positive'),
        ]
        permissions = [
            ('verify_payment', 'Can review UPI payment attempts'),
        ]

    def __str__(self):
        return f'Payment attempt #{self.pk} for order #{self.order_id} ({self.status})'


class PaymentReviewEvent(models.Model):
    ACTION_VERIFIED = 'Verified'
    ACTION_REJECTED = 'Rejected'
    ACTION_CHOICES = [(ACTION_VERIFIED, 'Verified'), (ACTION_REJECTED, 'Rejected')]

    attempt = models.OneToOneField(PaymentAttempt, on_delete=models.PROTECT, related_name='review_event')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_reviews')
    reviewer_name = models.CharField(max_length=255)
    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
    remarks = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Payment review events are append-only.')
        if self.attempt.status != self.action:
            raise ValidationError('Review action must match the final payment attempt status.')
        if self.action == self.ACTION_VERIFIED and self.attempt.order.payment_status != 'Paid':
            raise ValidationError('Order payment status must be Paid in the same approval transaction.')
        if self.action == self.ACTION_REJECTED and self.attempt.order.payment_status == 'Paid':
            raise ValidationError('A paid order cannot receive a rejected payment review.')
        if self.reviewer_id == self.attempt.customer_id:
            raise ValidationError('A customer cannot review their own payment.')
        if (not self.reviewer.is_staff or not self.reviewer.has_perm('store.verify_payment')):
            raise ValidationError('Reviewer must have the store.verify_payment permission.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Payment review events are append-only.', [self])

    class Meta:
        ordering = ['-reviewed_at', '-pk']


class PaymentReviewEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Payment review events are append-only.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Payment review events are append-only.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Payment review events must be saved individually.')

    def delete(self):
        raise ProtectedError('Payment review events are append-only.', [])


PaymentReviewEvent.add_to_class('objects', PaymentReviewEventQuerySet.as_manager())


class PaymentReceiptQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Payment receipt snapshots are immutable.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Payment receipt snapshots are immutable.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Payment receipts must be validated individually.')

    def delete(self):
        raise ProtectedError('Payment receipts are retained for audit.', [])


class PaymentReceipt(models.Model):
    attempt = models.OneToOneField(PaymentAttempt, on_delete=models.PROTECT, related_name='receipt')
    receipt_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    order_reference_snapshot = models.CharField(max_length=36, blank=True)
    customer_name_snapshot = models.CharField(max_length=120)
    customer_email_snapshot = models.EmailField(blank=True)
    showroom_name_snapshot = models.CharField(max_length=160)
    upi_id_snapshot = models.CharField(max_length=255)
    transaction_reference_snapshot = models.CharField(max_length=128)
    reviewer_name_snapshot = models.CharField(max_length=255)
    verified_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Payment receipt snapshots are immutable.')
        if self.attempt.status != PaymentAttempt.STATUS_VERIFIED:
            raise ValidationError('A receipt can only be created for a verified attempt.')
        if self.attempt.order.payment_status != 'Paid':
            raise ValidationError('A receipt requires the order payment status to be Paid.')
        if self.amount != self.attempt.expected_amount:
            raise ValidationError('Receipt amount must equal the verified expected amount.')
        try:
            review = self.attempt.review_event
        except PaymentReviewEvent.DoesNotExist:
            raise ValidationError('A receipt requires a verified review event.')
        expected_values = {
            'order_reference_snapshot': self.attempt.order.order_reference or '',
            'customer_name_snapshot': self.attempt.order.customer_name,
            'customer_email_snapshot': self.attempt.order.customer_email,
            'showroom_name_snapshot': self.attempt.instructions.display_name,
            'upi_id_snapshot': self.attempt.instructions.upi_id,
            'transaction_reference_snapshot': self.attempt.transaction_reference,
            'reviewer_name_snapshot': review.reviewer_name,
            'verified_at': review.reviewed_at,
        }
        if any(getattr(self, field) != value for field, value in expected_values.items()):
            raise ValidationError('Receipt values must be snapshots of the verified attempt and review.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Payment receipts are retained for audit.', [self])

    objects = PaymentReceiptQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-pk']

class CustomerOrderItem(models.Model):
    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    product_name = models.CharField(max_length=160)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    objects = CustomerOrderItemQuerySet.as_manager()
    IMMUTABLE_FIELDS = ('order_id', 'product_id', 'product_name', 'unit_price', 'quantity', 'line_subtotal')

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            update_fields = kwargs.get('update_fields')
            for field in self.IMMUTABLE_FIELDS:
                field_name = field.removesuffix('_id')
                if update_fields is not None and field_name not in update_fields and field not in update_fields:
                    continue
                if getattr(previous, field) != getattr(self, field):
                    raise ValidationError('Historical order item snapshots are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Historical order items are retained.', [self])

    def __str__(self): return f'{self.product_name} × {self.quantity} (Order #{self.order_id})'


class VendorPurchaseQuerySet(models.QuerySet):
    HISTORICAL_FIELDS = {'vendor', 'vendor_id', 'product', 'product_id', 'quantity', 'unit_cost'}
    RECEIVING_FIELDS = {'received_by', 'received_by_id', 'received_at'}

    def update(self, **kwargs):
        fields = set(kwargs)
        if fields & (self.HISTORICAL_FIELDS | self.RECEIVING_FIELDS) or 'status' in fields:
            raise ValidationError('Vendor purchase history can only be changed through its workflow.')
        return super().update(**kwargs)

    def delete(self):
        raise ProtectedError('Vendor purchase history is retained.', [])

    def bulk_update(self, objs, fields, batch_size=None):
        if set(fields) & (self.HISTORICAL_FIELDS | {'status', 'received_by', 'received_at'}):
            raise ValidationError('Vendor purchase history can only be changed through its workflow.')
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        if any(obj.status == 'Received' or obj.received_by_id or obj.received_at for obj in objs):
            raise ValidationError('Purchases must be received through the inventory receiving service.')
        return super().bulk_create(objs, **kwargs)


class VendorPurchase(models.Model):
    STATUS = [('Requested','Requested'),('Approved','Approved'),('Received','Received'),('Rejected','Rejected')]
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='purchases')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='purchases')
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default='Requested')
    purchased_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='received_vendor_purchases')
    received_at = models.DateTimeField(null=True, blank=True)
    objects = VendorPurchaseQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Purchase quantity must be positive.'})
        if not self.pk:
            if self.status == 'Received' or self.received_by_id or self.received_at:
                raise ValidationError('Purchases must be received through the inventory receiving service.')
        else:
            previous = type(self).objects.get(pk=self.pk)
            if previous.status == 'Received':
                immutable = ('vendor_id', 'product_id', 'quantity', 'unit_cost', 'purchased_at',
                             'received_by_id', 'received_at', 'status')
                if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                    raise ValidationError('Received purchase records are immutable.')
            if previous.status != self.status and self.status == 'Received' and not _vendor_receive_write.get():
                raise ValidationError('Purchases can only be received through the inventory receiving service.')
            if not _vendor_receive_write.get() and (
                previous.received_by_id != self.received_by_id
                or previous.received_at != self.received_at
            ):
                raise ValidationError('Receiving actor and timestamp are service-controlled.')
            if self.status == 'Received' and (
                not _vendor_receive_write.get() or not self.received_by_id or not self.received_at
            ):
                raise ValidationError('Receiving actor and timestamp are required.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Vendor purchase history is retained.', [self])

    class Meta:
        permissions = [('receive_vendorpurchase', 'Can receive vendor purchases')]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='vendor_purchase_quantity_positive'),
        ]
    def __str__(self): return f'Purchase #{self.pk}'


class OrderCancellation(models.Model):
    order = models.OneToOneField(CustomerOrder, on_delete=models.PROTECT, related_name='cancellation')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='order_cancellations')
    reason = models.TextField()
    cancelled_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk or not _order_cancellation_write.get():
            raise ValidationError('Cancellation events can only be created by the cancellation service.')
        if not self.actor.is_staff or not self.actor.has_perm('store.cancel_customerorder'):
            raise ValidationError('Cancellation actor lacks the required permission.')
        if not self.reason.strip():
            raise ValidationError({'reason': 'A cancellation reason is required.'})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Cancellation audit events are retained.', [self])

    class Meta:
        permissions = [('cancel_customerorder', 'Can cancel eligible customer orders')]


class OrderCancellationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Cancellation audit events are immutable.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Cancellation audit events are immutable.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Cancellation events must be created by the cancellation service.')

    def delete(self):
        raise ProtectedError('Cancellation audit events are retained.', [])


OrderCancellation.add_to_class('objects', OrderCancellationQuerySet.as_manager())


class OrderPaymentReconciliationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Payment reconciliation history is immutable.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Payment reconciliation history is immutable.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Payment reconciliation records must use the authorized service.')

    def delete(self):
        raise ProtectedError('Payment reconciliation history is retained.', [])


class OrderPaymentReconciliation(models.Model):
    OUTCOME_UNKNOWN = 'Unknown'
    OUTCOME_UNPAID = 'Unpaid'
    OUTCOME_PAID = 'Paid'
    OUTCOME_CHOICES = [
        (OUTCOME_UNKNOWN, 'Unknown'),
        (OUTCOME_UNPAID, 'Confirmed unpaid'),
        (OUTCOME_PAID, 'Confirmed paid'),
    ]

    order = models.ForeignKey(CustomerOrder, on_delete=models.PROTECT, related_name='payment_reconciliations')
    outcome = models.CharField(max_length=12, choices=OUTCOME_CHOICES)
    confirmed_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reason = models.TextField()
    evidence_reference = models.CharField(max_length=255)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='order_payment_reconciliations')
    reconciled_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk or not _reconciliation_write.get():
            raise ValidationError('Payment reconciliation records are append-only and service-controlled.')
        if not self.actor.is_staff or not self.actor.has_perm('store.reconcile_order_payment'):
            raise ValidationError('Reconciliation actor lacks the required permission.')
        if self.order.payment_status not in (None, 'Paid'):
            raise ValidationError('Only legacy or paid orders requiring reconciliation may be reconciled.')
        if not self.reason.strip() or not self.evidence_reference.strip():
            raise ValidationError({'evidence_reference': 'A reason and evidence reference are required.'})
        if self.outcome == self.OUTCOME_PAID:
            if self.confirmed_amount is None or self.confirmed_amount <= Decimal('0.00'):
                raise ValidationError({'confirmed_amount': 'A positive confirmed paid amount is required.'})
            if self.confirmed_amount > self.order.total_amount:
                raise ValidationError({'confirmed_amount': 'Confirmed payment cannot exceed the order total.'})
        elif self.outcome in (self.OUTCOME_UNKNOWN, self.OUTCOME_UNPAID):
            if self.confirmed_amount is not None:
                raise ValidationError({'confirmed_amount': 'Only a confirmed-paid outcome may include an amount.'})
        else:
            raise ValidationError({'outcome': 'Choose Unknown, Unpaid, or Paid.'})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Payment reconciliation history is retained.', [self])

    class Meta:
        ordering = ['-reconciled_at', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(outcome='Paid', confirmed_amount__gt=0) |
                           (models.Q(outcome__in=['Unknown', 'Unpaid']) & models.Q(confirmed_amount__isnull=True))),
                name='payment_reconciliation_amount_matches_outcome',
            ),
        ]
        permissions = [('reconcile_order_payment', 'Can reconcile legacy order payment status')]

    objects = OrderPaymentReconciliationQuerySet.as_manager()


class PaymentRefundQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Refund records can only be changed through the refund service.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Refund records can only be changed through the refund service.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Refund requests must use the authorized refund service.')

    def delete(self):
        raise ProtectedError('Refund audit records are retained.', [])


class PaymentRefund(models.Model):
    STATUS_PENDING = 'Pending'
    STATUS_CONFIRMED = 'Confirmed'
    STATUS_REJECTED = 'Rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    order = models.ForeignKey(CustomerOrder, on_delete=models.PROTECT, related_name='refunds')
    attempt = models.ForeignKey(PaymentAttempt, null=True, blank=True,
        on_delete=models.PROTECT, related_name='refunds')
    receipt = models.ForeignKey(PaymentReceipt, null=True, blank=True,
        on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='requested_payment_refunds')
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='confirmed_payment_refunds')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    manual_transaction_reference = models.CharField(max_length=128, null=True, blank=True, unique=True)
    reviewer_remarks = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not _refund_write.get():
            raise ValidationError('Refund records can only be changed through the refund service.')
        if not self.pk:
            if self.status != self.STATUS_PENDING or self.confirmed_by_id or self.confirmed_at:
                raise ValidationError('New refunds must start Pending.')
            if not self.requested_by.is_staff or not self.requested_by.has_perm('store.request_refund'):
                raise ValidationError('Refund requester lacks the required permission.')
            if self.amount <= Decimal('0.00') or not self.reason.strip():
                raise ValidationError({'amount': 'A positive amount and refund reason are required.'})
            if self.order_id != (self.attempt.order_id if self.attempt_id else self.order_id):
                raise ValidationError('Refund attempt must belong to the requested order.')
            if self.receipt_id and (
                self.receipt.attempt_id != self.attempt_id or self.receipt.attempt.order_id != self.order_id
            ):
                raise ValidationError('Refund receipt and attempt must belong to the requested order.')
        else:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ('order_id', 'attempt_id', 'receipt_id', 'amount', 'reason',
                         'requested_by_id', 'requested_at')
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Refund request snapshots are immutable.')
            if previous.status != self.status and (
                previous.status != self.STATUS_PENDING or self.status not in (self.STATUS_CONFIRMED, self.STATUS_REJECTED)
            ):
                raise ValidationError('A reviewed refund cannot be changed or reopened.')
            if previous.status != self.status:
                if not self.confirmed_by_id or not self.confirmed_by.is_staff:
                    raise ValidationError('A staff reviewer is required to resolve the refund.')
                if self.confirmed_by_id == self.requested_by_id:
                    raise ValidationError('The requester cannot review their own refund.')
                if not self.confirmed_by.has_perm('store.confirm_refund'):
                    raise ValidationError('Refund reviewer lacks the required permission.')
                if not self.confirmed_at or not self.reviewer_remarks.strip():
                    raise ValidationError({'reviewer_remarks': 'Review timestamp and remarks are required.'})
                if self.status == self.STATUS_CONFIRMED and not self.manual_transaction_reference:
                    raise ValidationError({'manual_transaction_reference': 'A manual UPI reference is required.'})
            elif any(getattr(previous, field) != getattr(self, field) for field in (
                'confirmed_by_id', 'confirmed_at', 'manual_transaction_reference', 'reviewer_remarks',
            )):
                raise ValidationError('Refund review details are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Refund audit records are retained.', [self])

    class Meta:
        ordering = ['-requested_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_refund_amount_positive'),
        ]
        permissions = [
            ('request_refund', 'Can request a manual payment refund'),
            ('confirm_refund', 'Can confirm or reject a manual payment refund'),
        ]

    objects = PaymentRefundQuerySet.as_manager()


class InventoryMovementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Inventory movement records are immutable.')

    def delete(self):
        raise ProtectedError('Inventory movement records are retained.', [])

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError('Inventory movement records are immutable.')

    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Inventory movements must be created by the inventory service.')


class InventoryMovement(models.Model):
    TYPE_ORDER_ALLOCATION = 'OrderAllocation'
    TYPE_ORDER_RESTORATION = 'OrderRestoration'
    TYPE_VENDOR_RECEIPT = 'VendorReceipt'
    TYPE_MANUAL_ADJUSTMENT = 'ManualAdjustment'
    TYPE_CHOICES = [
        (TYPE_ORDER_ALLOCATION, 'Order allocation'),
        (TYPE_ORDER_RESTORATION, 'Order restoration'),
        (TYPE_VENDOR_RECEIPT, 'Vendor receipt'),
        (TYPE_MANUAL_ADJUSTMENT, 'Manual adjustment'),
    ]
    DIRECTION_IN = 'IN'
    DIRECTION_OUT = 'OUT'
    DIRECTION_CHOICES = [(DIRECTION_IN, 'Stock in'), (DIRECTION_OUT, 'Stock out')]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='inventory_movements')
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    quantity = models.PositiveIntegerField()
    resulting_stock = models.PositiveIntegerField()
    order = models.ForeignKey(CustomerOrder, null=True, blank=True,
        on_delete=models.PROTECT, related_name='inventory_movements')
    order_item = models.ForeignKey(CustomerOrderItem, null=True, blank=True,
        on_delete=models.PROTECT, related_name='inventory_movements')
    vendor_purchase = models.ForeignKey(VendorPurchase, null=True, blank=True,
        on_delete=models.PROTECT, related_name='inventory_movements')
    cancellation = models.ForeignKey(OrderCancellation, null=True, blank=True,
        on_delete=models.PROTECT, related_name='inventory_movements')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='inventory_movements')
    reason = models.CharField(max_length=255)
    source_key = models.CharField(max_length=180, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = InventoryMovementQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.pk or not _inventory_write.get():
            raise ValidationError('Inventory movements can only be created by the inventory service.')
        if self.quantity <= 0 or self.resulting_stock < 0:
            raise ValidationError({'quantity': 'Movement quantity must be positive.'})
        if not self.reason.strip() or not self.source_key.strip():
            raise ValidationError({'reason': 'Movement reason and source key are required.'})
        expected = {
            self.TYPE_ORDER_ALLOCATION: (self.DIRECTION_OUT, self.order_id is not None and
                                         self.order_item_id is not None and self.vendor_purchase_id is None),
            self.TYPE_ORDER_RESTORATION: (self.DIRECTION_IN, self.cancellation_id is not None and
                                          self.order_id is not None and self.order_item_id is not None),
            self.TYPE_VENDOR_RECEIPT: (self.DIRECTION_IN, self.vendor_purchase_id is not None and
                                       self.order_id is None and self.order_item_id is None),
            self.TYPE_MANUAL_ADJUSTMENT: (self.direction, self.order_id is None and
                                          self.order_item_id is None and self.vendor_purchase_id is None and
                                          self.cancellation_id is None),
        }
        config = expected.get(self.movement_type)
        if not config or config[0] != self.direction or not config[1]:
            raise ValidationError('Inventory movement type, direction, and source do not agree.')
        if self.order_item_id and (
            self.order_item.order_id != self.order_id or self.order_item.product_id != self.product_id
        ):
            raise ValidationError('Inventory movement order item does not match its order and product.')
        if self.vendor_purchase_id and self.vendor_purchase.product_id != self.product_id:
            raise ValidationError('Inventory movement product does not match its vendor purchase.')
        if self.cancellation_id and self.cancellation.order_id != self.order_id:
            raise ValidationError('Inventory restoration must match its cancellation event.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('Inventory movement records are retained.', [self])

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='inventory_movement_quantity_positive'),
            models.CheckConstraint(condition=models.Q(direction__in=['IN', 'OUT']), name='inventory_movement_direction_valid'),
            models.CheckConstraint(
                condition=(
                    models.Q(movement_type='OrderAllocation', direction='OUT') |
                    models.Q(movement_type='OrderRestoration', direction='IN') |
                    models.Q(movement_type='VendorReceipt', direction='IN') |
                    models.Q(movement_type='ManualAdjustment')
                ),
                name='inventory_movement_type_direction_valid',
            ),
            models.UniqueConstraint(
                fields=['order_item', 'movement_type'],
                name='inventory_movement_unique_order_item_type',
            ),
            models.UniqueConstraint(
                fields=['vendor_purchase', 'movement_type'],
                name='inventory_movement_unique_purchase_type',
            ),
        ]

class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=180, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.subject or self.name

class Feedback(models.Model):
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    comments = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'Feedback {self.pk} ({self.rating}/5)'
