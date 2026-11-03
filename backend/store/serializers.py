from decimal import Decimal
import uuid

from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.models import User
from .models import Vendor, Category, Product, CustomerOrder, CustomerOrderItem, VendorPurchase, ContactMessage, Feedback

def create_order_with_unique_reference(*, order_reference=None, **order_data):
    # The unique DB constraint remains authoritative; a savepoint makes a rare
    # UUID collision retry safe inside an outer transaction.
    for attempt in range(3):
        try:
            with transaction.atomic():
                reference = order_reference or str(uuid.uuid4())
                return CustomerOrder.objects.create(order_reference=reference, **order_data)
        except IntegrityError:
            if order_reference is not None or attempt == 2:
                raise

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = ['id','username','first_name','last_name','email','password','is_active','is_staff','date_joined']
        read_only_fields = ['id','date_joined','is_staff','is_active']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'A password is required when creating a user.'})
        return attrs

    def validate_password(self, value):
        django_validate_password(value, self.instance)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=['password'])
        return instance
class VendorSerializer(serializers.ModelSerializer):
    class Meta: model=Vendor; fields='__all__'; read_only_fields=['id','created_at']
class CategorySerializer(serializers.ModelSerializer):
    class Meta: model=Category; fields='__all__'
class PublicCategorySerializer(serializers.ModelSerializer):
    class Meta: model=Category; fields=['id', 'name', 'description']
class ProductSerializer(serializers.ModelSerializer):
    category_name=serializers.CharField(source='category.name',read_only=True)
    vendor_name=serializers.CharField(source='vendor.name',read_only=True,default='')
    price=serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'))
    stock_reason=serializers.CharField(write_only=True, required=False, allow_blank=False, max_length=255)
    stock_source_key=serializers.CharField(write_only=True, required=False, allow_blank=False, max_length=180)
    class Meta: model=Product; fields=['id','name','category','category_name','vendor','vendor_name','description','price','stock','stock_reason','stock_source_key','image_url','image','is_active','created_at']; read_only_fields=['id','created_at']
    def validate(self, attrs):
        if 'stock' in attrs:
            user = self.context['request'].user
            if not (user.is_staff and user.has_perm('store.adjust_stock')):
                raise PermissionDenied('Stock changes require inventory adjustment permission.')
            changes_stock = self.instance is None or attrs['stock'] != self.instance.stock
            if changes_stock and (self.instance is not None or attrs['stock'] > 0) and not attrs.get('stock_reason'):
                raise serializers.ValidationError({'stock_reason': 'Provide a reason for the stock adjustment.'})
        elif 'stock_reason' in attrs or 'stock_source_key' in attrs:
            raise serializers.ValidationError({'stock': 'Stock adjustment metadata requires a stock value.'})
        return attrs

    @staticmethod
    def _inventory_error(exc):
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        raise serializers.ValidationError(detail) from exc

    @transaction.atomic
    def create(self, validated_data):
        target_stock = validated_data.pop('stock', 0)
        reason = validated_data.pop('stock_reason', '')
        source_key = validated_data.pop('stock_source_key', None)
        product = Product.objects.create(stock=0, **validated_data)
        if target_stock:
            from .services import adjust_product_stock
            try:
                adjust_product_stock(
                    product.pk, target_stock=target_stock,
                    actor=self.context['request'].user, reason=reason,
                    source_key=source_key,
                )
            except DjangoValidationError as exc:
                self._inventory_error(exc)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        target_stock = validated_data.pop('stock', None)
        reason = validated_data.pop('stock_reason', '')
        source_key = validated_data.pop('stock_source_key', None)
        product = super().update(instance, validated_data)
        if target_stock is not None:
            from .services import adjust_product_stock
            try:
                adjust_product_stock(
                    product.pk, target_stock=target_stock,
                    actor=self.context['request'].user, reason=reason,
                    source_key=source_key,
                )
            except DjangoValidationError as exc:
                self._inventory_error(exc)
            product.refresh_from_db()
        return product
class PublicProductSerializer(serializers.ModelSerializer):
    category_name=serializers.CharField(source='category.name',read_only=True)
    class Meta:
        model=Product
        fields=['id','name','category_name','description','price','stock','image_url','image']
        read_only_fields=fields
class CustomerOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model=CustomerOrderItem
        fields=['id','product','product_name','unit_price','quantity','line_subtotal']
        read_only_fields=fields
