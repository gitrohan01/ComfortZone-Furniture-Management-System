import io
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import Category, Product


def product_image(name='chair.png', image_format='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (24, 18), (80, 120, 90)).save(output, format=image_format)
    return SimpleUploadedFile(name, output.getvalue(), content_type=f'image/{image_format.lower()}')


class ProductImageApiTests(APITestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.media_override = override_settings(
            MEDIA_ROOT=Path(self.media_dir.name),
            MEDIA_URL='/media/',
        )
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.staff = User.objects.create_user(username='image-staff', password='test-password', is_staff=True, is_superuser=True)
        self.customer = User.objects.create_user(username='image-customer', password='test-password')
        self.category = Category.objects.create(name='Image test chairs')
        self.product = Product.objects.create(
            name='Image test chair', category=self.category, price='100.00', stock=2,
            image_url='https://example.test/legacy-chair.png',
        )
        self.client = APIClient()

    def test_staff_can_upload_replace_and_retrieve_product_image(self):
        self.client.force_authenticate(user=self.staff)
        first = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': product_image()},
            format='multipart',
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.data['image'].endswith('.png'))
        self.assertEqual(first.data['image_url'], 'https://example.test/legacy-chair.png')

        self.product.refresh_from_db()
        first_path = Path(self.product.image.path)
        self.assertTrue(first_path.is_file())
        with Image.open(first_path) as saved:
            self.assertEqual(saved.size, (24, 18))

        second = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': product_image('replacement.webp', 'WEBP')},
            format='multipart',
        )
        self.assertEqual(second.status_code, 200, second.data)
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.image.path, str(first_path))
        with Image.open(self.product.image.path) as saved:
            self.assertEqual(saved.format, 'WEBP')

        public = self.client.get(f'/api/products/{self.product.pk}/')
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data['image'], second.data['image'])
        self.assertEqual(public.data['image_url'], 'https://example.test/legacy-chair.png')

    def test_product_image_rejects_unsupported_and_oversized_uploads(self):
        self.client.force_authenticate(user=self.staff)
        unsupported = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': SimpleUploadedFile('chair.svg', b'<svg/>', content_type='image/svg+xml')},
            format='multipart',
        )
        oversized = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': SimpleUploadedFile('large.png', b'x' * (5 * 1024 * 1024 + 1), content_type='image/png')},
            format='multipart',
        )

        self.assertEqual(unsupported.status_code, 400)
        self.assertIn('image', unsupported.data)
        self.assertEqual(oversized.status_code, 400)
        self.assertIn('image', oversized.data)

    def test_customer_cannot_upload_product_images(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': product_image()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

    def test_product_image_upload_requires_product_change_permission(self):
        staff_without_product_permission = User.objects.create_user(
            username='image-unprivileged-staff', password='test-password', is_staff=True,
        )
        self.client.force_authenticate(user=staff_without_product_permission)
        response = self.client.patch(
            f'/api/products/{self.product.pk}/',
            {'image': product_image()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)
