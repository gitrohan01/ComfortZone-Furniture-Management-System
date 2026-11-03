from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch
from django.core.management import call_command
from django.contrib.auth.models import Group

from .models import Category, Product, Vendor


class AdminApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password="test-password", is_staff=True, is_superuser=True
        )
        self.customer = User.objects.create_user(
            username="customer", password="test-password"
        )
        self.category = Category.objects.create(name="Seating")
        self.vendor = Vendor.objects.create(name="Oak Works", email="oak@example.test")
        self.product = Product.objects.create(
            name="Oak Chair", category=self.category, vendor=self.vendor,
            price="125.00", stock=8,
        )
        Product.objects.create(
            name="Archived Chair", category=self.category, vendor=self.vendor,
            price="100.00", stock=0, is_active=False,
        )

    def test_staff_can_load_admin_dashboard_and_resource_lists(self):
        self.client.force_authenticate(user=self.admin)

        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["users"], 2)
        self.assertEqual(dashboard.data["categories"], 1)
        self.assertEqual(dashboard.data["products"], 1)
        self.assertEqual(dashboard.data["low_stock"], 0)

        for endpoint in (
            "users", "vendors", "categories", "products", "orders",
            "vendor-purchases", "contact-messages", "feedback",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(f"/api/{endpoint}/").status_code, 200)

    def test_staff_can_create_update_and_delete_category(self):
        self.client.force_authenticate(user=self.admin)

        created = self.client.post("/api/categories/", {"name": "Tables"}, format="json")
        self.assertEqual(created.status_code, 201)
        category_id = created.data["id"]

        updated = self.client.patch(
            f"/api/categories/{category_id}/", {"description": "Dining furniture"}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["description"], "Dining furniture")

        deleted = self.client.delete(f"/api/categories/{category_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Category.objects.filter(pk=category_id).exists())

    def test_staff_user_creation_sets_password_without_exposing_it(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/users/",
            {"username": "new-customer", "password": "Secure-test-pass-294!", "email": "new@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data)
        created_user = User.objects.get(username="new-customer")
        self.assertTrue(created_user.check_password("Secure-test-pass-294!"))

    def test_user_creation_rejects_missing_or_invalid_password(self):
        self.client.force_authenticate(user=self.admin)

        missing = self.client.post(
            "/api/users/", {"username": "missing-password"}, format="json"
        )
        invalid = self.client.post(
            "/api/users/", {"username": "short-password", "password": "short"}, format="json"
        )

        self.assertEqual(missing.status_code, 400)
        self.assertIn("password", missing.data)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("password", invalid.data)

    def test_user_password_update_is_hashed_and_not_returned(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/users/{self.customer.pk}/",
            {"password": "Replacement-test-pass-294!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("Replacement-test-pass-294!"))

    def test_user_edit_keeps_password_when_password_is_omitted(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/users/{self.customer.pk}/", {"first_name": "Updated"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("test-password"))

    def test_non_staff_cannot_access_admin_data_or_write_products(self):
        self.client.force_authenticate(user=self.customer)

        self.assertEqual(self.client.get("/api/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/products/", {"name": "Unauthorized"}, format="json").status_code,
            403,
        )

    def test_missing_and_expired_access_tokens_are_rejected_and_refresh_recovers(self):
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

        refresh = RefreshToken.for_user(self.admin)
        expired_access = refresh.access_token
        expired_access["exp"] = int((timezone.now() - timedelta(seconds=5)).timestamp())
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_access}")
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

        refreshed = self.client.post(
            "/api/auth/refresh/", {"refresh": str(refresh)}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)

    def test_invalid_refresh_token_is_rejected(self):
        response = self.client.post(
            "/api/auth/refresh/", {"refresh": "not-a-valid-refresh-token"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_product_catalogue_remains_public_and_staff_writes_work(self):
        public_response = self.client.get("/api/products/")
        self.assertEqual(public_response.status_code, 200)
        self.assertIn("Oak Chair", [product["name"] for product in public_response.data])

        self.client.force_authenticate(user=self.admin)
        updated = self.client.patch(
            f"/api/products/{self.product.pk}/",
            {"stock": 3, "stock_reason": "Cycle count correction."}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["stock"], 3)

    def test_public_catalogue_excludes_inactive_products_and_vendor_fields(self):
        products = self.client.get("/api/products/")
        self.assertEqual(products.status_code, 200)
        self.assertEqual([row["name"] for row in products.data], ["Oak Chair"])
        self.assertNotIn("vendor", products.data[0])
        self.assertNotIn("is_active", products.data[0])
        self.assertEqual(self.client.get("/api/categories/").status_code, 200)

    def test_customer_order_calculates_totals_and_snapshots_product_details(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post("/api/orders/", {
            "customer_name": "Customer One",
            "customer_email": "customer@example.test",
            "shipping_address": "10 Oak Street",
            "items": [{"product_id": self.product.pk, "quantity": 2}],
            "total_amount": "0.01",
            "status": "Delivered",
            "payment_status": "Paid",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["total_amount"], "250.00")
        self.assertEqual(response.data["status"], "Pending")
        self.assertEqual(response.data["payment_status"], "Pending")
        self.assertTrue(response.data["order_reference"])
        self.assertEqual(response.data["items"][0]["product_name"], "Oak Chair")
        self.assertEqual(response.data["items"][0]["unit_price"], "125.00")
        self.assertEqual(response.data["items"][0]["line_subtotal"], "250.00")
        from .models import CustomerOrder, InventoryMovement
        order = CustomerOrder.objects.get(pk=response.data['id'])
        allocation = InventoryMovement.objects.get(order=order)
        self.assertEqual(allocation.movement_type, InventoryMovement.TYPE_ORDER_ALLOCATION)
        self.assertEqual(allocation.direction, InventoryMovement.DIRECTION_OUT)
        self.assertEqual(allocation.quantity, 2)
        self.assertEqual(allocation.resulting_stock, 6)
        self.product.name = "Renamed After Order"
        self.product.price = "150.00"
        self.product.save(update_fields=["name", "price"])
        detail = self.client.get(f"/api/orders/{response.data['id']}/")
        self.assertEqual(detail.data["items"][0]["product_name"], "Oak Chair")
        self.assertEqual(detail.data["items"][0]["unit_price"], "125.00")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)

    def test_customer_checkout_rejects_invalid_quantities_and_unavailable_products(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"customer_name": "Customer One", "shipping_address": "10 Oak Street"}
        too_many = self.client.post("/api/orders/", {
            **payload, "items": [{"product_id": self.product.pk, "quantity": 99}],
        }, format="json")
        inactive = self.client.post("/api/orders/", {
            **payload, "items": [{"product_id": Product.objects.get(name="Archived Chair").pk, "quantity": 1}],
        }, format="json")
        zero = self.client.post("/api/orders/", {
            **payload, "items": [{"product_id": self.product.pk, "quantity": 0}],
        }, format="json")

        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(inactive.status_code, 400)
        self.assertEqual(zero.status_code, 400)
        self.assertEqual(self.client.get("/api/orders/").data, [])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_checkout_rejects_empty_duplicate_and_blank_delivery_data(self):
        self.client.force_authenticate(user=self.customer)
        base = {"customer_name": "Customer One", "shipping_address": "10 Oak Street"}
        empty = self.client.post("/api/orders/", {**base, "items": []}, format="json")
        duplicate = self.client.post("/api/orders/", {**base, "items": [
            {"product_id": self.product.pk, "quantity": 1},
            {"product_id": self.product.pk, "quantity": 1},
        ]}, format="json")
        blank_address = self.client.post("/api/orders/", {
            **base, "shipping_address": "  ", "items": [{"product_id": self.product.pk, "quantity": 1}],
        }, format="json")
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(blank_address.status_code, 400)
        self.assertFalse(self.customer.store_orders.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_checkout_retries_order_reference_collision(self):
        from .models import CustomerOrder
        self.client.force_authenticate(user=self.customer)
        CustomerOrder.objects.create(order_reference="collision-reference", customer_name="Legacy")
        payload = {"customer_name": "Customer", "shipping_address": "10 Oak Street", "items": [
            {"product_id": self.product.pk, "quantity": 1},
        ]}
        with patch("store.serializers.uuid.uuid4", side_effect=["collision-reference", "fresh-reference"]):
            response = self.client.post("/api/orders/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["order_reference"], "fresh-reference")

    def test_order_references_are_unique_and_legacy_null_references_are_supported(self):
        from django.db import IntegrityError, transaction
        from .models import CustomerOrder
        first = CustomerOrder.objects.create(order_reference="unique-reference", customer_name="First")
        legacy_one = CustomerOrder.objects.create(order_reference=None, customer_name="Legacy one")
        legacy_two = CustomerOrder.objects.create(order_reference=None, customer_name="Legacy two")
        self.assertIsNone(legacy_one.order_reference)
        self.assertIsNone(legacy_two.order_reference)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerOrder.objects.create(order_reference=first.order_reference, customer_name="Duplicate")

    def test_legacy_unowned_orders_are_staff_only_and_have_empty_items(self):
        from .models import CustomerOrder
        legacy = CustomerOrder.objects.create(
            customer=None, order_reference=None, payment_status=None,
            customer_name="Historical customer", total_amount="45.00",
        )
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(self.client.get("/api/orders/").data, [])
        self.assertEqual(self.client.get(f"/api/orders/{legacy.pk}/").status_code, 404)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/api/orders/{legacy.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["order_reference"])
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_amount"], "45.00")

    def test_staff_order_status_transitions_are_enforced_and_payment_is_independent(self):
        from .models import CustomerOrder
        order = CustomerOrder.objects.create(customer=self.customer, customer_name="Customer")
        self.client.force_authenticate(user=self.admin)
        accepted = self.client.patch(f"/api/orders/{order.pk}/", {"status": "Processing"}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        forged = self.client.patch(f"/api/orders/{order.pk}/", {
            "status": "Processing", "payment_status": "Paid",
        }, format="json")
        self.assertEqual(forged.status_code, 400, forged.data)
        rejected = self.client.patch(f"/api/orders/{order.pk}/", {"status": "Delivered"}, format="json")
        self.assertEqual(rejected.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "Processing")
        self.assertEqual(order.payment_status, "Pending")

    def test_cancellation_is_disabled_until_refund_and_stock_workflow_exists(self):
        from .models import CustomerOrder, CustomerOrderItem
        order = CustomerOrder.objects.create(customer=self.customer, customer_name="Customer")
        CustomerOrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            unit_price=self.product.price, quantity=2, line_subtotal="250.00",
        )
        from .services import adjust_product_stock
        adjust_product_stock(
            self.product.pk, target_stock=6, actor=self.admin,
            reason='Prepare cancellation stock assertion.',
        )
        self.client.force_authenticate(user=self.admin)
        cancelled = self.client.patch(f"/api/orders/{order.pk}/", {"status": "Cancelled"}, format="json")
        self.assertEqual(cancelled.status_code, 403, cancelled.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)

    def test_cancellation_is_rejected_by_serializer_model_and_queryset(self):
        from rest_framework.exceptions import ValidationError as SerializerValidationError
        from .models import CustomerOrder
        from .serializers import CustomerOrderSerializer
        order = CustomerOrder.objects.create(customer=self.customer, customer_name="Customer")

        order.status = "Cancelled"
        with self.assertRaises(ValidationError):
            order.save(update_fields=["status"])

        order.refresh_from_db()
        serializer = CustomerOrderSerializer(order, data={"status": "Cancelled"}, partial=True)
        serializer.is_valid(raise_exception=True)
        with self.assertRaises(SerializerValidationError):
            serializer.save()

        with self.assertRaises(ValidationError):
            CustomerOrder.objects.filter(pk=order.pk).update(status="Cancelled")
        order.status = "Cancelled"
        with self.assertRaises(ValidationError):
            CustomerOrder.objects.bulk_update([order], ["status"])
        with self.assertRaises(ValidationError):
            CustomerOrder.objects.create(customer=self.customer, customer_name="Forged cancelled order",
                                         status="Cancelled")
        order.refresh_from_db()
        self.assertEqual(order.status, "Pending")

    def test_product_api_rejects_negative_price(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f"/api/products/{self.product.pk}/", {"price": "-1.00"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_customers_only_list_and_retrieve_their_own_orders(self):
        from .models import CustomerOrder

        owned = CustomerOrder.objects.create(
            customer=self.customer, customer_name="Customer", total_amount="10.00"
        )
        other_user = User.objects.create_user(username="other", password="test-password")
        other = CustomerOrder.objects.create(
            customer=other_user, customer_name="Other", total_amount="20.00"
        )
        self.client.force_authenticate(user=self.customer)

        listing = self.client.get("/api/orders/")
        self.assertEqual([row["id"] for row in listing.data], [owned.pk])
        self.assertEqual(self.client.get(f"/api/orders/{owned.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{other.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/orders/{owned.pk}/", {"status": "Delivered"}, format="json").status_code, 403)

    def test_staff_can_view_customer_orders_and_nested_items_through_existing_api(self):
        from .models import CustomerOrder, CustomerOrderItem

        order = CustomerOrder.objects.create(
            customer=self.customer, customer_name="Customer", total_amount="125.00"
        )
        CustomerOrderItem.objects.create(
            order=order, product=self.product, product_name="Oak Chair",
            unit_price="125.00", quantity=1, line_subtotal="125.00",
        )
        self.client.force_authenticate(user=self.admin)

        listing = self.client.get("/api/orders/")
        row = next(item for item in listing.data if item["id"] == order.pk)
        self.assertEqual(row["items"][0]["product_name"], "Oak Chair")
        self.assertEqual(row["payment_status"], "Pending")
        other_user = User.objects.create_user(username="second-customer", password="test-password")
        second_order = CustomerOrder.objects.create(customer=other_user, customer_name="Second customer")
        all_rows = self.client.get("/api/orders/").data
        self.assertEqual({item["id"] for item in all_rows}, {order.pk, second_order.pk})

    def test_staff_manual_order_creation_is_disabled(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/orders/", {
            "customer_name": "Walk-in customer",
            "customer_email": "walkin@example.test",
            "shipping_address": "Showroom pickup",
            "total_amount": "45.00",
            "status": "Delivered",
            "payment_status": "Paid",
        }, format="json")
        self.assertEqual(response.status_code, 403, response.data)

    def test_public_registration_cannot_create_staff_user(self):
        response = self.client.post("/api/register/", {
            "username": "public-user", "email": "public@example.test",
            "password": "safe-password-2026", "confirm_password": "safe-password-2026",
            "is_staff": True, "is_superuser": True, "role": "admin",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(username="public-user")
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)


class StaffRolePermissionTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='role-staff', password='test-password', is_staff=True)
        self.customer = User.objects.create_user(username='role-customer', password='test-password')
        self.category = Category.objects.create(name='Role Seating')
        self.product = Product.objects.create(name='Role Chair', category=self.category, price='20.00', stock=3)

    def grant(self, user, *codenames):
        permissions = Permission.objects.filter(content_type__app_label='store', codename__in=codenames)
        user.user_permissions.add(*permissions)
        user.refresh_from_db()
        for cache_name in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            if hasattr(user, cache_name):
                delattr(user, cache_name)
        self.client.force_authenticate(user)

    def test_self_permissions_endpoint_returns_effective_permissions_without_other_accounts(self):
        self.grant(self.staff, 'view_reports')
        response = self.client.get(f'/api/auth/permissions/?user_id={self.customer.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['user_id'], self.staff.pk)
        self.assertTrue(response.data['is_staff'])
        self.assertIn('store.view_reports', response.data['permissions'])
        self.assertNotIn('password', response.data)
        self.assertNotIn('users', response.data)

        self.client.force_authenticate(self.customer)
        customer_response = self.client.get('/api/auth/permissions/')
        self.assertEqual(customer_response.status_code, 200, customer_response.data)
        self.assertFalse(customer_response.data['is_staff'])
        self.assertEqual(customer_response.data['permissions'], [])
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/auth/permissions/').status_code, 401)

    def test_audit_history_lists_require_their_specific_view_permissions(self):
        self.client.force_authenticate(self.staff)
        endpoints = [
            ('view_paymentrefund', '/api/admin/refunds/'),
            ('view_orderpaymentreconciliation', '/api/admin/payment-reconciliations/'),
            ('view_inventorymovement', '/api/admin/inventory-movements/'),
        ]
        for codename, endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 403)
                self.grant(self.staff, codename)
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['count'], 0)
        self.customer.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='store',
            codename__in=('view_paymentrefund', 'view_orderpaymentreconciliation', 'view_inventorymovement'),
        ))
        self.client.force_authenticate(self.customer)
        for _codename, endpoint in endpoints:
            with self.subTest(non_staff_endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 403)

    def test_anonymous_and_customer_cannot_use_staff_resources_but_catalogue_is_public(self):
        self.assertEqual(self.client.get('/api/users/').status_code, 401)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)
        self.assertEqual(self.client.post('/api/vendors/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.get('/api/products/').status_code, 200)
        self.assertEqual(self.client.get('/api/categories/').status_code, 200)

    def test_reports_only_staff_cannot_read_or_mutate_business_resources(self):
        self.grant(self.staff, 'view_reports')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/reports/summary/').status_code, 200)
        for method, path, data in (
            ('get', '/api/users/', None), ('get', '/api/products/', None),
            ('get', '/api/categories/', None), ('get', '/api/vendors/', None),
            ('get', '/api/orders/', None), ('get', '/api/vendor-purchases/', None),
            ('get', '/api/contact-messages/', None), ('get', '/api/feedback/', None),
            ('post', '/api/categories/', {'name': 'Blocked'}),
            ('put', f'/api/products/{self.product.pk}/', {'name': 'Blocked'}),
            ('patch', f'/api/products/{self.product.pk}/', {'name': 'Blocked'}),
            ('delete', f'/api/categories/{self.category.pk}/', None),
        ):
            response = getattr(self.client, method)(path, data, format='json') if data is not None else getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 403, f'{method.upper()} {path}: {response.data}')
        from .models import CustomerOrder, VendorPurchase
        order = CustomerOrder.objects.create(customer=self.customer, customer_name='Reports-only order')
        vendor = Vendor.objects.create(name='Reports-only vendor', email='reports-only-vendor@example.test')
        purchase = VendorPurchase.objects.create(
            vendor=vendor, product=self.product, quantity=1, unit_cost='10.00', status='Approved',
        )
        self.assertEqual(self.client.post(
            f'/api/orders/{order.pk}/cancel/', {'reason': 'Blocked.'}, format='json',
        ).status_code, 403)
        self.assertEqual(self.client.post(
            f'/api/admin/orders/{order.pk}/refunds/',
            {'amount': '1.00', 'reason': 'Blocked.'}, format='json',
        ).status_code, 403)
        self.assertEqual(self.client.post(
            f'/api/admin/orders/{order.pk}/payment-reconciliation/',
            {'outcome': 'Unpaid', 'reason': 'Blocked.', 'evidence_reference': 'REF'},
            format='json',
        ).status_code, 403)
        self.assertEqual(self.client.post('/api/admin/refunds/1/confirm/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'/api/vendor-purchases/{purchase.pk}/receive/').status_code, 403)

    def test_model_permissions_are_method_specific(self):
        self.client.force_authenticate(self.staff)
        self.grant(self.staff, 'view_category')
        self.assertEqual(self.client.get('/api/categories/').status_code, 200)
        self.assertEqual(self.client.post('/api/categories/', {'name': 'New'}, format='json').status_code, 403)
        self.grant(self.staff, 'add_category')
        created = self.client.post('/api/categories/', {'name': 'New'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.client.patch(f"/api/categories/{created.data['id']}/", {'description': 'x'}, format='json').status_code, 403)
        self.grant(self.staff, 'change_category')
        self.assertEqual(self.client.patch(f"/api/categories/{created.data['id']}/", {'description': 'x'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f"/api/categories/{created.data['id']}/").status_code, 403)
        self.grant(self.staff, 'delete_category')
        self.assertEqual(self.client.delete(f"/api/categories/{created.data['id']}/").status_code, 204)

    def test_stock_changes_require_adjust_stock_and_purchase_receiving_is_dedicated(self):
        from .models import VendorPurchase
        self.client.force_authenticate(self.staff)
        self.grant(self.staff, 'change_product')
        stock_payload = {'stock': 9, 'stock_reason': 'Cycle count correction.'}
        self.assertEqual(self.client.patch(f'/api/products/{self.product.pk}/', stock_payload, format='json').status_code, 403)
        self.grant(self.staff, 'adjust_stock')
        adjusted = self.client.patch(f'/api/products/{self.product.pk}/', stock_payload, format='json')
        self.assertEqual(adjusted.status_code, 200, adjusted.data)
        purchase = VendorPurchase.objects.create(vendor=Vendor.objects.create(name='Role Vendor', email='role-vendor@example.test'),
            product=self.product, quantity=2, unit_cost='10.00', status='Approved')
        self.grant(self.staff, 'view_vendorpurchase', 'change_vendorpurchase')
        self.assertEqual(self.client.patch(f'/api/vendor-purchases/{purchase.pk}/', {'status': 'Received'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'/api/vendor-purchases/{purchase.pk}/receive/').status_code, 403)
        self.grant(self.staff, 'receive_vendorpurchase')
        response = self.client.post(f'/api/vendor-purchases/{purchase.pk}/receive/')
        self.assertEqual(response.status_code, 200, response.data)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'Received')
        self.assertEqual(purchase.received_by_id, self.staff.pk)
        self.assertTrue(purchase.inventory_movements.filter(quantity=2, direction='IN').exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 11)
        duplicate = self.client.post(f'/api/vendor-purchases/{purchase.pk}/receive/')
        self.assertEqual(duplicate.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 11)

    def test_order_read_and_fulfillment_permissions_do_not_allow_creation_or_delete(self):
        from .models import CustomerOrder
        order = CustomerOrder.objects.create(customer=self.customer, customer_name='Role Customer')
        self.client.force_authenticate(self.staff)
        self.grant(self.staff, 'view_customerorder')
        self.assertEqual(self.client.get(f'/api/orders/{order.pk}/').status_code, 200)
        self.assertEqual(self.client.post('/api/orders/', {}, format='json').status_code, 403)
        self.grant(self.staff, 'change_order_fulfillment')
        self.assertEqual(self.client.patch(f'/api/orders/{order.pk}/', {'status': 'Processing'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'/api/orders/{order.pk}/', {'status': 'Cancelled'}, format='json').status_code, 403)
        self.grant(self.staff, 'delete_customerorder')
        self.assertEqual(self.client.delete(f'/api/orders/{order.pk}/').status_code, 403)

    def test_role_provision_command_is_idempotent_and_does_not_assign_users(self):
        call_command('provision_staff_roles', verbosity=0)
        call_command('provision_staff_roles', verbosity=0)
        names = {'Administrator', 'Store Manager', 'Inventory Manager', 'Sales/Order Staff', 'Payment Reviewer', 'Reports-only Staff'}
        self.assertEqual(set(Group.objects.filter(name__in=names).values_list('name', flat=True)), names)
        reports = Group.objects.get(name='Reports-only Staff')
        self.assertEqual(set(reports.permissions.values_list('codename', flat=True)), {'view_reports'})
        reviewer = Group.objects.get(name='Payment Reviewer')
        self.assertEqual(set(reviewer.permissions.values_list('codename', flat=True)), {
            'verify_payment', 'confirm_refund', 'view_paymentrefund',
            'view_orderpaymentreconciliation',
        })
        role_grants = {
            'Store Manager': {'view_product', 'add_product', 'change_product', 'view_category', 'add_category',
                'change_category', 'view_vendor', 'add_vendor', 'change_vendor', 'view_vendorpurchase',
                'add_vendorpurchase', 'change_vendorpurchase', 'view_customerorder', 'change_order_fulfillment',
                'view_contactmessage', 'view_feedback', 'view_dashboard', 'cancel_customerorder',
                'request_refund', 'reconcile_order_payment', 'view_ordercancellation',
                'view_paymentrefund', 'view_orderpaymentreconciliation', 'view_inventorymovement'},
            'Inventory Manager': {'view_product', 'view_category', 'view_vendor', 'view_vendorpurchase',
                'adjust_stock', 'receive_vendorpurchase', 'view_inventorymovement'},
            'Sales/Order Staff': {'view_customerorder', 'change_order_fulfillment', 'view_dashboard'},
            'Reports-only Staff': {'view_reports'},
        }
        for name, expected in role_grants.items():
            with self.subTest(role=name):
                self.assertEqual(set(Group.objects.get(name=name).permissions.values_list('codename', flat=True)), expected)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.groups.filter(name__in=names).exists())

    def test_payment_reviewer_gets_payment_context_without_general_order_access(self):
        self.grant(self.staff, 'verify_payment')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/payment-attempts/').status_code, 200)
        self.assertEqual(self.client.get('/api/orders/').status_code, 403)
        self.assertEqual(self.client.get('/api/products/').status_code, 403)

    def test_user_api_cannot_assign_staff_privileges_or_groups(self):
        self.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='auth', codename__in=('add_user', 'change_user')
        ))
        self.client.force_authenticate(self.staff)
        response = self.client.post('/api/users/', {
            'username': 'attempted-staff', 'password': 'Strong-password-2026!',
            'is_staff': True, 'is_superuser': True, 'is_active': False, 'groups': [1],
            'user_permissions': [1],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        created = User.objects.get(username='attempted-staff')
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertTrue(created.is_active)
        self.assertFalse(created.groups.exists())
        self.assertFalse(created.user_permissions.exists())

    def test_staff_can_create_update_and_delete_product(self):
        self.grant(self.staff, 'add_product', 'change_product', 'delete_product', 'adjust_stock')
        self.client.force_authenticate(user=self.staff)

        created = self.client.post(
            "/api/products/",
            {"name": "Dining Chair", "category": self.category.pk, "price": "85.50",
             "stock": 4, "stock_reason": "Initial inventory receipt."},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        product_id = created.data["id"]

        updated = self.client.patch(
            f"/api/products/{product_id}/",
            {"stock": 7, "stock_reason": "Cycle count correction."}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["stock"], 7)

        deleted = self.client.delete(f"/api/products/{product_id}/")
        self.assertEqual(deleted.status_code, 409)
        self.assertTrue(Product.objects.filter(pk=product_id).exists())


class PaymentFoundationTests(APITestCase):
    def setUp(self):
        from .models import CustomerOrder
        self.customer = User.objects.create_user(username='payment-customer', password='test-password')
        self.staff = User.objects.create_user(username='payment-staff', password='test-password', is_staff=True)
        self.order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Payment Customer',
            customer_email='customer@example.test', total_amount=Decimal('123.40'),
        )
        self.config_permission = Permission.objects.get(
            content_type__app_label='store', codename='manage_payment_configuration')
        self.review_permission = Permission.objects.get(
            content_type__app_label='store', codename='verify_payment')
        self.config = self.make_config('Comfort Zone', 'comfortzone@upi')

    def make_config(self, display_name, upi_id):
        from .models import PaymentConfiguration
        return PaymentConfiguration.objects.create(
            display_name=display_name, upi_id=upi_id,
            qr_image='private/payment-config/qr/showroom.png',
        )

    def activate_config(self, configuration=None):
        self.staff.user_permissions.add(self.config_permission)
        self.staff = User.objects.get(pk=self.staff.pk)
        return (configuration or self.config).activate(self.staff)

    def make_instructions(self):
        from .services import create_order_payment_instructions
        self.activate_config()
        return create_order_payment_instructions(self.order)

    def make_attempt(self, instructions=None, reference='UPI-TXN-100'):
        from .models import PaymentAttempt
        instructions = instructions or self.make_instructions()
        return PaymentAttempt.objects.create(
            order=self.order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference=reference,
            proof_image='private/payment-proofs/proof.png',
        )

    def test_pending_attempt_requires_authorized_review_to_become_verified(self):
        from .models import PaymentAttempt, PaymentReceipt
        from .services import review_payment_attempt
        attempt = self.make_attempt()
        attempt.status = PaymentAttempt.STATUS_VERIFIED
        with self.assertRaises(ValidationError):
            attempt.save()

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_PENDING)
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.STATUS_VERIFIED)
        attempt.status = PaymentAttempt.STATUS_VERIFIED
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.bulk_update([attempt], ["status"])

        attempt.refresh_from_db()
        self.authorize_reviewer()
        review_payment_attempt(attempt.pk, self.staff, approve=True, bank_checked=True)
        attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_VERIFIED)
        self.assertEqual(self.order.payment_status, 'Paid')
        self.assertTrue(PaymentReceipt.objects.filter(attempt=attempt).exists())

    def authorize_reviewer(self):
        self.staff.user_permissions.add(self.review_permission)
        self.staff = User.objects.get(pk=self.staff.pk)

    def test_configuration_activation_and_unique_active_slot(self):
        from .models import PaymentConfiguration
        second = self.make_config('Comfort Zone New', 'comfortzone-new@upi')
        with self.assertRaises(PermissionDenied):
            self.config.activate(self.staff)
        self.activate_config()
        second.activate(self.staff)
        self.config.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(self.config.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(PaymentConfiguration.objects.filter(active_slot=1).count(), 1)

    def test_database_unique_nullable_active_slot_prevents_two_active_configs(self):
        from .models import PaymentConfiguration
        PaymentConfiguration.objects.create(
            display_name='Active one', upi_id='one@upi',
            qr_image='private/payment-config/qr/one.png', active_slot=1,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentConfiguration.objects.create(
                display_name='Active two', upi_id='two@upi',
                qr_image='private/payment-config/qr/two.png', active_slot=1,
            )

    def test_order_instructions_are_idempotent_and_immutable_snapshots(self):
        from .services import create_order_payment_instructions
        first = self.make_instructions()
        same = create_order_payment_instructions(self.order)
        self.assertEqual(first.pk, same.pk)
        self.assertEqual(first.expected_amount, Decimal('123.40'))
        self.assertEqual(first.upi_id, 'comfortzone@upi')
        self.assertEqual(first.qr_image_name, 'private/payment-config/qr/showroom.png')
        self.order.total_amount = Decimal('999.99')
        with self.assertRaises(ValidationError):
            self.order.save(update_fields=['total_amount'])
        self.order.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(first.expected_amount, Decimal('123.40'))
        self.assertEqual(self.order.total_amount, Decimal('123.40'))
        first.upi_id = 'changed@upi'
        with self.assertRaises(ValidationError):
            first.save()
        self.config.upi_id = 'mutated@upi'
        with self.assertRaises(ValidationError):
            self.config.save()

    def test_payment_attempt_relationships_decimal_amount_and_pending_order_guard(self):
        from .models import PaymentAttempt
        instructions = self.make_instructions()
        attempt = self.make_attempt(instructions)
        self.assertEqual(attempt.order, self.order)
        self.assertEqual(attempt.customer, self.customer)
        self.assertEqual(attempt.instructions, instructions)
        self.assertEqual(attempt.expected_amount, Decimal('123.40'))
        self.assertEqual(attempt.normalized_transaction_reference, 'UPI-TXN-100')
        self.assertEqual(PaymentAttempt._meta.get_field('expected_amount').max_digits, 10)
        self.assertEqual(PaymentAttempt._meta.get_field('expected_amount').decimal_places, 2)
        with self.assertRaises(ValidationError):
            PaymentAttempt.objects.create(
                order=self.order, customer=self.customer, instructions=instructions,
                expected_amount=Decimal('123.41'), transaction_reference='OTHER-TXN',
                proof_image='private/payment-proofs/other.png',
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_attempt(instructions, reference='UPI-TXN-101')

    def test_rejected_attempt_and_review_are_retained_for_corrected_submission(self):
        from .models import PaymentAttempt, PaymentReviewEvent
        instructions = self.make_instructions()
        attempt = self.make_attempt(instructions)
        self.authorize_reviewer()
        from .services import review_payment_attempt
        review_payment_attempt(attempt.pk, self.staff, approve=False,
                               remarks='Reference is unreadable; resubmit.')
        attempt.refresh_from_db()
        event = PaymentReviewEvent.objects.get(attempt=attempt)
        self.assertEqual(event.attempt_id, attempt.pk)
        with self.assertRaises(ProtectedError):
            attempt.delete()
        with self.assertRaises(ProtectedError):
            event.delete()
        retry = self.make_attempt(instructions, reference='UPI-TXN-CORRECTED')
        self.assertEqual(self.order.payment_attempts.count(), 2)
        self.assertEqual(retry.status, PaymentAttempt.STATUS_PENDING)

    def test_duplicate_verified_normalized_transaction_references_are_rejected(self):
        from .models import CustomerOrder, PaymentAttempt
        from .services import create_order_payment_instructions, review_payment_attempt
        instructions = self.make_instructions()
        first = self.make_attempt(instructions, reference='  utr-abc-123 ')
        self.authorize_reviewer()
        review_payment_attempt(first.pk, self.staff, approve=True, bank_checked=True)
        first.refresh_from_db()
        second_order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Second order', total_amount=Decimal('42.10'))
        second_instructions = create_order_payment_instructions(second_order)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.create(
                order=second_order, customer=self.customer, instructions=second_instructions,
                expected_amount=second_instructions.expected_amount,
                transaction_reference='UTR-ABC-123', proof_image='private/payment-proofs/second.png',
            )
        self.assertEqual(first.verified_transaction_reference, 'UTR-ABC-123')

    def test_receipt_is_unique_per_verified_attempt_and_snapshots_review(self):
        from .models import PaymentReceipt
        from .services import review_payment_attempt
        attempt = self.make_attempt()
        self.authorize_reviewer()
        review_payment_attempt(attempt.pk, self.staff, approve=True,
                               remarks='Matched bank record.', bank_checked=True)
        attempt.refresh_from_db()
        self.order.refresh_from_db()
        review = attempt.review_event
        receipt_data = {
            'attempt': attempt, 'amount': Decimal('123.40'),
            'order_reference_snapshot': self.order.order_reference,
            'customer_name_snapshot': self.order.customer_name,
            'customer_email_snapshot': self.order.customer_email,
            'showroom_name_snapshot': attempt.instructions.display_name,
            'upi_id_snapshot': attempt.instructions.upi_id,
            'transaction_reference_snapshot': attempt.transaction_reference,
            'reviewer_name_snapshot': review.reviewer_name,
            'verified_at': review.reviewed_at,
        }
        receipt = attempt.receipt
        self.assertEqual(receipt.amount, Decimal('123.40'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentReceipt.objects.create(**receipt_data)
        self.assertEqual(PaymentReceipt.objects.filter(attempt=attempt).count(), 1)

    def test_receipt_snapshot_is_immutable_and_stored_values_remain_unchanged(self):
        from .models import CustomerOrder, PaymentAttempt, PaymentReceipt
        from .services import create_order_payment_instructions, review_payment_attempt
        order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Independent Receipt Buyer',
            customer_email='independent@example.test', total_amount=Decimal('50.00'),
        )
        self.activate_config()
        instructions = create_order_payment_instructions(order)
        attempt = PaymentAttempt.objects.create(
            order=order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference='INDEPENDENT-RECEIPT',
            proof_image='private/payment-proofs/independent.png',
        )
        self.authorize_reviewer()
        review_payment_attempt(attempt.pk, self.staff, approve=True, bank_checked=True)
        receipt = PaymentReceipt.objects.get(attempt=attempt)
        original_name = receipt.customer_name_snapshot
        original_reference = receipt.transaction_reference_snapshot
        receipt.customer_name_snapshot = 'Changed Buyer'
        receipt.transaction_reference_snapshot = 'CHANGED-REFERENCE'
        with self.assertRaises(ValidationError):
            receipt.save()
        receipt.refresh_from_db()
        self.assertEqual(receipt.customer_name_snapshot, original_name)
        self.assertEqual(receipt.transaction_reference_snapshot, original_reference)

    def test_historical_null_payment_status_is_preserved(self):
        from .models import CustomerOrder
        legacy = CustomerOrder.objects.create(
            customer=None, customer_name='Historical order', payment_status=None,
            total_amount=Decimal('0.00'),
        )
        legacy.refresh_from_db()
        self.assertIsNone(legacy.payment_status)

    def test_payment_permissions_are_defined_but_not_granted_to_staff(self):
        self.assertEqual(self.review_permission.codename, 'verify_payment')
        self.assertEqual(self.config_permission.codename, 'manage_payment_configuration')
        self.assertTrue(self.staff.is_staff)
        self.assertFalse(self.staff.has_perm('store.verify_payment'))
        self.assertFalse(self.staff.has_perm('store.manage_payment_configuration'))


class PaymentWorkflowApiTests(APITestCase):
    def setUp(self):
        from .models import CustomerOrder, PaymentConfiguration
        self.customer = User.objects.create_user(username='workflow-customer', password='test-password')
        self.other = User.objects.create_user(username='workflow-other', password='test-password')
        self.staff = User.objects.create_user(username='workflow-staff', password='test-password', is_staff=True)
        self.order = CustomerOrder.objects.create(customer=self.customer, customer_name='Workflow Customer', total_amount='88.10')
        self.configuration = PaymentConfiguration.objects.create(display_name='Comfort Zone', upi_id='comfort@upi', qr_image='private/payment-config/qr/test.png', active_slot=1)

    @staticmethod
    def png():
        from PIL import Image
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = BytesIO()
        Image.new('RGB', (8, 8), 'white').save(buffer, format='PNG')
        return SimpleUploadedFile('proof.png', buffer.getvalue(), content_type='image/png')

    def grant(self, codename):
        permission = Permission.objects.get(content_type__app_label='store', codename=codename)
        self.staff.user_permissions.add(permission)
        self.staff = User.objects.get(pk=self.staff.pk)

    def instructions(self):
        self.client.force_authenticate(self.customer)
        first = self.client.post(f'/api/orders/{self.order.pk}/payment-instructions/')
        second = self.client.post(f'/api/orders/{self.order.pk}/payment-instructions/')
        return first, second

    def submit(self, reference='UTR-987'):
        self.client.force_authenticate(self.customer)
        return self.client.post(f'/api/orders/{self.order.pk}/payment-attempts/',
                                {'transaction_reference': reference, 'proof_image': self.png()}, format='multipart')

    def test_owner_instructions_are_idempotent_private_and_amount_exact(self):
        first, second = self.instructions()
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data, second.data)
        self.assertEqual(first.data['amount'], '88.10')
        self.assertEqual(first.data['upi_id'], 'comfort@upi')
        self.assertNotIn('private/', str(first.data))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f'/api/orders/{self.order.pk}/payment-instructions/').status_code, 404)

    def test_customer_submission_owner_pending_duplicate_and_history(self):
        self.instructions()
        created = self.submit()
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['expected_amount'], '88.10')
        self.assertNotIn('proof_image', created.data)
        self.assertEqual(self.submit('ANOTHER').status_code, 409)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/payment-attempts/').status_code, 404)
        self.client.force_authenticate(self.customer)
        self.assertEqual(len(self.client.get(f'/api/orders/{self.order.pk}/payment-attempts/').data), 1)

    def test_staff_review_permission_confirmation_approval_and_conflict(self):
        self.instructions()
        created = self.submit()
        attempt_id = created.data['id']
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/payment-attempts/').status_code, 403)
        self.grant('verify_payment')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/payment-attempts/').status_code, 200)
        missing_confirmation = self.client.post(f'/api/admin/payment-attempts/{attempt_id}/approve/', {}, format='json')
        self.assertEqual(missing_confirmation.status_code, 400)
        approved = self.client.post(f'/api/admin/payment-attempts/{attempt_id}/approve/', {'bank_checked': True}, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['order']['items'], [])
        self.assertEqual(approved.data['receipt']['amount'], str(self.order.total_amount))
        self.assertEqual(approved.data['receipt']['transaction_reference'], 'UTR-987')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'Paid')
        self.assertEqual(self.order.status, 'Pending')
        self.assertEqual(self.client.post(f'/api/admin/payment-attempts/{attempt_id}/approve/', {'bank_checked': True}, format='json').status_code, 409)

    def test_rejection_allows_corrected_attempt_and_keeps_order_pending(self):
        self.instructions()
        attempt_id = self.submit().data['id']
        self.grant('verify_payment')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f'/api/admin/payment-attempts/{attempt_id}/reject/', {}, format='json').status_code, 400)
        rejected = self.client.post(f'/api/admin/payment-attempts/{attempt_id}/reject/', {'remarks': 'Reference does not match.'}, format='json')
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'Pending')
        retried = self.submit('UTR-CORRECTED')
        self.assertEqual(retried.status_code, 201, retried.data)

    def test_configuration_permission_and_versioned_creation(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/payment-configurations/').status_code, 403)
        self.grant('manage_payment_configuration')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/payment-configurations/').status_code, 200)
        response = self.client.post('/api/admin/payment-configurations/', {
            'display_name': 'New Showroom', 'upi_id': 'new.showroom@upi', 'qr_image': self.png()}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotEqual(response.data['id'], self.configuration.pk)
        self.assertFalse(response.data['is_active'])


class PaymentReceiptApiTests(APITestCase):
    def setUp(self):
        from .models import CustomerOrder, PaymentConfiguration
        self.customer = User.objects.create_user(username='receipt-customer', password='test-password', email='buyer@example.test')
        self.other = User.objects.create_user(username='receipt-other', password='test-password')
        self.staff = User.objects.create_user(username='receipt-reviewer', password='test-password', is_staff=True, first_name='Asha', last_name='Reviewer')
        self.order = CustomerOrder.objects.create(customer=self.customer, customer_name='Snapshot Buyer', customer_email='buyer@example.test', shipping_address='Private delivery address', total_amount='1234.50')
        self.config = PaymentConfiguration.objects.create(display_name='Comfort Zone', upi_id='comfort@upi', qr_image='private/payment-config/qr/receipt.png', active_slot=1)
        self.grant_reviewer()

    def grant_reviewer(self):
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='verify_payment'))
        self.staff = User.objects.get(pk=self.staff.pk)

    def make_pending_attempt(self, reference='RECEIPT-UTR-123'):
        from .models import PaymentAttempt
        from .services import create_order_payment_instructions
        instructions = create_order_payment_instructions(self.order)
        return PaymentAttempt.objects.create(order=self.order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference=reference,
            proof_image='private/payment-proofs/receipt-proof.png')

    def approve(self, attempt):
        from .services import review_payment_attempt
        return review_payment_attempt(attempt.pk, self.staff, approve=True, bank_checked=True)

    @staticmethod
    def pdf_bytes(response):
        return b''.join(response.streaming_content)

    def test_unpaid_or_rejected_order_has_no_receipt(self):
        pending = self.make_pending_attempt()
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 404)
        from .services import review_payment_attempt
        review_payment_attempt(pending.pk, self.staff, approve=False, remarks='Transaction not found.')
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 404)

    def test_receipt_download_authorization_pdf_content_and_stable_snapshot(self):
        from .models import PaymentReceipt
        attempt = self.make_pending_attempt()
        self.approve(attempt)
        receipt = PaymentReceipt.objects.get(attempt=attempt)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 200)
        self.client.force_authenticate(self.customer)
        first = self.client.get(f'/api/orders/{self.order.pk}/receipt/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', first['Content-Disposition'])
        self.assertIn(str(receipt.receipt_number), first['Content-Disposition'])
        pdf = self.pdf_bytes(first)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'MANUAL UPI PAYMENT RECEIPT', pdf)
        self.assertEqual(receipt.amount, Decimal('1234.50'))
        self.assertIn(b'Comfort Zone', pdf)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='manage_payment_configuration'))
        self.staff = User.objects.get(pk=self.staff.pk)
        from .models import PaymentConfiguration
        new_config = PaymentConfiguration.objects.create(display_name='New Showroom', upi_id='new@upi', qr_image='private/payment-config/qr/new.png')
        new_config.activate(self.staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_name, 'Snapshot Buyer')
        second = self.client.get(f'/api/orders/{self.order.pk}/receipt/')
        second_pdf = self.pdf_bytes(second)
        self.assertEqual(first['Content-Disposition'], second['Content-Disposition'])
        self.assertIn(b'Snapshot Buyer', second_pdf)
        self.assertIn(b'comfort@upi', second_pdf)
        self.assertNotIn(b'new@upi', second_pdf)
        self.assertIn(b'INR 1,234.50', second_pdf)
        self.assertNotIn(b'Private delivery address', second_pdf)

    def test_anonymous_and_staff_without_permission_are_rejected(self):
        self.make_pending_attempt()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 401)
        self.staff.user_permissions.clear()
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(f'/api/orders/{self.order.pk}/receipt/').status_code, 403)

    def test_approval_creates_attempt_order_review_and_receipt_atomically(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        from .models import PaymentAttempt, PaymentReceipt, PaymentReviewEvent
        attempt = self.make_pending_attempt()
        with patch.object(PaymentReceipt.objects, 'create', side_effect=IntegrityError('receipt insert failed')):
            with self.assertRaises(IntegrityError):
                self.approve(attempt)
        attempt.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_PENDING)
        self.assertEqual(self.order.payment_status, 'Pending')
        self.assertEqual(self.order.status, 'Pending')
        self.assertFalse(PaymentReviewEvent.objects.filter(attempt=attempt).exists())
        self.assertFalse(PaymentReceipt.objects.filter(attempt=attempt).exists())

        self.approve(attempt)
        attempt.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_VERIFIED)
        self.assertEqual(self.order.payment_status, 'Paid')
        self.assertEqual(self.order.status, 'Pending')
        self.assertTrue(PaymentReviewEvent.objects.filter(attempt=attempt, action='Verified').exists())
        self.assertEqual(PaymentReceipt.objects.filter(attempt=attempt).count(), 1)
        with self.assertRaises(ValueError):
            self.approve(attempt)
        self.assertEqual(PaymentReceipt.objects.filter(attempt=attempt).count(), 1)

    def test_invalid_order_receipt_path_is_not_found(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/orders/999999/receipt/').status_code, 404)


class RefundCancellationInventoryTests(APITestCase):
    def setUp(self):
        from .models import Category, PaymentConfiguration
        self.customer = User.objects.create_user(username='phase52d-customer', password='test-password')
        self.manager = self.make_staff('phase52d-manager', 'cancel_customerorder',
            'request_refund', 'reconcile_order_payment')
        self.reviewer = self.make_staff('phase52d-reviewer', 'verify_payment', 'confirm_refund')
        self.inventory = self.make_staff('phase52d-inventory', 'adjust_stock', 'receive_vendorpurchase')
        self.unauthorized = User.objects.create_user(
            username='phase52d-unauthorized', password='test-password', is_staff=True,
        )
        self.category = Category.objects.create(name='Phase 5.2D Seating')
        self.product = Product.objects.create(
            name='Phase 5.2D Chair', category=self.category, price='50.00', stock=30,
        )
        self.configuration = PaymentConfiguration.objects.create(
            display_name='Comfort Zone', upi_id='phase52d@upi',
            qr_image='private/payment-config/qr/phase52d.png', active_slot=1,
        )

    @staticmethod
    def make_staff(username, *permissions):
        user = User.objects.create_user(username=username, password='test-password', is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='store', codename__in=permissions,
        ))
        user = User.objects.get(pk=user.pk)
        for cache_name in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            if hasattr(user, cache_name):
                delattr(user, cache_name)
        return user

    def make_order(self, *, status='Pending', payment_status='Pending', quantity=2):
        from .models import CustomerOrder, CustomerOrderItem
        from .services import allocate_order_item_stock
        order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Phase 5.2D Buyer',
            customer_email='buyer@phase52d.test', status=status,
            payment_status=payment_status, total_amount=Decimal('100.00'),
        )
        item = CustomerOrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            unit_price=Decimal('50.00'), quantity=quantity,
            line_subtotal=Decimal('50.00') * quantity,
        )
        allocate_order_item_stock(item, self.customer)
        return order, item

    def make_paid_order(self, *, status='Pending'):
        from .models import PaymentAttempt
        from .services import create_order_payment_instructions, review_payment_attempt
        order, item = self.make_order(status=status)
        instructions = create_order_payment_instructions(order)
        attempt = PaymentAttempt.objects.create(
            order=order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount,
            transaction_reference=f'PAID-{order.pk}',
            proof_image=f'private/payment-proofs/paid-{order.pk}.png',
        )
        review_payment_attempt(attempt.pk, self.reviewer, approve=True, bank_checked=True)
        attempt.refresh_from_db()
        return order, item, attempt

    def request_refund(self, order, amount):
        from .services import request_payment_refund
        return request_payment_refund(
            order.pk, amount=Decimal(str(amount)), reason='Customer refund approved.',
            actor=self.manager,
        )

    def confirm_refund(self, refund, reference='REFUND-UTR-1'):
        from .services import review_payment_refund
        return review_payment_refund(
            refund.pk, self.reviewer, confirm=True,
            manual_reference=reference, remarks='Manual UPI refund confirmed.',
        )

    def test_unpaid_cancellation_restores_stock_once_and_is_idempotent(self):
        from .models import InventoryMovement, OrderCancellation
        order, item = self.make_order()
        self.product.refresh_from_db()
        reduced_stock = self.product.stock

        self.client.force_authenticate(self.unauthorized)
        self.assertEqual(self.client.post(
            f'/api/orders/{order.pk}/cancel/', {'reason': 'Unauthorized request.'}, format='json',
        ).status_code, 403)
        self.client.force_authenticate(self.manager)
        first_response = self.client.post(
            f'/api/orders/{order.pk}/cancel/',
            {'reason': 'Customer requested cancellation.'}, format='json',
        )
        self.assertEqual(first_response.status_code, 200, first_response.data)
        first = OrderCancellation.objects.get(order=order)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, reduced_stock + item.quantity)
        self.assertEqual(order.__class__.objects.get(pk=order.pk).status, 'Cancelled')
        movement = InventoryMovement.objects.get(cancellation=first, order_item=item)
        self.assertEqual(movement.movement_type, InventoryMovement.TYPE_ORDER_RESTORATION)
        self.assertEqual(movement.direction, InventoryMovement.DIRECTION_IN)
        self.assertEqual(movement.quantity, item.quantity)
        second_response = self.client.post(
            f'/api/orders/{order.pk}/cancel/',
            {'reason': 'Retry must not replace audit.'}, format='json',
        )
        self.assertEqual(second_response.status_code, 200, second_response.data)
        second = OrderCancellation.objects.get(order=order)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(OrderCancellation.objects.filter(order=order).count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(cancellation=first).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, reduced_stock + item.quantity)

    def test_pending_attempt_blocks_cancellation_but_rejected_attempt_does_not(self):
        from .models import PaymentAttempt
        from .services import (cancel_customer_order, create_order_payment_instructions,
                               review_payment_attempt)
        order, _item = self.make_order()
        instructions = create_order_payment_instructions(order)
        attempt = PaymentAttempt.objects.create(
            order=order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference='PENDING-CANCEL',
            proof_image='private/payment-proofs/pending-cancel.png',
        )
        with self.assertRaisesRegex(ValueError, 'pending payment attempt'):
            cancel_customer_order(order.pk, self.manager, reason='Attempted cancellation.')
        review_payment_attempt(attempt.pk, self.reviewer, approve=False, remarks='Not in bank records.')
        cancel_customer_order(order.pk, self.manager, reason='Rejected payment was resolved.')
        self.assertEqual(order.__class__.objects.get(pk=order.pk).status, 'Cancelled')

    def test_paid_order_requires_full_confirmed_refund_before_cancellation(self):
        from .services import cancel_customer_order
        order, _item, attempt = self.make_paid_order()
        with self.assertRaisesRegex(ValueError, 'full verified payment'):
            cancel_customer_order(order.pk, self.manager, reason='No refund yet.')
        partial = self.request_refund(order, '40.00')
        self.confirm_refund(partial)
        with self.assertRaisesRegex(ValueError, 'full verified payment'):
            cancel_customer_order(order.pk, self.manager, reason='Partial refund is not settlement.')
        remaining = self.request_refund(order, '60.00')
        self.confirm_refund(remaining, 'REFUND-UTR-2')
        cancellation = cancel_customer_order(order.pk, self.manager, reason='Full payment refunded.')
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.status, 'Cancelled')
        self.assertEqual(order.payment_status, 'Paid')
        self.assertEqual(attempt.status, 'Verified')
        self.assertEqual(order.refunds.filter(status='Confirmed').aggregate(total=Sum('amount'))['total'], Decimal('100.00'))
        self.assertEqual(cancellation.actor_id, self.manager.pk)

    def test_refund_api_permissions_separation_and_required_confirmation_fields(self):
        order, _item, _attempt = self.make_paid_order()
        endpoint = f'/api/admin/orders/{order.pk}/refunds/'
        self.client.force_authenticate(self.unauthorized)
        self.assertEqual(self.client.post(endpoint, {'amount': '100.00', 'reason': 'Refund'}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/admin/refunds/1/confirm/', {}, format='json').status_code, 403)

        self.client.force_authenticate(self.manager)
        created = self.client.post(endpoint, {'amount': '100.00', 'reason': 'Full refund'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['source_payment']['kind'], 'Receipt')
        self.assertEqual(created.data['source_payment']['amount'], '100.00')
        self.assertEqual(created.data['source_payment']['reference'], f'PAID-{order.pk}')
        review_url = f"/api/admin/refunds/{created.data['id']}/confirm/"
        self.assertEqual(self.client.post(review_url, {'remarks': 'Self-review'}, format='json').status_code, 403)

        self.client.force_authenticate(self.reviewer)
        missing_reference = self.client.post(review_url, {'remarks': 'Checked records.'}, format='json')
        self.assertEqual(missing_reference.status_code, 400, missing_reference.data)
        missing_remarks = self.client.post(review_url, {'manual_transaction_reference': 'UTR-REFUND'}, format='json')
        self.assertEqual(missing_remarks.status_code, 400, missing_remarks.data)
        confirmed = self.client.post(review_url, {
            'manual_transaction_reference': 'UTR-REFUND', 'remarks': 'Refund transfer confirmed.',
        }, format='json')
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data['status'], 'Confirmed')

    def test_refund_amount_and_cumulative_reservations_cannot_exceed_received_amount(self):
        order, _item, _attempt = self.make_paid_order()
        with self.assertRaises(ValidationError):
            self.request_refund(order, '100.01')
        self.request_refund(order, '60.00')
        with self.assertRaises(ValidationError):
            self.request_refund(order, '40.01')

    def test_cumulative_confirmed_refunds_cannot_exceed_received_amount(self):
        order, _item, _attempt = self.make_paid_order()
        first = self.request_refund(order, '60.00')
        self.confirm_refund(first, 'CUMULATIVE-REFUND-1')
        second = self.request_refund(order, '40.00')
        self.confirm_refund(second, 'CUMULATIVE-REFUND-2')
        with self.assertRaises(ValidationError):
            self.request_refund(order, '0.01')

    def test_requester_cannot_confirm_and_confirmed_refund_retry_is_idempotent(self):
        from .services import review_payment_refund
        order, _item, attempt = self.make_paid_order()
        from .models import InventoryMovement
        movement_count = InventoryMovement.objects.filter(order=order).count()
        refund = self.request_refund(order, '100.00')
        with self.assertRaises(PermissionDenied):
            review_payment_refund(refund.pk, self.manager, confirm=True,
                                  manual_reference='SELF-UTR', remarks='Not allowed.')
        first = self.confirm_refund(refund)
        second = self.confirm_refund(refund, 'IGNORED-RETRY-REFERENCE')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(order.refunds.filter(status='Confirmed').count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(order=order).count(), movement_count)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'Paid')
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'Verified')
        self.assertEqual(attempt.transaction_reference, f'PAID-{order.pk}')
        receipt = attempt.receipt
        self.assertEqual(receipt.amount, Decimal('100.00'))
        attempt.transaction_reference = 'MUTATED'
        with self.assertRaises(ValidationError):
            attempt.save()
        receipt.amount = Decimal('1.00')
        with self.assertRaises(ValidationError):
            receipt.save()
        attempt.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(attempt.transaction_reference, f'PAID-{order.pk}')
        self.assertEqual(receipt.amount, Decimal('100.00'))

    def test_rejected_refund_is_audited_and_releases_reserved_amount(self):
        order, _item, _attempt = self.make_paid_order()
        refund = self.request_refund(order, '75.00')
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            f'/api/admin/refunds/{refund.pk}/reject/',
            {'remarks': 'Refund reference could not be verified.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'Rejected')
        self.assertEqual(response.data['reviewer_remarks'], 'Refund reference could not be verified.')
        replacement = self.request_refund(order, '100.00')
        self.assertEqual(replacement.status, 'Pending')

    def test_legacy_reconciliation_unknown_blocks_unpaid_allows_and_paid_requires_refund(self):
        from .models import CustomerOrder, OrderPaymentReconciliation
        from .services import cancel_customer_order, reconcile_order_payment
        unknown_order, _ = self.make_order(payment_status=None)
        with self.assertRaisesRegex(ValueError, 'explicitly reconciled'):
            cancel_customer_order(unknown_order.pk, self.manager, reason='Legacy order.')
        reconcile_order_payment(
            unknown_order.pk, self.manager, outcome=OrderPaymentReconciliation.OUTCOME_UNKNOWN,
            reason='Records are incomplete.', evidence_reference='LEDGER-UNKNOWN',
        )
        with self.assertRaisesRegex(ValueError, 'explicitly reconciled'):
            cancel_customer_order(unknown_order.pk, self.manager, reason='Still unresolved.')
        reconcile_order_payment(
            unknown_order.pk, self.manager, outcome=OrderPaymentReconciliation.OUTCOME_UNPAID,
            reason='No transfer found.', evidence_reference='BANK-CHECK-1',
        )
        cancel_customer_order(unknown_order.pk, self.manager, reason='Confirmed unpaid.')

        paid_legacy, _ = self.make_order(payment_status=None)
        reconcile_order_payment(
            paid_legacy.pk, self.manager, outcome=OrderPaymentReconciliation.OUTCOME_PAID,
            confirmed_amount=Decimal('100.00'), reason='Transfer verified from statement.',
            evidence_reference='BANK-LEDGER-22',
        )
        with self.assertRaisesRegex(ValueError, 'full verified payment'):
            cancel_customer_order(paid_legacy.pk, self.manager, reason='Refund is pending.')
        refund = self.request_refund(paid_legacy, '100.00')
        self.assertIsNone(refund.attempt_id)
        self.assertIsNone(refund.receipt_id)
        self.confirm_refund(refund, 'LEGACY-REFUND-UTR')
        cancel_customer_order(paid_legacy.pk, self.manager, reason='Legacy payment fully refunded.')
        paid_legacy.refresh_from_db()
        self.assertIsNone(paid_legacy.payment_status)
        self.assertEqual(paid_legacy.status, 'Cancelled')

    def test_paid_order_without_receipt_needs_reconciliation_and_documented_refund(self):
        from .models import CustomerOrder
        from .services import cancel_customer_order, reconcile_order_payment
        order, _item = self.make_order(payment_status='Paid')
        with self.assertRaisesRegex(ValueError, 'confirmed-paid reconciliation'):
            cancel_customer_order(order.pk, self.manager, reason='Receipt is missing.')
        reconcile_order_payment(
            order.pk, self.manager, outcome='Paid', confirmed_amount=Decimal('100.00'),
            reason='Bank statement confirms funds.', evidence_reference='BANK-PAID-9',
        )
        refund = self.request_refund(order, '100.00')
        self.confirm_refund(refund, 'NO-RECEIPT-REFUND-UTR')
        cancel_customer_order(order.pk, self.manager, reason='Reconciled payment refunded.')
        order.refresh_from_db()
        self.assertEqual(order.status, 'Cancelled')

    def test_shipped_and_delivered_orders_cannot_be_cancelled(self):
        from .services import cancel_customer_order
        for status in ('Shipped', 'Delivered'):
            with self.subTest(status=status):
                order, _item = self.make_order(status=status)
                with self.assertRaisesRegex(ValueError, 'cannot be cancelled'):
                    cancel_customer_order(order.pk, self.manager, reason='Not eligible.')

    def test_processing_order_can_be_cancelled_under_unpaid_rules(self):
        from .services import cancel_customer_order
        order, _item = self.make_order(status='Processing')
        event = cancel_customer_order(order.pk, self.manager, reason='Processing order cancelled.')
        self.assertEqual(event.order_id, order.pk)


    def test_cancellation_and_stock_restore_roll_back_together_on_movement_failure(self):
        from unittest.mock import patch
        from .models import CustomerOrder, InventoryMovement, OrderCancellation
        from .services import cancel_customer_order
        order, _item = self.make_order()
        self.product.refresh_from_db()
        before = self.product.stock
        with patch('store.services.InventoryMovement.objects.create',
                   side_effect=IntegrityError('simulated movement failure')):
            with self.assertRaises(IntegrityError):
                cancel_customer_order(order.pk, self.manager, reason='Rollback test.')
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'Pending')
        self.assertEqual(self.product.stock, before)
        self.assertFalse(OrderCancellation.objects.filter(order=order).exists())
        self.assertFalse(InventoryMovement.objects.filter(
            order=order, movement_type=InventoryMovement.TYPE_ORDER_RESTORATION,
        ).exists())

    def test_vendor_receiving_is_atomic_idempotent_and_received_purchase_is_immutable(self):
        from .models import InventoryMovement, Vendor, VendorPurchase
        from .services import receive_vendor_purchase
        vendor = Vendor.objects.create(name='Phase 5.2D Vendor', email='phase52d-vendor@example.test')
        purchase = VendorPurchase.objects.create(
            vendor=vendor, product=self.product, quantity=4, unit_cost='12.00', status='Approved',
        )
        initial = self.product.stock
        received = receive_vendor_purchase(purchase.pk, self.inventory)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial + 4)
        self.assertEqual(received.received_by_id, self.inventory.pk)
        self.assertEqual(InventoryMovement.objects.filter(vendor_purchase=purchase).count(), 1)
        with self.assertRaisesRegex(ValueError, 'already been received'):
            receive_vendor_purchase(purchase.pk, self.inventory)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial + 4)
        purchase.quantity = 9
        with self.assertRaises(ValidationError):
            purchase.save()
        with self.assertRaises(ValidationError):
            VendorPurchase.objects.filter(pk=purchase.pk).update(quantity=9)

        self.inventory.user_permissions.add(Permission.objects.get(
            content_type__app_label='store', codename='change_vendorpurchase',
        ))
        self.inventory = User.objects.get(pk=self.inventory.pk)
        self.client.force_authenticate(self.inventory)
        edit = self.client.patch(f'/api/vendor-purchases/{purchase.pk}/', {'quantity': 9}, format='json')
        self.assertEqual(edit.status_code, 400, edit.data)

    def test_vendor_stock_and_receipt_roll_back_if_purchase_transition_fails(self):
        from unittest.mock import patch
        from .models import Vendor, VendorPurchase, InventoryMovement
        from .services import receive_vendor_purchase
        vendor = Vendor.objects.create(name='Rollback Vendor', email='rollback-vendor@example.test')
        purchase = VendorPurchase.objects.create(
            vendor=vendor, product=self.product, quantity=3, unit_cost='12.00', status='Approved',
        )
        before = self.product.stock
        with patch.object(VendorPurchase, 'save', side_effect=RuntimeError('simulated receive failure')):
            with self.assertRaisesRegex(RuntimeError, 'simulated receive failure'):
                receive_vendor_purchase(purchase.pk, self.inventory)
        purchase.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(purchase.status, 'Approved')
        self.assertEqual(self.product.stock, before)
        self.assertFalse(InventoryMovement.objects.filter(vendor_purchase=purchase).exists())

    def test_inventory_adjustment_and_stock_guards(self):
        from .models import CustomerOrderItem, InventoryMovement, Product
        from .services import adjust_product_stock, allocate_order_item_stock
        self.client.force_authenticate(self.unauthorized)
        denied = self.client.patch(f'/api/products/{self.product.pk}/', {
            'stock': 31, 'stock_reason': 'Unauthorized.',
        }, format='json')
        self.assertEqual(denied.status_code, 403)
        self.client.force_authenticate(self.inventory)
        source_key = 'phase52d-manual-stock-adjustment'
        payload = {'stock': 25, 'stock_reason': 'Verified cycle count.', 'stock_source_key': source_key}
        changed = self.client.patch(f'/api/products/{self.product.pk}/', payload, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        retry = self.client.patch(f'/api/products/{self.product.pk}/', payload, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(InventoryMovement.objects.filter(source_key=source_key).count(), 1)
        with self.assertRaises(ValidationError):
            Product.objects.filter(pk=self.product.pk).update(stock=999)
        product = Product.objects.get(pk=self.product.pk)
        product.stock = 24
        with self.assertRaises(ValidationError):
            product.save(update_fields=['stock'])
        with self.assertRaises(ValidationError):
            adjust_product_stock(self.product.pk, target_stock=-1, actor=self.inventory,
                                 reason='Invalid quantity.')
        self.assertEqual(adjust_product_stock(self.product.pk, target_stock=25,
                                              actor=self.inventory, reason='No change.'), None)

        order, _item = self.make_order()
        zero_quantity_item = CustomerOrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            unit_price=Decimal('50.00'), quantity=0, line_subtotal=Decimal('0.00'),
        )
        with self.assertRaises(ValidationError):
            allocate_order_item_stock(zero_quantity_item, self.customer)
        self.assertFalse(InventoryMovement.objects.filter(order_item=zero_quantity_item).exists())

    def test_allocation_rejects_insufficient_stock_without_negative_balance(self):
        from .models import CustomerOrder, CustomerOrderItem, InventoryMovement
        from .services import allocate_order_item_stock, adjust_product_stock
        adjust_product_stock(
            self.product.pk, target_stock=0, actor=self.inventory,
            reason='Prepare zero-stock guard.',
        )
        order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Insufficient stock order',
            total_amount='50.00',
        )
        item = CustomerOrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            unit_price='50.00', quantity=1, line_subtotal='50.00',
        )
        with self.assertRaises(ValidationError):
            allocate_order_item_stock(item, self.customer)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertFalse(InventoryMovement.objects.filter(order_item=item).exists())

    def test_reconciliation_api_is_permission_controlled_and_requires_evidence(self):
        from .models import CustomerOrder
        order = CustomerOrder.objects.create(
            customer=None, customer_name='Legacy API Order',
            payment_status=None, total_amount='25.00',
        )
        url = f'/api/admin/orders/{order.pk}/payment-reconciliation/'
        data = {'outcome': 'Unpaid', 'reason': 'Checked records.', 'evidence_reference': 'BANK-REF'}
        self.client.force_authenticate(self.unauthorized)
        self.assertEqual(self.client.post(url, data, format='json').status_code, 403)
        self.client.force_authenticate(self.manager)
        response = self.client.post(url, {**data, 'evidence_reference': ''}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['outcome'], 'Unpaid')