class CustomerOrderSerializer(serializers.ModelSerializer):
    items=CustomerOrderItemSerializer(many=True,read_only=True)
    class Meta:
        model=CustomerOrder
        fields='__all__'
        read_only_fields=['id','created_at','customer','order_reference','customer_name',
                          'customer_email','shipping_address','total_amount','payment_status']

    def create(self, validated_data):
        # Administrative order creation remains compatible, but cannot skip the
        # initial fulfillment state or forge a payment state.
        validated_data.pop('status', None)
        validated_data['status']='Pending'
        validated_data['payment_status']='Pending'
        return create_order_with_unique_reference(**validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        current=CustomerOrder.objects.select_for_update().get(pk=instance.pk)
        requested=validated_data.get('status', current.status)
        if requested == 'Cancelled':
            raise serializers.ValidationError({'status': 'Order cancellation is disabled.'})
        transitions={
            'Pending': {'Pending', 'Processing'},
            'Processing': {'Processing', 'Shipped'},
            'Shipped': {'Shipped', 'Delivered'},
            'Delivered': {'Delivered'},
        }
        if requested not in transitions.get(current.status, {current.status}):
            raise serializers.ValidationError({'status': f'Cannot move an order from {current.status} to {requested}.'})
        return super().update(current, validated_data)
class CheckoutItemSerializer(serializers.Serializer):
    product_id=serializers.IntegerField(min_value=1)
    quantity=serializers.IntegerField(min_value=1)

class CustomerOrderCreateSerializer(serializers.ModelSerializer):
    items=CheckoutItemSerializer(many=True,write_only=True)

    class Meta:
        model=CustomerOrder
        fields=['customer_name','customer_email','shipping_address','items']

    def validate_shipping_address(self, value):
        if not value.strip():
            raise serializers.ValidationError('A delivery address is required.')
        return value.strip()

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('Add at least one item before checkout.')
        product_ids=[item['product_id'] for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError('Each product can appear only once in the cart.')
        products={product.id: product for product in Product.objects.filter(id__in=product_ids, is_active=True)}
        missing=set(product_ids)-products.keys()
        if missing:
            raise serializers.ValidationError('One or more products are unavailable.')
        for item in items:
            product=products[item['product_id']]
            if item['quantity'] > product.stock:
                raise serializers.ValidationError(f'Only {product.stock} of {product.name} are currently available.')
        return items

    @transaction.atomic
    def create(self, validated_data):
        order_reference = validated_data.pop('order_reference', None)
        item_data=validated_data.pop('items')
        products={product.id: product for product in Product.objects.select_for_update().filter(
            id__in=[item['product_id'] for item in item_data]
        ).order_by('id')}
        prepared=[]
        total=Decimal('0.00')
        for item in item_data:
            product=products.get(item['product_id'])
            quantity=item['quantity']
            if not product or not product.is_active or quantity > product.stock:
                raise serializers.ValidationError({'items': 'Availability changed. Review your cart and try again.'})
            subtotal=(product.price * quantity).quantize(Decimal('0.01'))
            prepared.append((product, quantity, subtotal))
            total += subtotal

        user=self.context['request'].user
        if total > Decimal('99999999.99'):
            raise serializers.ValidationError({'items': 'The order total exceeds the supported amount.'})
        order_data={
            'customer': user,
            'customer_name': validated_data['customer_name'],
            'customer_email': validated_data.get('customer_email') or user.email,
            'shipping_address': validated_data['shipping_address'],
            'total_amount': total,
            'status': 'Pending',
            'payment_status': 'Pending',
        }
        order=create_order_with_unique_reference(
            order_reference=order_reference, **order_data,
        )
        for product, quantity, subtotal in prepared:
            order_item = CustomerOrderItem.objects.create(
                order=order, product=product, product_name=product.name,
                unit_price=product.price, quantity=quantity, line_subtotal=subtotal,
            )
            from .services import allocate_order_item_stock
            allocate_order_item_stock(order_item, user)
        return order

class CustomerOrderReadSerializer(serializers.ModelSerializer):
    items=CustomerOrderItemSerializer(many=True,read_only=True)
    class Meta:
        model=CustomerOrder
        fields=['id','order_reference','customer_name','customer_email','shipping_address','total_amount','status','payment_status','created_at','items']
        read_only_fields=fields
class VendorPurchaseSerializer(serializers.ModelSerializer):
    vendor_name=serializers.CharField(source='vendor.name',read_only=True)
    product_name=serializers.CharField(source='product.name',read_only=True)
    received_by=serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta: model=VendorPurchase; fields=['id','vendor','vendor_name','product','product_name','quantity','unit_cost','status','purchased_at','received_by','received_at']; read_only_fields=['id','purchased_at','received_by','received_at']
    def validate_status(self, value):
        if value == 'Received':
            raise serializers.ValidationError('Use the authorized purchase receiving action.')
        return value

    def validate(self, attrs):
        if self.instance and self.instance.status == 'Received':
            historical = {'vendor', 'product', 'quantity', 'unit_cost', 'status'}
            if historical.intersection(attrs):
                raise serializers.ValidationError(
                    'Received purchase quantities and status are immutable.'
                )
        return attrs


class CancellationRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, allow_blank=False)


class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(max_length=2000, allow_blank=False)


class RefundReviewSerializer(serializers.Serializer):
    manual_transaction_reference = serializers.CharField(max_length=128, required=False, allow_blank=False)
    remarks = serializers.CharField(max_length=2000, allow_blank=False)


class PaymentReconciliationSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=('Unknown', 'Unpaid', 'Paid'))
    confirmed_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01'), required=False,
    )
    reason = serializers.CharField(max_length=2000, allow_blank=False)
    evidence_reference = serializers.CharField(max_length=255, allow_blank=False)
class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta: model=ContactMessage; fields='__all__'; read_only_fields=['id','created_at']
class FeedbackSerializer(serializers.ModelSerializer):
    class Meta: model=Feedback; fields='__all__'; read_only_fields=['id','created_at']
