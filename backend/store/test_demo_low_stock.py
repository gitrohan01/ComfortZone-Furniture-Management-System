from django.contrib.auth.models import Permission, User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Category, InventoryMovement, Product


class DemoLowStockTests(TestCase):
    def setUp(self):
        self.inventory_manager = User.objects.create_user(
            username='low-stock-inventory', password='test-password', is_staff=True,
        )
        self.inventory_manager.user_permissions.add(
            Permission.objects.get(content_type__app_label='store', codename='adjust_stock'),
        )
        self.report_user = User.objects.create_user(
            username='low-stock-reports', password='test-password', is_staff=True,
        )
        self.report_user.user_permissions.add(
            Permission.objects.get(content_type__app_label='store', codename='view_reports'),
        )
        category = Category.objects.create(name='Low stock test furniture')
        self.products = {
            'Demo Oak Lounge Chair': Product.objects.create(
                name='Demo Oak Lounge Chair', category=category, price='100.00', stock=12,
                demo_key='demo:product:demo-oak-lounge-chair',
            ),
            'Demo Teak Two-Seater Sofa': Product.objects.create(
                name='Demo Teak Two-Seater Sofa', category=category, price='200.00', stock=12,
                demo_key='demo:product:demo-teak-two-seater-sofa',
            ),
        }
        self.unrelated = Product.objects.create(
            name='Unrelated test table', category=category, price='300.00', stock=12,
        )

    def test_seed_adjustment_is_idempotent_and_reports_and_exports_real_stock(self):
        from .management.commands.seed_demo_data import Command

        Command._seed_low_stock(self.products, self.inventory_manager)
        first_movement_count = InventoryMovement.objects.count()
        Command._seed_low_stock(self.products, self.inventory_manager)

        self.assertEqual(InventoryMovement.objects.count(), first_movement_count)
        for product_name, expected_stock in (
            ('Demo Oak Lounge Chair', 1),
            ('Demo Teak Two-Seater Sofa', 2),
        ):
            product = self.products[product_name]
            product.refresh_from_db()
            self.assertTrue(product.is_active)
            self.assertEqual(product.stock, expected_stock)
            movement = InventoryMovement.objects.filter(product=product).latest('pk')
            self.assertEqual(movement.resulting_stock, product.stock)
            self.assertEqual(movement.reason, 'Seeded low-stock demo record for inventory reporting.')

        client = APIClient()
        client.force_authenticate(user=self.report_user)
        report = client.get('/api/admin/reports/low-stock/')
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['threshold'], 5)
        self.assertEqual(
            {row['product'] for row in report.data['results']},
            {'Demo Oak Lounge Chair', 'Demo Teak Two-Seater Sofa'},
        )
        self.assertEqual(self.unrelated.stock, 12)

        csv_export = client.get('/api/admin/reports/low-stock/export/?format=csv')
        self.assertEqual(csv_export.status_code, 200)
        self.assertIn('text/csv', csv_export['Content-Type'])
        csv_content = b''.join(csv_export.streaming_content).decode('utf-8')
        self.assertIn('Demo Oak Lounge Chair', csv_content)
        self.assertIn('Demo Teak Two-Seater Sofa', csv_content)

        pdf_export = client.get('/api/admin/reports/low-stock/export/?format=pdf')
        self.assertEqual(pdf_export.status_code, 200)
        self.assertEqual(pdf_export['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_export.content.startswith(b'%PDF'))

    def test_seed_catalog_reuses_demo_product_after_a_ui_name_change(self):
        from .management.commands.seed_demo_data import Command

        _, _, products = Command._seed_catalog(self.inventory_manager)
        original_product = products['Demo Oak Lounge Chair']
        original_id = original_product.pk
        original_product.name = 'Renamed showroom chair'
        original_product.save(update_fields=['name'])

        _, _, reseeded_products = Command._seed_catalog(self.inventory_manager)

        self.assertEqual(reseeded_products['Demo Oak Lounge Chair'].pk, original_id)
        self.assertEqual(reseeded_products['Demo Oak Lounge Chair'].name, 'Renamed showroom chair')
        self.assertEqual(Product.objects.filter(demo_key__isnull=False).count(), len(reseeded_products))