class ReportingApiTests(APITestCase):
    def setUp(self):
        from .models import Category, CustomerOrder, PaymentConfiguration, Product, Vendor
        self.staff = User.objects.create_user(username='report-staff', password='test-password', is_staff=True)
        self.customer = User.objects.create_user(username='report-customer', password='test-password', first_name='Report', last_name='Buyer', email='buyer@reports.test')
        self.unlinked_order = CustomerOrder.objects.create(customer=None, customer_name='Legacy Named Buyer', payment_status=None, total_amount='15.00')
        self.category = Category.objects.create(name='Report Chairs')
        self.product = Product.objects.create(name='Available Chair', category=self.category, price='40.00', stock=5, is_active=True)
        self.vendor = Vendor.objects.create(name='Report Vendor', email='vendor@reports.test')
        self.configuration = PaymentConfiguration.objects.create(display_name='Report Showroom', upi_id='reports@upi', qr_image='private/payment-config/qr/report.png', active_slot=1)
        self.report_permission = Permission.objects.get(content_type__app_label='store', codename='view_reports')
        self.review_permission = Permission.objects.get(content_type__app_label='store', codename='verify_payment')
        self.staff.user_permissions.add(
            self.report_permission, self.review_permission,
            Permission.objects.get(content_type__app_label='store', codename='cancel_customerorder'),
        )
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)

    def make_order(self, amount, *, customer=None, status='Pending', payment='Pending', created_at=None):
        from .models import CustomerOrder
        from django.utils import timezone
        requested_status = status
        order = CustomerOrder.objects.create(customer=customer, customer_name=(customer.get_full_name() or customer.username) if customer else 'Unlinked record',
            customer_email=customer.email if customer else '',
            status='Pending' if status == 'Cancelled' else status,
            payment_status=payment, total_amount=amount)
        if requested_status == 'Cancelled':
            from .services import cancel_customer_order
            cancel_customer_order(order.pk, self.staff, reason='Reporting fixture cancellation.')
            order.refresh_from_db()
        if created_at:
            CustomerOrder.objects.filter(pk=order.pk).update(created_at=created_at)
            order.refresh_from_db()
        return order

    def make_verified_order(self, amount='100.00'):
        from .models import CustomerOrder, PaymentAttempt
        from .services import create_order_payment_instructions, review_payment_attempt
        order = self.make_order(amount, customer=self.customer)
        instructions = create_order_payment_instructions(order)
        attempt = PaymentAttempt.objects.create(order=order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference=f'RPT-{order.pk}',
            proof_image=f'private/payment-proofs/report-{order.pk}.png')
        review_payment_attempt(attempt.pk, self.staff, approve=True, bank_checked=True)
        return order, attempt

    def test_permission_boundaries_and_payment_report_needs_both_permissions(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/admin/reports/summary/').status_code, 401)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/admin/reports/summary/').status_code, 403)
        self.client.force_authenticate(self.staff)
        self.staff.user_permissions.remove(self.review_permission)
        self.staff.user_permissions.remove(self.report_permission)
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/reports/inventory/').status_code, 403)
        self.staff.user_permissions.add(self.report_permission)
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/reports/inventory/').status_code, 200)
        self.assertEqual(self.client.get('/api/admin/reports/payment-verification/').status_code, 403)

    def test_sales_metrics_cancelled_verified_pending_rejected_and_unreceipted(self):
        from .models import CustomerOrder
        from .services import review_payment_attempt
        from .models import PaymentAttempt
        self.make_order('50.00', customer=self.customer)
        self.make_order('30.00', customer=self.customer, status='Cancelled')
        self.make_verified_order('100.00')
        self.make_order('200.00', customer=self.customer, payment='Paid')
        rejected_order = self.make_order('70.00', customer=self.customer)
        from .services import create_order_payment_instructions
        instructions = create_order_payment_instructions(rejected_order)
        attempt = PaymentAttempt.objects.create(order=rejected_order, customer=self.customer, instructions=instructions,
            expected_amount=instructions.expected_amount, transaction_reference='RPT-REJECTED', proof_image='private/payment-proofs/rejected.png')
        review_payment_attempt(attempt.pk, self.staff, approve=False, remarks='Not present in bank records.')
        response = self.client.get('/api/admin/reports/summary/')
        self.assertEqual(response.status_code, 200, response.data)
        metrics = response.data['metrics']
        self.assertEqual(metrics['order_count'], 5)
        self.assertEqual(metrics['order_value'], Decimal('435.00'))
        self.assertEqual(metrics['cancelled_order_count'], 1)
        self.assertEqual(metrics['cancelled_order_value'], Decimal('30.00'))
        self.assertEqual(metrics['verified_revenue'], Decimal('100.00'))
        self.assertEqual(metrics['pending_payment_value'], Decimal('120.00'))
        self.assertEqual(metrics['paid_orders_without_receipts_count'], 1)
        self.assertEqual(metrics['paid_orders_without_receipts_value'], Decimal('200.00'))
        self.assertEqual(metrics['rejected_payment_attempt_count'], 1)
        daily = self.client.get('/api/admin/reports/sales/').data['daily']['results']
        self.assertTrue(any(row['verified_revenue'] == Decimal('100.00') for row in daily))

    def test_sales_reports_keep_gross_verified_revenue_and_add_confirmed_refunds(self):
        order, _attempt = self.make_verified_order('100.00')
        self.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='store', codename='confirm_refund',
        ))
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        requester = User.objects.create_user(username='report-refund-requester', password='test-password', is_staff=True)
        requester.user_permissions.add(Permission.objects.get(
            content_type__app_label='store', codename='request_refund',
        ))
        requester = User.objects.get(pk=requester.pk)
        from .services import request_payment_refund, review_payment_refund
        refund = request_payment_refund(
            order.pk, amount=Decimal('35.00'), reason='Report refund.', actor=requester,
        )
        review_payment_refund(
            refund.pk, self.staff, confirm=True,
            manual_reference='REPORT-REFUND-UTR', remarks='Refund verified for report.',
        )

        metrics = self.client.get('/api/admin/reports/summary/').data['metrics']
        self.assertEqual(metrics['verified_revenue'], Decimal('100.00'))
        self.assertEqual(metrics['confirmed_refunds'], Decimal('35.00'))
        self.assertEqual(metrics['net_verified_revenue'], Decimal('65.00'))
        daily = self.client.get('/api/admin/reports/sales/').data['daily']['results']
        self.assertTrue(any(
            row['verified_revenue'] == Decimal('100.00')
            and row['confirmed_refunds'] == Decimal('35.00')
            and row['net_verified_revenue'] == Decimal('65.00')
            for row in daily
        ))

        export = self.client.get('/api/admin/reports/sales/export/', {'format': 'csv'})
        self.assertEqual(export.status_code, 200)
        body = b''.join(export.streaming_content).decode('utf-8-sig')
        self.assertIn('Gross verified payments (INR)', body)
        self.assertIn('Confirmed refunds (INR)', body)
        self.assertIn('Net verified payments (INR)', body)
        self.assertIn('35.00', body)
        self.assertIn('65.00', body)

    def test_orders_search_filters_date_boundaries_and_server_pagination(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import CustomerOrderItem
        today = timezone.localdate()
        start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        in_range = self.make_order('90.00', customer=self.customer, created_at=start)
        CustomerOrderItem.objects.create(order=in_range, product=self.product, product_name='Snapshot Chair', unit_price='45.00', quantity=2, line_subtotal='90.00')
        self.make_order('12.00', customer=self.customer, created_at=start - timedelta(days=40))
        response = self.client.get('/api/admin/reports/orders/', {'date_from': today.isoformat(), 'date_to': today.isoformat(), 'search': 'Snapshot', 'page_size': '1'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['items'][0]['product_name'], 'Snapshot Chair')
        self.assertTrue(response.data['results'][0]['linked_account'])
        self.assertNotIn('shipping_address', response.data['results'][0])

    def test_inventory_low_stock_threshold_search_and_empty_results(self):
        from .models import Product
        Product.objects.create(name='Above Threshold', category=self.category, price='20.00', stock=6, is_active=True)
        low = self.client.get('/api/admin/reports/low-stock/').data
        self.assertEqual(low['threshold'], 5)
        self.assertEqual([row['product'] for row in low['results']], ['Available Chair'])
        self.assertIsNone(low['results'][0]['reorder_recommendation'])
        inventory = self.client.get('/api/admin/reports/inventory/', {'search': 'Above'}).data
        self.assertEqual(inventory['count'], 1)
        empty = self.client.get('/api/admin/reports/inventory/', {'search': 'no matching item'}).data
        self.assertEqual(empty['results'], [])

    def test_customer_report_only_linked_accounts_and_uses_receipts(self):
        self.make_order('22.00', customer=self.customer)
        self.make_verified_order('100.00')
        response = self.client.get('/api/admin/reports/customers/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['customer_id'], self.customer.pk)
        self.assertEqual(row['order_count'], 2)
        self.assertEqual(row['pending_order_value'], Decimal('22.00'))
        self.assertEqual(row['verified_payment_total'], Decimal('100.00'))
        self.assertEqual(row['email'], 'buyer@reports.test')

    def test_vendor_purchase_values_filters_and_payment_report_fields(self):
        from .models import VendorPurchase
        from .services import receive_vendor_purchase
        self.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='store', codename='receive_vendorpurchase',
        ))
        self.staff = User.objects.get(pk=self.staff.pk)
        purchase = VendorPurchase.objects.create(
            vendor=self.vendor, product=self.product, quantity=3, unit_cost='12.50', status='Approved',
        )
        receive_vendor_purchase(purchase.pk, self.staff)
        data = self.client.get('/api/admin/reports/vendor-purchases/', {'status': 'Received'}).data
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['purchase_value'], Decimal('37.50'))
        self.assertEqual(data['summary_by_vendor'][0]['purchase_value'], Decimal('37.50'))
        attempt_order, attempt = self.make_verified_order()
        payment = self.client.get('/api/admin/reports/payment-verification/', {'status': 'Verified'}).data
        self.assertEqual(payment['count'], 1)
        row = payment['results'][0]
        self.assertEqual(row['attempt_id'], attempt.pk)
        self.assertEqual(row['order_reference'], str(attempt_order.order_reference))
        self.assertEqual(row['transaction_reference'], attempt.transaction_reference)
        self.assertNotIn('proof_image', row)
        self.assertNotIn('proof_url', row)

    def test_validation_default_range_and_page_limits(self):
        from datetime import timedelta
        from django.utils import timezone
        bad_dates = self.client.get('/api/admin/reports/orders/', {'date_from': '2026-02-30'})
        self.assertEqual(bad_dates.status_code, 400)
        reversed_range = self.client.get('/api/admin/reports/orders/', {'date_from': '2026-11-02', 'date_to': '2026-11-01'})
        self.assertEqual(reversed_range.status_code, 400)
        too_large = self.client.get('/api/admin/reports/inventory/', {'page_size': 101})
        self.assertEqual(too_large.status_code, 400)
        invalid_status = self.client.get('/api/admin/reports/payment-verification/', {'status': 'unknown'})
        self.assertEqual(invalid_status.status_code, 400)
        default_range = self.client.get('/api/admin/reports/summary/').data['date_range']
        self.assertEqual(default_range['date_from'], (timezone.localdate() - timedelta(days=29)).isoformat())

    def test_order_report_avoids_n_plus_one_item_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from .models import CustomerOrderItem
        orders = [self.make_order('5.00', customer=self.customer) for _ in range(6)]
        for order in orders:
            CustomerOrderItem.objects.create(order=order, product=self.product, product_name='Chair', unit_price='5.00', quantity=1, line_subtotal='5.00')
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/api/admin/reports/orders/', {'page_size': 10})
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(captured), 7)


