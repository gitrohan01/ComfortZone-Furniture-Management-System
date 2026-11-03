import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models.query import QuerySet
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import CustomerOrder, OrderPaymentInstructions, PaymentAttempt, PaymentConfiguration
from .services import create_order_payment_instructions
from .storage import (
    MAX_PAYMENT_IMAGE_BYTES, PrivatePaymentStorageError, FORMAT_EXTENSIONS,
    payment_proof_upload_to, payment_qr_upload_to, persist_payment_image,
    private_payment_storage, private_storage_available, sanitize_payment_image,
)


def image_upload(image_format='PNG', extension=None, *, content_type='application/octet-stream', size=(24, 18)):
    extension = extension or FORMAT_EXTENSIONS[image_format]
    output = io.BytesIO()
    Image.new('RGB', size, (140, 90, 30)).save(output, format=image_format)
    return SimpleUploadedFile(f'customer-name{extension}', output.getvalue(), content_type=content_type)


class PaymentImageValidationTests(SimpleTestCase):
    def test_jpeg_png_and_webp_are_decoded_and_reencoded(self):
        for image_format in ('JPEG', 'PNG', 'WEBP'):
            with self.subTest(image_format=image_format):
                upload = image_upload(image_format, content_type='text/html')
                cleaned, detected = sanitize_payment_image(upload)
                self.assertEqual(detected, image_format)
                self.assertTrue(cleaned.name.endswith(FORMAT_EXTENSIONS[image_format]))
                with Image.open(cleaned) as decoded:
                    self.assertEqual(decoded.format, image_format)
                    self.assertEqual(decoded.size, (24, 18))

    def test_mismatched_extension_invalid_content_svg_and_unknown_format_are_rejected(self):
        cases = [
            SimpleUploadedFile('spoofed.png', image_upload('JPEG').read(), content_type='image/png'),
            SimpleUploadedFile('not-an-image.png', b'<html>not an image</html>', content_type='image/png'),
            SimpleUploadedFile('vector.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', content_type='image/svg+xml'),
            SimpleUploadedFile('document.pdf', b'%PDF-1.7', content_type='application/pdf'),
            SimpleUploadedFile('program.exe', b'MZ\x00\x00executable', content_type='application/octet-stream'),
            image_upload('GIF', extension='.gif'),
        ]
        for upload in cases:
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                sanitize_payment_image(upload)

    def test_oversized_upload_is_rejected_before_image_decode(self):
        upload = SimpleUploadedFile('large.png', b'x' * (MAX_PAYMENT_IMAGE_BYTES + 1), content_type='image/png')
        with self.assertRaisesMessage(ValidationError, '5 MB'):
            sanitize_payment_image(upload)

    def test_excessive_dimensions_and_pixel_count_are_rejected(self):
        too_wide = image_upload('PNG', size=(101, 10))
        too_many_pixels = image_upload('PNG', size=(100, 100))
        with patch('store.storage.MAX_PAYMENT_IMAGE_DIMENSION', 100):
            with self.assertRaises(ValidationError):
                sanitize_payment_image(too_wide)
        with patch('store.storage.MAX_PAYMENT_IMAGE_PIXELS', 9_999):
            with self.assertRaises(ValidationError):
                sanitize_payment_image(too_many_pixels)

    def test_upload_path_functions_randomize_names_and_separate_categories(self):
        proof_a = payment_proof_upload_to(None, 'same-name.png')
        proof_b = payment_proof_upload_to(None, 'same-name.png')
        qr_path = payment_qr_upload_to(None, 'same-name.png')
        self.assertNotEqual(proof_a, proof_b)
        self.assertTrue(proof_a.startswith('private/payment-proofs/'))
        self.assertTrue(qr_path.startswith('private/payment-config/qr/'))
        self.assertNotIn('same-name', proof_a + qr_path)

    def test_private_storage_has_no_url_and_rejects_traversal(self):
        with self.assertRaises(ValueError):
            private_payment_storage.url('private/payment-proofs/random.png')
        for path in ('../secret.png', 'private/../../secret.png', r'private\..\secret.png'):
            with self.subTest(path=path), self.assertRaises(SuspiciousFileOperation):
                private_payment_storage.path(path)


class PrivatePaymentStorageTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(PRIVATE_STORAGE_ROOT=Path(self.temp.name) / 'private')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.customer = User.objects.create_user(username='storage-customer', password='test-password')
        self.other_customer = User.objects.create_user(username='other-storage-customer', password='test-password')
        self.staff = User.objects.create_user(username='storage-staff', password='test-password', is_staff=True)
        self.reviewer_permission = Permission.objects.get(content_type__app_label='store', codename='verify_payment')
        self.configuration_permission = Permission.objects.get(
            content_type__app_label='store', codename='manage_payment_configuration')
        self.order = CustomerOrder.objects.create(
            customer=self.customer, customer_name='Storage Customer', total_amount='325.50')
        self.config = self.create_config()
        self.config.activate(self.grant(self.configuration_permission))
        self.instructions = create_order_payment_instructions(self.order)
        self.attempt = self.create_attempt()

    def grant(self, permission):
        self.staff.user_permissions.add(permission)
        return User.objects.get(pk=self.staff.pk)

    def create_config(self):
        manager = self.grant(self.configuration_permission)
        return persist_payment_image(
            image_upload('PNG'), 'qr',
            lambda name: PaymentConfiguration.objects.create(
                display_name='Comfort Zone', upi_id='showroom@upi', qr_image=name),
            actor=manager,
        )

    def create_attempt(self):
        return persist_payment_image(
            image_upload('JPEG'), 'proof',
            lambda name: PaymentAttempt.objects.create(
                order=self.order, customer=self.customer, instructions=self.instructions,
                expected_amount=self.instructions.expected_amount,
                transaction_reference='TXN-SECURE-123', proof_image=name),
            actor=self.customer, owner_order=self.order,
        )

    @staticmethod
    def read_streaming(response):
        try:
            return b''.join(response.streaming_content)
        finally:
            response.close()

    def test_valid_files_live_only_in_private_root_and_have_no_public_url(self):
        self.assertTrue(self.attempt.proof_image.name.startswith('private/payment-proofs/'))
        self.assertTrue(self.config.qr_image.name.startswith('private/payment-config/qr/'))
        self.assertTrue(private_payment_storage.exists(self.attempt.proof_image.name))
        self.assertTrue(private_payment_storage.exists(self.config.qr_image.name))
        with self.assertRaises(ValueError):
            self.attempt.proof_image.url
        self.assertNotIn('media', str(private_payment_storage.path(self.attempt.proof_image.name)).lower())

    def test_upload_service_requires_owner_for_proof_and_configuration_permission_for_qr(self):
        with self.assertRaises(PermissionDenied):
            persist_payment_image(
                image_upload('PNG'), 'qr', lambda name: name,
                actor=User.objects.get(pk=self.other_customer.pk),
            )
        with self.assertRaises(PermissionDenied):
            persist_payment_image(
                image_upload('PNG'), 'proof', lambda name: name,
                actor=self.other_customer, owner_order=self.order,
            )

    def test_customer_ownership_reviewer_and_configuration_permissions_control_delivery(self):
        client = APIClient()
        anonymous = client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/')
        self.assertEqual(anonymous.status_code, 401)

        client.force_authenticate(self.customer)
        owner_proof = client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/')
        self.assertEqual(owner_proof.status_code, 200)
        self.assertEqual(owner_proof['X-Content-Type-Options'], 'nosniff')
        self.assertIn('attachment', owner_proof['Content-Disposition'])
        self.assertIn(b'\xff\xd8\xff', self.read_streaming(owner_proof))
        owner_qr = client.get(f'/api/orders/{self.order.pk}/payment-qr/')
        self.assertEqual(owner_qr.status_code, 200)
        self.assertIn('inline', owner_qr['Content-Disposition'])
        self.assertIn(b'\x89PNG', self.read_streaming(owner_qr))
        self.assertEqual(client.get(f'/api/payment-configurations/{self.config.pk}/qr/').status_code, 403)

        client.force_authenticate(self.other_customer)
        self.assertEqual(client.get(f'/api/orders/{self.order.pk}/payment-qr/').status_code, 404)
        self.assertEqual(client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/').status_code, 403)

        client.force_authenticate(self.staff)
        self.assertEqual(client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/').status_code, 403)
        manager_client = APIClient()
        manager_client.force_authenticate(User.objects.get(pk=self.staff.pk))
        manager_qr = manager_client.get(f'/api/payment-configurations/{self.config.pk}/qr/')
        self.assertEqual(manager_qr.status_code, 200)
        self.read_streaming(manager_qr)
        self.staff.user_permissions.add(self.reviewer_permission)
        reviewer_client = APIClient()
        reviewer_client.force_authenticate(User.objects.get(pk=self.staff.pk))
        reviewer_response = reviewer_client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/')
        self.assertEqual(reviewer_response.status_code, 200)
        self.read_streaming(reviewer_response)

    def test_failed_database_transaction_removes_new_private_file(self):
        upload = image_upload('WEBP')
        saved_names = []

        def fail_after_database_write(name):
            saved_names.append(name)
            PaymentConfiguration.objects.create(
                display_name='Rollback config', upi_id='rollback@upi', qr_image=name)
            raise RuntimeError('simulated database failure')

        with self.assertRaisesRegex(RuntimeError, 'simulated database failure'):
            persist_payment_image(upload, 'qr', fail_after_database_write,
                                  actor=User.objects.get(pk=self.staff.pk))
        self.assertEqual(len(saved_names), 1)
        self.assertFalse(private_payment_storage.exists(saved_names[0]))
        self.assertFalse(PaymentConfiguration.objects.filter(display_name='Rollback config').exists())

    def test_storage_unavailable_fails_without_leaking_filesystem_path(self):
        invalid_root = Path(self.temp.name) / 'not-a-directory'
        invalid_root.write_text('blocked')
        with override_settings(PRIVATE_STORAGE_ROOT=invalid_root):
            self.assertFalse(private_storage_available())
            with self.assertRaises(PrivatePaymentStorageError):
                private_payment_storage._ensure_private_root()

    def test_storage_root_inside_public_static_tree_is_rejected(self):
        with override_settings(PRIVATE_STORAGE_ROOT=Path(settings.BASE_DIR) / 'static' / 'payment-files'):
            self.assertFalse(private_storage_available())

    def test_missing_stored_file_returns_safe_unavailable_response(self):
        client = APIClient()
        client.force_authenticate(self.customer)
        missing_name = 'private/payment-proofs/missing.png'
        self.attempt.proof_image.name = missing_name
        # Direct DB update avoids changing the immutable evidence through model save.
        QuerySet(model=PaymentAttempt, using='default').filter(pk=self.attempt.pk).update(
            proof_image=missing_name,
        )
        response = client.get(f'/api/payment-attempts/{self.attempt.pk}/proof/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.temp.name), str(response.data))

    def test_rejected_proof_and_snapshotted_qr_remain_available(self):
        reviewer = self.grant(self.reviewer_permission)
        from .services import review_payment_attempt
        review_payment_attempt(self.attempt.pk, reviewer, approve=False, remarks='Resubmit evidence.')
        self.attempt.refresh_from_db()
        original_proof = self.attempt.proof_image.name
        original_qr = self.instructions.qr_image_name
        new_config = self.create_config()
        new_config.activate(User.objects.get(pk=self.staff.pk))
        self.assertTrue(private_payment_storage.exists(original_proof))
        self.assertTrue(private_payment_storage.exists(original_qr))
        self.assertNotEqual(new_config.qr_image.name, original_qr)
        with self.assertRaises(ProtectedError):
            self.attempt.delete()
        with self.assertRaises(ProtectedError):
            self.config.delete()
