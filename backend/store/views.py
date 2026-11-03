import logging
import re
from io import BytesIO
from datetime import datetime, time

from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Q
from django.utils import timezone
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from .models import (Vendor, Category, Product, CustomerOrder, OrderPaymentInstructions,
    PaymentAttempt, PaymentReceipt, PaymentConfiguration, PaymentReviewEvent, VendorPurchase,
    ContactMessage, Feedback, PaymentRefund, OrderPaymentReconciliation,
    InventoryMovement)
from .serializers import (UserSerializer, VendorSerializer, CategorySerializer,
    PublicCategorySerializer, ProductSerializer, PublicProductSerializer,
    CustomerOrderSerializer, CustomerOrderReadSerializer, CustomerOrderCreateSerializer,
    VendorPurchaseSerializer, ContactMessageSerializer, FeedbackSerializer,
    CancellationRequestSerializer, RefundRequestSerializer, RefundReviewSerializer,
    PaymentReconciliationSerializer)
from .permissions import StoreModelPermissions, StoreDashboardPermission

logger = logging.getLogger(__name__)



class CustomerTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        return super().get_token(user)

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": "admin" if self.user.is_staff else "user",
        }
        return data

class CustomerTokenView(TokenObtainPairView):
    serializer_class = CustomerTokenSerializer


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user_permissions(request):
    user = request.user
    return Response({
        'user_id': user.pk,
        'username': user.get_username(),
        'is_staff': user.is_staff,
        'permissions': sorted(user.get_all_permissions()),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def register_customer(request):
    username = str(request.data.get("username", "")).strip()
    email = str(request.data.get("email", "")).strip()
    password = request.data.get("password", "")
    confirm_password = request.data.get("confirm_password", "")
    errors = {}
    if not username:
        errors["username"] = ["Username is required."]
    elif User.objects.filter(username=username).exists():
        errors["username"] = ["This username is already taken."]
    if not email:
        errors["email"] = ["Email is required."]
    elif User.objects.filter(email__iexact=email).exists():
        errors["email"] = ["This email is already registered."]
    if len(password) < 8:
        errors["password"] = ["Password must contain at least 8 characters."]
    if password != confirm_password:
        errors["confirm_password"] = ["Passwords do not match."]
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(username=username, email=email, password=password, is_staff=False, is_superuser=False)
    return Response({"message": "Account created successfully. Please log in."}, status=status.HTTP_201_CREATED)

class AdminModelViewSet(viewsets.ModelViewSet):
    permission_classes=[StoreModelPermissions]


def _private_image_response(storage, name, *, inline, public_filename):
    extension = str(name).rsplit('.', 1)[-1].lower() if '.' in str(name) else ''
    content_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(extension)
    if not content_type:
        return Response({'detail': 'Private image is unavailable.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        image_file = storage.open(name, 'rb')
    except (OSError, ValueError, SuspiciousFileOperation) as exc:
        logger.error('Private payment image unavailable (%s).', type(exc).__name__)
        return Response({'detail': 'Private image is temporarily unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    response = FileResponse(image_file, content_type=content_type, as_attachment=not inline, filename=public_filename)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    response['X-Frame-Options'] = 'DENY'
    return response


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def customer_payment_qr(request, order_id):
    order = get_object_or_404(CustomerOrder, pk=order_id, customer=request.user)
    try:
        instructions = order.payment_instructions
    except OrderPaymentInstructions.DoesNotExist:
        return Response({'detail': 'Payment instructions are unavailable.'}, status=status.HTTP_404_NOT_FOUND)
    from .storage import private_payment_storage
    return _private_image_response(private_payment_storage, instructions.qr_image_name,
                                   inline=True, public_filename='showroom-payment-qr.png')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_attempt_proof(request, attempt_id):
    attempt = get_object_or_404(PaymentAttempt.objects.select_related('order', 'customer'), pk=attempt_id)
    reviewer = request.user.is_staff and request.user.has_perm('store.verify_payment')
    if attempt.customer_id != request.user.pk and not reviewer:
        return Response({'detail': 'You do not have access to this payment image.'}, status=status.HTTP_403_FORBIDDEN)
    return _private_image_response(attempt.proof_image.storage, attempt.proof_image.name,
                                   inline=False, public_filename='payment-proof.png')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_configuration_qr(request, configuration_id):
    if not request.user.is_staff or not request.user.has_perm('store.manage_payment_configuration'):
        return Response({'detail': 'You do not have access to payment configuration files.'}, status=status.HTTP_403_FORBIDDEN)
    configuration = get_object_or_404(PaymentConfiguration, pk=configuration_id)
    return _private_image_response(configuration.qr_image.storage, configuration.qr_image.name,
                                   inline=False, public_filename='showroom-payment-qr.png')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def customer_order_payment_receipt(request, order_id):
    if request.user.is_staff:
        if not request.user.has_perm('store.verify_payment'):
            return Response({'detail': 'Payment review permission required.'}, status=status.HTTP_403_FORBIDDEN)
        order = get_object_or_404(CustomerOrder, pk=order_id)
    else:
        order = get_object_or_404(CustomerOrder, pk=order_id, customer=request.user)
    if order.payment_status != 'Paid':
        return Response({'detail': 'Verified payment receipt is unavailable.'}, status=status.HTTP_404_NOT_FOUND)
    from .models import PaymentReceipt
    receipt = PaymentReceipt.objects.select_related('attempt').filter(
        attempt__order=order, attempt__status=PaymentAttempt.STATUS_VERIFIED,
    ).first()
    if receipt is None:
        return Response({'detail': 'Verified payment receipt is unavailable.'}, status=status.HTTP_404_NOT_FOUND)
    from .receipts import receipt_filename, render_payment_receipt
    try:
        pdf = render_payment_receipt(receipt)
    except Exception as exc:
        logger.error('Payment receipt rendering failed (%s).', type(exc).__name__)
        return Response({'detail': 'Receipt is temporarily unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    response = FileResponse(
        BytesIO(pdf), content_type='application/pdf',
        as_attachment=True, filename=receipt_filename(receipt),
    )
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _payment_staff(request, permission):
    return bool(request.user.is_authenticated and request.user.is_staff and request.user.has_perm(permission))


def _instructions_data(instructions):
    return {'amount': str(instructions.expected_amount), 'order_reference': instructions.order.order_reference,
            'upi_id': instructions.upi_id, 'showroom_name': instructions.display_name,
            'qr_url': f'/api/orders/{instructions.order_id}/payment-qr/'}


def _attempt_data(attempt, *, staff=False):
    data = {'id': attempt.pk, 'transaction_reference': attempt.transaction_reference,
            'expected_amount': str(attempt.expected_amount), 'submitted_at': attempt.submitted_at,
            'status': attempt.status, 'review_remarks': '', 'reviewed_at': None}
    event = getattr(attempt, 'review_event', None)
    if event:
        data.update(review_remarks=event.remarks, reviewed_at=event.reviewed_at)
    if staff:
        data.update(order={'id': attempt.order_id, 'reference': attempt.order.order_reference,
                           'payment_status': attempt.order.payment_status,
                           'fulfillment_status': attempt.order.status,
                           'items': [{
                               'id': item.pk, 'product_name': item.product_name,
                               'quantity': item.quantity, 'line_subtotal': str(item.line_subtotal),
                           } for item in attempt.order.items.all()]},
                    customer={'id': attempt.customer_id, 'name': attempt.order.customer_name,
                              'email': attempt.order.customer_email},
                    proof_url=f'/api/payment-attempts/{attempt.pk}/proof/',
                    review_history=([{'action': event.action, 'reviewer': event.reviewer_name,
                                     'remarks': event.remarks, 'reviewed_at': event.reviewed_at}] if event else []))
        try:
            receipt = attempt.receipt
        except PaymentReceipt.DoesNotExist:
            receipt = None
        data['receipt'] = ({
            'receipt_number': str(receipt.receipt_number),
            'amount': str(receipt.amount),
            'verified_at': receipt.verified_at,
            'transaction_reference': receipt.transaction_reference_snapshot,
            'showroom_name': receipt.showroom_name_snapshot,
            'upi_id': receipt.upi_id_snapshot,
            'reviewer_name': receipt.reviewer_name_snapshot,
        } if receipt else None)
    return data


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def customer_payment_instructions(request, order_id):
    order = get_object_or_404(CustomerOrder, pk=order_id, customer=request.user)
    from .services import create_order_payment_instructions
    try:
        instructions = create_order_payment_instructions(order)
    except DjangoValidationError as exc:
        return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_instructions_data(instructions))


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def customer_payment_attempt_create(request, order_id):
    order = get_object_or_404(CustomerOrder, pk=order_id, customer=request.user)
    if request.method == 'GET':
        attempts = order.payment_attempts.select_related('review_event').order_by('submitted_at', 'pk')
        return Response([_attempt_data(attempt) for attempt in attempts])
    if request.user.is_staff:
        return Response({'detail': 'Customer account required.'}, status=403)
    try:
        instructions = order.payment_instructions
    except OrderPaymentInstructions.DoesNotExist:
        return Response({'detail': 'Request payment instructions before submitting proof.'}, status=400)
    reference = str(request.data.get('transaction_reference', '')).strip()
    if not reference or len(reference) > 128 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ./_-]*', reference):
        return Response({'transaction_reference': ['Enter a valid transaction reference.']}, status=400)
    proof = request.FILES.get('proof_image')
    if not proof:
        return Response({'proof_image': ['A proof image is required.']}, status=400)
    normalized = reference.upper()
    if PaymentAttempt.objects.filter(normalized_transaction_reference=normalized).exists():
        return Response({'transaction_reference': ['This transaction reference has already been submitted.']}, status=400)
    if PaymentAttempt.objects.filter(order=order, status=PaymentAttempt.STATUS_PENDING).exists():
        return Response({'detail': 'This order already has a pending payment attempt.'}, status=409)
    if order.status == 'Cancelled' or order.payment_status != 'Pending':
        return Response({'detail': 'This order is not eligible for payment submission.'}, status=409)
    def persist(saved_name):
        return PaymentAttempt.objects.create(order=order, customer=request.user, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference=reference, proof_image=saved_name)
    from .storage import persist_payment_image
    try:
        attempt = persist_payment_image(proof, 'proof', persist, actor=request.user, owner_order=order)
    except (DjangoValidationError, IntegrityError) as exc:
        if isinstance(exc, DjangoValidationError):
            return Response({'proof_image': exc.messages}, status=400)
        return Response({'detail': 'A payment submission conflicts with an existing record.'}, status=409)
    return Response(_attempt_data(attempt), status=201)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def customer_payment_attempts(request, order_id):
    order = get_object_or_404(CustomerOrder, pk=order_id, customer=request.user)
    attempts = order.payment_attempts.select_related('review_event').order_by('submitted_at', 'pk')
    return Response([_attempt_data(attempt) for attempt in attempts])


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def staff_payment_attempts(request, attempt_id=None):
    if not _payment_staff(request, 'store.verify_payment'):
        return Response({'detail': 'Payment review permission required.'}, status=403)
    attempts = PaymentAttempt.objects.select_related(
        'order', 'customer', 'review_event', 'receipt',
    ).prefetch_related('order__items').all()
    if attempt_id is not None:
        attempt = get_object_or_404(attempts, pk=attempt_id)
        return Response(_attempt_data(attempt, staff=True))
    if request.query_params.get('status'):
        attempts = attempts.filter(status=request.query_params['status'])
    if request.query_params.get('order_reference'):
        attempts = attempts.filter(order__order_reference__iexact=request.query_params['order_reference'])
    for key, op in [('date_from', 'gte'), ('date_to', 'lte')]:
        raw = request.query_params.get(key)
        if raw:
            try:
                day = datetime.strptime(raw, '%Y-%m-%d').date()
                bound = timezone.make_aware(datetime.combine(day, time.min if key == 'date_from' else time.max))
            except ValueError:
                return Response({key: ['Use YYYY-MM-DD.']}, status=400)
            attempts = attempts.filter(**{f'submitted_at__{op}': bound})
    return Response([_attempt_data(attempt, staff=True) for attempt in attempts.order_by('-submitted_at', '-pk')])


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def staff_payment_decision(request, attempt_id, decision):
    if not _payment_staff(request, 'store.verify_payment'):
        return Response({'detail': 'Payment review permission required.'}, status=403)
    from .services import review_payment_attempt
    approve = decision == 'approve'
    try:
        attempt = review_payment_attempt(attempt_id, request.user, approve=approve,
            remarks=str(request.data.get('remarks', '')),
            bank_checked=request.data.get('bank_checked') is True or request.data.get('bank_checked') == 'true')
    except PaymentAttempt.DoesNotExist:
        return Response({'detail': 'Payment attempt not found.'}, status=404)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    except DjangoValidationError as exc:
        return Response({'detail': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages}, status=400)
    except IntegrityError as exc:
        logger.error('Atomic payment approval rolled back (%s).', type(exc).__name__)
        return Response({'detail': 'Approval could not be completed. No payment state was changed.'}, status=500)
    return Response(_attempt_data(attempt, staff=True))


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def payment_configurations(request):
    if not _payment_staff(request, 'store.manage_payment_configuration'):
        return Response({'detail': 'Payment configuration permission required.'}, status=403)
    if request.method == 'GET':
        return Response([{'id': c.pk, 'version': str(c.version), 'display_name': c.display_name,
                          'upi_id': c.upi_id, 'is_active': c.is_active, 'created_at': c.created_at,
                          'qr_url': f'/api/payment-configurations/{c.pk}/qr/'}
                         for c in PaymentConfiguration.objects.all()])
    display = str(request.data.get('display_name', '')).strip()
    upi = str(request.data.get('upi_id', '')).strip()
    image = request.FILES.get('qr_image')
    if not display or len(display) > 160 or not re.fullmatch(r'[A-Za-z0-9._-]{2,128}@[A-Za-z0-9.-]{2,120}', upi) or not image:
        return Response({'detail': 'Provide a display name, valid UPI ID, and QR image.'}, status=400)
    from .storage import persist_payment_image
    def persist(saved_name):
        return PaymentConfiguration.objects.create(display_name=display, upi_id=upi, qr_image=saved_name, created_by=request.user)
    try:
        config = persist_payment_image(image, 'qr', persist, actor=request.user)
    except DjangoValidationError as exc:
        return Response({'qr_image': exc.messages}, status=400)
    return Response({'id': config.pk, 'version': str(config.version), 'display_name': config.display_name,
                     'upi_id': config.upi_id, 'is_active': config.is_active,
                     'qr_url': f'/api/payment-configurations/{config.pk}/qr/'}, status=201)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def payment_configuration_action(request, configuration_id, action):
    if not _payment_staff(request, 'store.manage_payment_configuration'):
        return Response({'detail': 'Payment configuration permission required.'}, status=403)
    if action not in ('activate', 'deactivate'):
        return Response({'detail': 'Unknown configuration action.'}, status=404)
    config = get_object_or_404(PaymentConfiguration, pk=configuration_id)
    if action == 'activate':
        from .services import activate_payment_configuration
        try:
            config = activate_payment_configuration(config, request.user)
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=400)
    else:
        with transaction.atomic():
            list(PaymentConfiguration.objects.select_for_update().order_by('pk'))
            PaymentConfiguration.objects.filter(pk=config.pk, active_slot=1).update(active_slot=None)
        config.refresh_from_db()
    return Response({'id': config.pk, 'version': str(config.version), 'is_active': config.is_active})
class UserViewSet(AdminModelViewSet):
    queryset=User.objects.all().order_by('-date_joined'); serializer_class=UserSerializer
class VendorViewSet(AdminModelViewSet):
    queryset=Vendor.objects.all().order_by('-created_at'); serializer_class=VendorSerializer
class CategoryViewSet(AdminModelViewSet):
    queryset=Category.objects.all().order_by('name'); serializer_class=CategorySerializer
    public_catalog_read = True
    def get_serializer_class(self):
        if self.request.method in permissions.SAFE_METHODS and not self.request.user.is_staff:
            return PublicCategorySerializer
        return CategorySerializer
class ProductViewSet(viewsets.ModelViewSet):
    permission_classes=[StoreModelPermissions]
    public_catalog_read = True
    queryset=Product.objects.select_related('category','vendor').all().order_by('-created_at')
    serializer_class=ProductSerializer
    def get_queryset(self):
        products=Product.objects.select_related('category','vendor').order_by('-created_at')
        if self.request.user.is_staff:
            return products
        return products.filter(is_active=True)
    def get_serializer_class(self):
        if self.request.method in permissions.SAFE_METHODS and not self.request.user.is_staff:
            return PublicProductSerializer
        return ProductSerializer

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        try:
            product.delete()
        except ProtectedError:
            return Response(
                {'detail': 'Products referenced by historical inventory or orders cannot be deleted.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

class OrderViewSet(viewsets.ModelViewSet):
    queryset=CustomerOrder.objects.select_related('customer').prefetch_related('items').order_by('-created_at')
    permission_classes=[StoreModelPermissions]
    disable_staff_create = True

    def get_permissions(self):
        if not self.request.user.is_staff and self.action in ('list', 'retrieve', 'create'):
            return [permissions.IsAuthenticated()]
        return [StoreModelPermissions()]

    def get_queryset(self):
        orders=super().get_queryset()
        if self.request.user.is_staff:
            return orders
        return orders.filter(customer=self.request.user)

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return CustomerOrderSerializer
        if self.action == 'create':
            return CustomerOrderCreateSerializer
        return CustomerOrderReadSerializer

    def create(self, request, *args, **kwargs):
        if request.user.is_staff:
            return Response({'detail': 'Staff-created orders are disabled.'}, status=status.HTTP_403_FORBIDDEN)
        serializer=self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order=serializer.save()
        response_serializer=CustomerOrderReadSerializer(order, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def _validate_staff_order_update(self, request):
        if request.user.is_staff:
            unexpected = set(request.data.keys()) - {'status'}
            if unexpected:
                return Response({'detail': 'Staff may only update order fulfillment status.'}, status=400)
            if request.data.get('status') == 'Cancelled':
                return Response({'detail': 'Order cancellation requires the approved cancellation workflow.'}, status=403)
        return None

    def update(self, request, *args, **kwargs):
        error = self._validate_staff_order_update(request)
        if error:
            return error
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        error = self._validate_staff_order_update(request)
        if error:
            return error
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Orders cannot be deleted.'}, status=403)

    @action(detail=True, methods=['post'], permission_classes=[StoreModelPermissions])
    def cancel(self, request, pk=None):
        order = self.get_object()
        serializer = CancellationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .services import cancel_customer_order
        try:
            event = cancel_customer_order(
                order.pk, request.user, reason=serializer.validated_data['reason'],
            )
        except CustomerOrder.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=404)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
            return Response({'detail': detail}, status=400)
        return Response({
            'order_id': event.order_id, 'status': 'Cancelled',
            'reason': event.reason, 'actor_id': event.actor_id,
            'cancelled_at': event.cancelled_at,
        })

class PurchaseViewSet(AdminModelViewSet):
    queryset=VendorPurchase.objects.select_related('vendor','product').all().order_by('-purchased_at'); serializer_class=VendorPurchaseSerializer
    @action(detail=True, methods=['post'], permission_classes=[StoreModelPermissions])
    def receive(self, request, pk=None):
        from .services import receive_vendor_purchase
        try:
            purchase = receive_vendor_purchase(self.get_object().pk, request.user)
        except VendorPurchase.DoesNotExist:
            return Response({'detail': 'Vendor purchase not found.'}, status=404)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
            return Response({'detail': detail}, status=400)
        return Response(self.get_serializer(purchase).data)


def _workflow_actor(request, permission):
    return bool(request.user.is_authenticated and request.user.is_staff
                and request.user.has_perm(permission))


def _refund_data(refund):
    source_payment = None
    if refund.receipt_id:
        receipt = refund.receipt
        source_payment = {
            'kind': 'Receipt',
            'receipt_number': str(receipt.receipt_number),
            'amount': str(receipt.amount),
            'reference': receipt.transaction_reference_snapshot,
            'verified_at': receipt.verified_at,
        }
    elif refund.attempt_id:
        attempt = refund.attempt
        source_payment = {
            'kind': 'Payment attempt',
            'amount': str(attempt.expected_amount),
            'reference': attempt.transaction_reference,
            'status': attempt.status,
        }
    return {
        'id': refund.pk, 'order_id': refund.order_id,
        'order_reference': refund.order.order_reference,
        'attempt_id': refund.attempt_id, 'receipt_id': refund.receipt_id,
        'source_payment': source_payment,
        'amount': str(refund.amount), 'reason': refund.reason,
        'status': refund.status, 'requested_by_id': refund.requested_by_id,
        'requested_at': refund.requested_at, 'confirmed_by_id': refund.confirmed_by_id,
        'confirmed_at': refund.confirmed_at,
        'manual_transaction_reference': refund.manual_transaction_reference,
        'reviewer_remarks': refund.reviewer_remarks,
    }


def _paged_audit_response(request, queryset, serializer):
    try:
        page = int(request.query_params.get('page', '1'))
        page_size = int(request.query_params.get('page_size', '50'))
    except (TypeError, ValueError):
        return Response({'detail': 'page and page_size must be positive integers.'}, status=400)
    if page < 1 or page_size < 1 or page_size > 100:
        return Response({'detail': 'page must be positive and page_size must be between 1 and 100.'}, status=400)
    count = queryset.count()
    start = (page - 1) * page_size
    return Response({
        'count': count,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (count + page_size - 1) // page_size),
        'results': [serializer(row) for row in queryset[start:start + page_size]],
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_refund_list(request):
    if not request.user.is_staff or not any(request.user.has_perm(permission) for permission in (
        'store.view_paymentrefund', 'store.request_refund', 'store.confirm_refund',
    )):
        return Response({'detail': 'Refund access permission required.'}, status=403)
    refunds = PaymentRefund.objects.select_related(
        'order', 'requested_by', 'confirmed_by', 'receipt', 'attempt',
    ).order_by('-requested_at', '-pk')
    return _paged_audit_response(request, refunds, _refund_data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_reconciliation_list(request):
    if not request.user.is_staff or not request.user.has_perm('store.view_orderpaymentreconciliation'):
        return Response({'detail': 'Payment reconciliation history permission required.'}, status=403)
    reconciliations = OrderPaymentReconciliation.objects.select_related(
        'order', 'actor',
    ).order_by('-reconciled_at', '-pk')
    return _paged_audit_response(request, reconciliations, lambda event: {
        'id': event.pk,
        'order_id': event.order_id,
        'order_reference': event.order.order_reference,
        'outcome': event.outcome,
        'confirmed_amount': str(event.confirmed_amount) if event.confirmed_amount is not None else None,
        'reason': event.reason,
        'evidence_reference': event.evidence_reference,
        'actor_id': event.actor_id,
        'actor': event.actor.get_username(),
        'reconciled_at': event.reconciled_at,
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def inventory_movement_list(request):
    if not request.user.is_staff or not request.user.has_perm('store.view_inventorymovement'):
        return Response({'detail': 'Inventory movement history permission required.'}, status=403)
    movements = InventoryMovement.objects.select_related(
        'product', 'actor', 'order', 'vendor_purchase',
    ).order_by('-created_at', '-pk')
    return _paged_audit_response(request, movements, lambda movement: {
        'id': movement.pk,
        'product_id': movement.product_id,
        'product_name': movement.product.name,
        'movement_type': movement.movement_type,
        'direction': movement.direction,
        'quantity': movement.quantity,
        'resulting_stock': movement.resulting_stock,
        'order_id': movement.order_id,
        'vendor_purchase_id': movement.vendor_purchase_id,
        'actor': movement.actor.get_username() if movement.actor_id else None,
        'reason': movement.reason,
        'created_at': movement.created_at,
    })


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def order_refunds(request, order_id):
    if request.method == 'GET':
        if not (_workflow_actor(request, 'store.request_refund')
                or _workflow_actor(request, 'store.confirm_refund')):
            return Response({'detail': 'Refund access permission required.'}, status=403)
        if not CustomerOrder.objects.filter(pk=order_id).exists():
            return Response({'detail': 'Order not found.'}, status=404)
        refunds = PaymentRefund.objects.filter(order_id=order_id).select_related(
            'order', 'requested_by', 'confirmed_by', 'receipt', 'attempt',
        )
        return Response([_refund_data(refund) for refund in refunds])
    if not _workflow_actor(request, 'store.request_refund'):
        return Response({'detail': 'Refund request permission required.'}, status=403)
    serializer = RefundRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from .services import request_payment_refund
    try:
        refund = request_payment_refund(order_id, actor=request.user, **serializer.validated_data)
    except CustomerOrder.DoesNotExist:
        return Response({'detail': 'Order not found.'}, status=404)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return Response({'detail': detail}, status=400)
    return Response(_refund_data(refund), status=201)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def refund_review_action(request, refund_id, decision):
    if not _workflow_actor(request, 'store.confirm_refund'):
        return Response({'detail': 'Refund confirmation permission required.'}, status=403)
    if decision not in ('confirm', 'reject'):
        return Response({'detail': 'Unknown refund action.'}, status=404)
    serializer = RefundReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from .services import review_payment_refund
    try:
        refund = review_payment_refund(
            refund_id, request.user, confirm=decision == 'confirm',
            manual_reference=serializer.validated_data.get('manual_transaction_reference', ''),
            remarks=serializer.validated_data['remarks'],
        )
    except PaymentRefund.DoesNotExist:
        return Response({'detail': 'Refund request not found.'}, status=404)
    except PermissionDenied as exc:
        return Response({'detail': str(exc)}, status=403)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return Response({'detail': detail}, status=400)
    except IntegrityError:
        return Response({'detail': 'This refund reference is already recorded.'}, status=409)
    return Response(_refund_data(refund))


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def order_payment_reconciliation(request, order_id):
    if not _workflow_actor(request, 'store.reconcile_order_payment'):
        return Response({'detail': 'Payment reconciliation permission required.'}, status=403)
    serializer = PaymentReconciliationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from .services import reconcile_order_payment
    try:
        event = reconcile_order_payment(order_id, request.user, **serializer.validated_data)
    except CustomerOrder.DoesNotExist:
        return Response({'detail': 'Order not found.'}, status=404)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return Response({'detail': detail}, status=400)
    return Response({
        'id': event.pk, 'order_id': event.order_id, 'outcome': event.outcome,
        'confirmed_amount': str(event.confirmed_amount) if event.confirmed_amount is not None else None,
        'reason': event.reason, 'evidence_reference': event.evidence_reference,
        'actor_id': event.actor_id, 'reconciled_at': event.reconciled_at,
    }, status=201)
class ContactViewSet(AdminModelViewSet):
    queryset=ContactMessage.objects.all().order_by('-created_at'); serializer_class=ContactMessageSerializer
class FeedbackViewSet(AdminModelViewSet):
    queryset=Feedback.objects.all().order_by('-created_at'); serializer_class=FeedbackSerializer
@api_view(['GET'])
@permission_classes([StoreDashboardPermission])
def dashboard_stats(request):
    from django.conf import settings
    return Response({'users':User.objects.count(),'categories':Category.objects.count(),'products':Product.objects.filter(is_active=True).count(),'orders':CustomerOrder.objects.count(),'vendors':Vendor.objects.count(),'low_stock':Product.objects.filter(stock__lte=settings.STORE_LOW_STOCK_THRESHOLD, is_active=True).count()})