class ReportingExportTests(APITestCase):
    def setUp(self):
        from .models import Category, CustomerOrder, Product
        self.staff = User.objects.create_user(username='export-staff', password='test-password', is_staff=True)
        self.customer = User.objects.create_user(username='export-customer', password='test-password', email='export@example.test')
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='view_reports'))
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='verify_payment'))
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='cancel_customerorder'))
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.category = Category.objects.create(name='Export category')
        self.product = Product.objects.create(name='Export chair', category=self.category, price='75.00', stock=3)
        self.order = CustomerOrder.objects.create(customer=self.customer, customer_name='=1+1',
            customer_email=self.customer.email, shipping_address='PRIVATE DELIVERY ADDRESS', total_amount='75.00')

    def stream_bytes(self, response):
        return b''.join(response.streaming_content) if getattr(response, 'streaming', False) else response.content

    def test_csv_has_safe_headers_filename_filters_and_formula_protection(self):
        url = '/api/admin/reports/orders/export/'
        response = self.client.get(url, {'format': 'csv', 'search': '=1+1', 'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('orders_report_', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        body = self.stream_bytes(response).decode('utf-8-sig')
        self.assertIn('Order reference,Customer,Linked account', body)
        self.assertIn("'=1+1", body)
        self.assertNotIn('PRIVATE DELIVERY ADDRESS', body)
        self.assertEqual(body.count('\r\n'), 2)

    def test_csv_formula_guard_handles_whitespace_prefix_and_numeric_values(self):
        from .report_exports import _safe_csv_text
        for value in ('=1+1', '+SUM(A1:A2)', '-2+3', '@SUM(A1:A2)',
                      '  =1+1', '\t+SUM(A1:A2)', '\n-2+3', '\r\t@SUM(A1:A2)', '\u00a0=1+1'):
            with self.subTest(value=value):
                self.assertEqual(_safe_csv_text(value), "'" + value)
        self.assertEqual(_safe_csv_text('ordinary text'), 'ordinary text')
        self.assertEqual(_safe_csv_text(Decimal('-12.50')), '-12.50')

        from .report_exports import _csv_response
        response = _csv_response('orders', [{
            'order_reference': 'ORD-1', 'customer_name': '-Customer', 'linked_account': True,
            'created_at': None, 'item_summary': 'Chair', 'total_amount': Decimal('-12.50'),
            'payment_status': 'Pending', 'fulfillment_status': 'Pending',
        }], 1)
        csv_body = b''.join(response.streaming_content).decode('utf-8-sig')
        self.assertIn("'-Customer", csv_body)
        self.assertIn(',-12.50,', csv_body)

    def test_pdf_is_valid_attachment_and_dynamic_text_is_not_reportlab_markup(self):
        from .models import CustomerOrder
        CustomerOrder.objects.create(
            customer=self.customer, customer_name='<b>Buyer</b> & Co',
            customer_email=self.customer.email, shipping_address='PRIVATE DELIVERY ADDRESS',
            total_amount='1.00',
        )
        response = self.client.get('/api/admin/reports/orders/export/', {'format': 'pdf'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        payload = response.content
        self.assertTrue(payload.startswith(b'%PDF-'))
        self.assertTrue(payload.rstrip().endswith(b'%%EOF'))
        # Escaped content is shown as text; it cannot create rich-text markup.
        self.assertNotIn(b'<b>Buyer</b>', payload)
        self.assertNotIn(b'PRIVATE DELIVERY ADDRESS', payload)

    def test_export_endpoints_cover_all_seven_reports(self):
        paths = ('sales', 'orders', 'inventory', 'low-stock', 'customers', 'vendor-purchases', 'payment-verification')
        for name in paths:
            for file_format in ('csv', 'pdf'):
                with self.subTest(report=name, format=file_format):
                    response = self.client.get(f'/api/admin/reports/{name}/export/', {'format': file_format})
                    self.assertEqual(response.status_code, 200, getattr(response, 'data', None))

    def test_export_query_filters_and_pagination_parameters(self):
        from .models import Category, CustomerOrder, Product, Vendor, VendorPurchase
        other_category = Category.objects.create(name='Another category')
        Product.objects.create(name='Inactive table', category=other_category, price='120.00', stock=1, is_active=False)
        Product.objects.create(name='Active table', category=other_category, price='140.00', stock=1, is_active=True)
        inventory = self.client.get('/api/admin/reports/inventory/export/', {
            'format': 'csv', 'category_id': other_category.pk, 'active': 'false', 'page': 99, 'page_size': 1,
        })
        self.assertEqual(inventory.status_code, 200)
        inventory_csv = self.stream_bytes(inventory).decode('utf-8-sig')
        self.assertIn('Inactive table', inventory_csv)
        self.assertNotIn('Active table', inventory_csv)

        legacy = CustomerOrder.objects.create(customer=None, customer_name='Legacy NULL payment',
            payment_status=None, total_amount='18.00')
        orders = self.client.get('/api/admin/reports/orders/export/', {
            'format': 'csv', 'payment_status': 'unrecorded', 'search': 'Legacy NULL',
            'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat(),
            'page': 99, 'page_size': 1,
        })
        self.assertEqual(orders.status_code, 200)
        orders_csv = self.stream_bytes(orders).decode('utf-8-sig')
        self.assertIn('Legacy NULL payment', orders_csv)
        self.assertNotIn(self.order.customer_name, orders_csv)

        low_stock = self.client.get('/api/admin/reports/low-stock/export/', {
            'format': 'csv', 'category_id': self.category.pk, 'active': 'true',
        })
        self.assertEqual(low_stock.status_code, 200)
        low_stock_csv = self.stream_bytes(low_stock).decode('utf-8-sig')
        self.assertIn('Export chair', low_stock_csv)
        self.assertNotIn('Inactive table', low_stock_csv)

        customers = self.client.get('/api/admin/reports/customers/export/', {
            'format': 'csv', 'search': 'export-customer',
            'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat(),
        })
        self.assertEqual(customers.status_code, 200)
        customer_csv = self.stream_bytes(customers).decode('utf-8-sig')
        self.assertIn('export@example.test', customer_csv)
        self.assertNotIn('Legacy NULL payment', customer_csv)

        vendor = Vendor.objects.create(name='Filtered vendor', email='filtered-vendor@example.test')
        other_vendor = Vendor.objects.create(name='Other vendor', email='other-vendor@example.test')
        matching_purchase = VendorPurchase.objects.create(vendor=vendor, product=self.product,
            quantity=2, unit_cost='12.50', status='Requested')
        VendorPurchase.objects.create(vendor=other_vendor, product=self.product,
            quantity=1, unit_cost='10.00', status='Approved')
        purchases = self.client.get('/api/admin/reports/vendor-purchases/export/', {
            'format': 'csv', 'vendor_id': vendor.pk, 'status': 'Requested', 'search': 'Export chair',
            'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat(),
        })
        self.assertEqual(purchases.status_code, 200)
        purchase_csv = self.stream_bytes(purchases).decode('utf-8-sig')
        self.assertIn('Filtered vendor', purchase_csv)
        self.assertIn(str(matching_purchase.pk), purchase_csv)
        self.assertNotIn('Other vendor', purchase_csv)

    def test_exports_ignore_api_pagination_and_return_the_full_filtered_set(self):
        import csv
        import io
        from .models import CustomerOrder
        CustomerOrder.objects.create(customer=self.customer, customer_name='Second export row', total_amount='11.00')
        CustomerOrder.objects.create(customer=self.customer, customer_name='Third export row', total_amount='12.00')
        response = self.client.get('/api/admin/reports/orders/export/', {
            'format': 'csv', 'date_from': timezone.localdate().isoformat(),
            'date_to': timezone.localdate().isoformat(), 'page': 99, 'page_size': 1,
        })
        self.assertEqual(response.status_code, 200)
        csv_rows = list(csv.DictReader(io.StringIO(self.stream_bytes(response).decode('utf-8-sig'))))
        self.assertEqual(len(csv_rows), 3)

    def test_sales_csv_matches_json_daily_financial_definitions(self):
        import csv
        import io
        from .models import CustomerOrder, PaymentAttempt, PaymentConfiguration
        from .services import create_order_payment_instructions, review_payment_attempt

        configuration = PaymentConfiguration.objects.create(
            display_name='Audit Showroom', upi_id='audit@upi',
            qr_image='private/payment-config/qr/audit.png', active_slot=1,
        )

        def make_attempt(order, reference):
            instructions = create_order_payment_instructions(order)
            return PaymentAttempt.objects.create(
                order=order, customer=self.customer, instructions=instructions,
                expected_amount=instructions.expected_amount, transaction_reference=reference,
                proof_image=f'private/payment-proofs/{reference}.png',
            )

        verified = make_attempt(self.order, 'AUDIT-VERIFIED')
        review_payment_attempt(verified.pk, self.staff, approve=True, bank_checked=True)
        rejected_order = CustomerOrder.objects.create(customer=self.customer, customer_name='Rejected Buyer', total_amount='40.00')
        rejected = make_attempt(rejected_order, 'AUDIT-REJECTED')
        review_payment_attempt(rejected.pk, self.staff, approve=False, remarks='Not found in records.')
        cancelled_order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Cancelled Buyer', total_amount='10.00',
        )
        from .services import cancel_customer_order
        cancel_customer_order(cancelled_order.pk, self.staff, reason='Reporting fixture cancellation.')
        CustomerOrder.objects.create(customer=self.customer, customer_name='Unreceipted Paid Buyer',
            payment_status='Paid', total_amount='12.00')

        date_params = {'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat()}
        api_daily = self.client.get('/api/admin/reports/sales/', date_params)
        self.assertEqual(api_daily.status_code, 200)
        expected = api_daily.data['daily']['results'][0]
        export = self.client.get('/api/admin/reports/sales/export/', {**date_params, 'format': 'csv'})
        self.assertEqual(export.status_code, 200)
        sales_csv_body = self.stream_bytes(export).decode('utf-8-sig')
        row = next(csv.DictReader(io.StringIO(sales_csv_body)))
        self.assertEqual(int(row['Orders']), expected['order_count'])
        self.assertEqual(Decimal(row['Order value (INR)']), expected['order_value'])
        self.assertEqual(int(row['Cancelled orders']), expected['cancelled_order_count'])
        self.assertEqual(Decimal(row['Cancelled value (INR)']), expected['cancelled_order_value'])
        self.assertEqual(Decimal(row['Pending payment value (INR)']), expected['pending_payment_value'])
        self.assertEqual(Decimal(row['Gross verified payments (INR)']), expected['verified_revenue'])
        self.assertEqual(int(row['Rejected attempts']), expected['rejected_attempt_count'])
        self.assertEqual(expected['verified_revenue'], Decimal('75.00'))
        self.assertEqual(expected['rejected_attempt_count'], 1)

        payment_csv = self.client.get('/api/admin/reports/payment-verification/export/', {
            **date_params, 'format': 'csv', 'status': 'Verified', 'search': 'AUDIT-VERIFIED',
        })
        payment_csv_body = self.stream_bytes(payment_csv).decode('utf-8-sig')
        self.assertEqual(payment_csv.status_code, 200)
        self.assertIn('AUDIT-VERIFIED', payment_csv_body)
        self.assertNotIn('private/payment-proofs', payment_csv_body)
        self.assertNotIn('PRIVATE DELIVERY ADDRESS', payment_csv_body)
        rejected_csv = self.client.get('/api/admin/reports/payment-verification/export/', {
            **date_params, 'format': 'csv', 'status': 'Rejected', 'review_action': 'Rejected',
            'search': 'AUDIT-REJECTED',
        })
        self.assertEqual(rejected_csv.status_code, 200)
        rejected_csv_body = self.stream_bytes(rejected_csv).decode('utf-8-sig')
        self.assertIn('Not found in records.', rejected_csv_body)
        self.assertNotIn('private/payment-proofs', rejected_csv_body)
        payment_pdf = self.client.get('/api/admin/reports/payment-verification/export/', {
            **date_params, 'format': 'pdf', 'status': 'Verified',
        })
        self.assertEqual(payment_pdf.status_code, 200)
        self.assertNotIn(b'private/payment-proofs', payment_pdf.content)
        self.assertNotIn(b'PRIVATE DELIVERY ADDRESS', payment_pdf.content)

        csv_rows = list(csv.DictReader(io.StringIO(sales_csv_body)))
        summary_row = next(row for row in csv_rows if row['Record type'].startswith('Period summary'))
        summary_api = self.client.get('/api/admin/reports/summary/', date_params).data['metrics']
        self.assertEqual(int(summary_row['Orders']), summary_api['order_count'])
        self.assertEqual(Decimal(summary_row['Order value (INR)']), summary_api['order_value'])
        self.assertEqual(int(summary_row['Paid orders without receipts']), summary_api['paid_orders_without_receipts_count'])
        self.assertEqual(Decimal(summary_row['Paid orders without receipts value (INR)']), summary_api['paid_orders_without_receipts_value'])

    def test_permissions_and_payment_export_requires_both_permissions(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/admin/reports/orders/export/').status_code, 401)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/admin/reports/orders/export/').status_code, 403)
        self.staff.user_permissions.remove(Permission.objects.get(content_type__app_label='store', codename='view_reports'))
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/reports/inventory/export/').status_code, 403)
        self.assertEqual(self.client.get('/api/admin/reports/payment-verification/export/').status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='store', codename='view_reports'))
        self.staff.user_permissions.remove(Permission.objects.get(content_type__app_label='store', codename='verify_payment'))
        self.staff = User.objects.get(pk=self.staff.pk)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/reports/payment-verification/export/').status_code, 403)

    def test_invalid_format_and_export_row_limits(self):
        from unittest.mock import patch
        bad = self.client.get('/api/admin/reports/orders/export/', {'format': 'xlsx'})
        self.assertEqual(bad.status_code, 400)
        with patch('store.report_exports._rows_for', return_value=([], 10000, None, None, None, {})):
            csv_at_limit = self.client.get('/api/admin/reports/orders/export/', {'format': 'csv'})
            self.assertEqual(csv_at_limit.status_code, 200)
        with patch('store.report_exports._rows_for', return_value=([], 2000, None, None, None, {})):
            pdf_at_limit = self.client.get('/api/admin/reports/orders/export/', {'format': 'pdf'})
            self.assertEqual(pdf_at_limit.status_code, 200)
        with patch('store.report_exports._rows_for', return_value=([{}] * 10001, 10001, None, None, None, {})):
            csv_limit = self.client.get('/api/admin/reports/orders/export/', {'format': 'csv'})
            self.assertEqual(csv_limit.status_code, 400)
        with patch('store.report_exports._rows_for', return_value=([{}] * 2001, 2001, None, None, None, {})):
            pdf_limit = self.client.get('/api/admin/reports/orders/export/', {'format': 'pdf'})
            self.assertEqual(pdf_limit.status_code, 400)

    def test_pdf_markup_wrapping_repeated_headers_and_page_numbers(self):
        import base64
        import zlib
        from .report_exports import _pdf_response

        rows = [{
            'order_reference': f'ORD-{index}', 'customer_name': '<script>alert("x")</script> & <b>literal</b>',
            'linked_account': True, 'created_at': None, 'item_summary': 'long text ' * 140,
            'total_amount': Decimal('20.00'), 'payment_status': 'Pending', 'fulfillment_status': 'Pending',
        } for index in range(45)]
        for row in rows:
            row['item_summary'] = 'long text ' * 35
        payload = _pdf_response('orders', rows, len(rows)).content
        self.assertTrue(payload.startswith(b'%PDF-'))
        page_count = payload.count(b'/Type /Page ') + payload.count(b'/Type /Page\n')
        self.assertGreater(page_count, 1)

        decoded_streams = []
        cursor = 0
        while True:
            stream_start = payload.find(b'stream\n', cursor)
            if stream_start < 0:
                break
            data_start = stream_start + len(b'stream\n')
            stream_end = payload.find(b'endstream', data_start)
            if stream_end < 0:
                break
            dictionary_start = payload.rfind(b'<<', 0, stream_start)
            dictionary = payload[dictionary_start:stream_start]
            encoded = payload[data_start:stream_end].rstrip(b'\r\n')
            if b'/ASCII85Decode' in dictionary and b'/FlateDecode' in dictionary:
                decoded_streams.append(zlib.decompress(base64.a85decode(encoded, adobe=True)))
            cursor = stream_end + len(b'endstream')
        text_stream = b' '.join(decoded_streams)
        self.assertGreater(page_count, 1)
        self.assertGreaterEqual(text_stream.count(b'Order reference'), page_count)
        self.assertIn(b'Page 1 of ', text_stream)
        self.assertIn(b'Page 2 of ', text_stream)
        # ReportLab may split Paragraph text across multiple PDF text operators;
        # these tokens demonstrate markup-like content was emitted as text.
        self.assertIn(b'(script)', text_stream)
        self.assertIn(b'(alert', text_stream)
        self.assertIn(b'(literal)', text_stream)
        self.assertIn(b'&', text_stream)
