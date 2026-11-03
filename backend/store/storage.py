"""Private payment image storage and validation primitives.

This module deliberately exposes no URLs. Callers must use the scoped file
delivery views and must persist new files through persist_payment_image().
"""
import io
import logging
import os
import stat
import uuid
import warnings
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, SuspiciousFileOperation, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.utils import validate_file_name
from django.db import models, transaction
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

MAX_PAYMENT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PAYMENT_IMAGE_PIXELS = 20_000_000
MAX_PAYMENT_IMAGE_DIMENSION = 8_000
FORMAT_EXTENSIONS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}
VALIDATION_EXTENSIONS = {'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'}, 'WEBP': {'.webp'}}
CONTENT_TYPES = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
IMAGE_SIGNATURES = {
    'JPEG': lambda data: data.startswith(b'\xff\xd8\xff'),
    'PNG': lambda data: data.startswith(b'\x89PNG\r\n\x1a\n'),
    'WEBP': lambda data: len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP',
}


class PrivatePaymentStorageError(Exception):
    """Safe, path-free error raised when private storage cannot be used."""


class ValidatedPrivateImageField(models.FileField):
    """File field that validates and re-encodes uploads before storage writes."""
    def pre_save(self, model_instance, add):
        field_file = getattr(model_instance, self.attname)
        if field_file and not field_file._committed:
            sanitized, _ = sanitize_payment_image(field_file.file)
            field_file.file = sanitized
            field_file.name = sanitized.name
        return super().pre_save(model_instance, add)


@deconstructible
class PrivatePaymentStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=None, base_url=None)

    @property
    def location(self):
        # Read dynamically so isolated tests can safely override the root.
        return str(settings.PRIVATE_STORAGE_ROOT)

    @property
    def base_location(self):
        return os.path.abspath(self.location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError('Private payment files do not have public URLs.')

    def _safe_name(self, name):
        try:
            name = name.replace('\\', '/')
            validate_file_name(name, allow_relative_path=True)
            path = PurePosixPath(name)
            if path.is_absolute() or not path.parts or any(part in ('', '.', '..') for part in path.parts):
                raise SuspiciousFileOperation('Invalid private file name.')
            candidate = Path(self.path(name))
            if candidate.is_symlink():
                raise SuspiciousFileOperation('Symlinks are not allowed in private storage.')
            return name
        except (SuspiciousFileOperation, ValueError, OSError):
            raise SuspiciousFileOperation('Invalid private file name.') from None

    def _ensure_private_root(self):
        root = Path(self.location).expanduser()
        if not root.is_absolute() or root.is_symlink():
            raise PrivatePaymentStorageError('Private payment storage is unavailable.')
        try:
            resolved_root = root.resolve()
            public_roots = [Path(settings.BASE_DIR) / 'static', Path(settings.BASE_DIR) / 'media']
            for setting_name in ('STATIC_ROOT', 'MEDIA_ROOT'):
                configured = getattr(settings, setting_name, None)
                if configured:
                    public_roots.append(Path(configured))
            for public_root in public_roots:
                resolved_public = public_root.expanduser().resolve()
                if resolved_root == resolved_public or resolved_public in resolved_root.parents:
                    raise PrivatePaymentStorageError('Private payment storage is unavailable.')
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK | os.X_OK):
                raise PrivatePaymentStorageError('Private payment storage is unavailable.')
            if os.name == 'posix':
                os.chmod(root, stat.S_IRWXU)
        except (OSError, RuntimeError):
            raise PrivatePaymentStorageError('Private payment storage is unavailable.') from None

    def _save(self, name, content):
        self._ensure_private_root()
        return super()._save(self._safe_name(name), content)

    def path(self, name):
        from django.utils._os import safe_join
        safe_name = name.replace('\\', '/')
        validate_file_name(safe_name, allow_relative_path=True)
        parts = PurePosixPath(safe_name)
        if parts.is_absolute() or not parts.parts or any(part in ('', '.', '..') for part in parts.parts):
            raise SuspiciousFileOperation('Invalid private file name.')
        result = safe_join(self.location, safe_name)
        root = Path(self.location).resolve()
        resolved = Path(result).resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise SuspiciousFileOperation('Invalid private file name.')
        return result

    def open(self, name, mode='rb'):
        return super().open(self._safe_name(name), mode)

    def delete(self, name):
        return super().delete(self._safe_name(name))

    def exists(self, name):
        return super().exists(self._safe_name(name))


private_payment_storage = PrivatePaymentStorage()


def _read_bounded(upload):
    declared_size = getattr(upload, 'size', None)
    if declared_size is not None and declared_size > MAX_PAYMENT_IMAGE_BYTES:
        raise ValidationError('Image exceeds the 5 MB limit.')
    try:
        upload.seek(0)
    except (AttributeError, OSError):
        pass
    chunks = []
    total = 0
    while True:
        chunk = upload.read(min(64 * 1024, MAX_PAYMENT_IMAGE_BYTES + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_PAYMENT_IMAGE_BYTES:
            raise ValidationError('Image exceeds the 5 MB limit.')
        chunks.append(chunk)
    if total == 0:
        raise ValidationError('The uploaded file is empty.')
    try:
        upload.seek(0)
    except (AttributeError, OSError):
        pass
    return b''.join(chunks)


def sanitize_payment_image(upload):
    """Decode and re-encode a supported image; ignores the browser MIME type."""
    data = _read_bounded(upload)
    original_name = getattr(upload, 'name', '') or ''
    extension = Path(original_name).suffix.lower()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                detected = image.format
                if detected not in FORMAT_EXTENSIONS or not IMAGE_SIGNATURES[detected](data):
                    raise ValidationError('Only valid JPEG, PNG, and WebP images are accepted.')
                if extension not in VALIDATION_EXTENSIONS[detected]:
                    raise ValidationError('The filename extension does not match the image content.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValidationError('Animated images are not accepted.')
                width, height = image.size
                if (width < 1 or height < 1 or width > MAX_PAYMENT_IMAGE_DIMENSION
                        or height > MAX_PAYMENT_IMAGE_DIMENSION or width * height > MAX_PAYMENT_IMAGE_PIXELS):
                    raise ValidationError('Image dimensions exceed the supported limit.')
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                has_alpha = 'A' in image.getbands() or 'transparency' in image.info
                mode = 'RGBA' if detected in ('PNG', 'WEBP') and has_alpha else 'RGB'
                clean = Image.new(mode, image.size)
                clean.paste(image.convert(mode))
                output = io.BytesIO()
                options = {'format': detected}
                if detected == 'JPEG':
                    options.update(quality=90, optimize=True)
                elif detected == 'WEBP':
                    options.update(quality=90, method=4)
                clean.save(output, **options)
                normalized = output.getvalue()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        logger.info('Rejected invalid payment image (%s).', type(exc).__name__)
        raise ValidationError('The uploaded file is not a valid supported image.') from None
    if len(normalized) > MAX_PAYMENT_IMAGE_BYTES:
        raise ValidationError('Normalized image exceeds the 5 MB limit.')
    return ContentFile(normalized, name=f'validated{FORMAT_EXTENSIONS[detected]}'), detected


def validate_payment_image(upload):
    sanitize_payment_image(upload)


def validate_product_image(upload):
    sanitize_payment_image(upload)


def product_image_upload_to(instance, filename):
    extension = Path(filename).suffix.lower()
    extensions = {'.jpg': '.jpg', '.jpeg': '.jpg', '.png': '.png', '.webp': '.webp'}
    if extension not in extensions:
        raise ValidationError('Only JPEG, PNG, and WebP product images are accepted.')
    return f'products/{uuid.uuid4().hex}{extensions[extension]}'


def _random_upload_path(kind, extension):
    folders = {'proof': 'private/payment-proofs', 'qr': 'private/payment-config/qr'}
    if kind not in folders or extension not in FORMAT_EXTENSIONS.values():
        raise ValidationError('Invalid private payment image category.')
    return f'{folders[kind]}/{uuid.uuid4().hex}{extension}'


def payment_proof_upload_to(instance, filename):
    return _random_upload_path('proof', Path(filename).suffix.lower())


def payment_qr_upload_to(instance, filename):
    return _random_upload_path('qr', Path(filename).suffix.lower())


def persist_payment_image(upload, kind, persist_record, *, actor, owner_order=None):
    """Validate, privately store, and persist a DB reference as one outer transaction.

    ``persist_record`` receives the randomized storage name. This service must be
    called outside another atomic block so rollback cleanup is reliable.
    """
    if kind == 'qr':
        if not (actor and actor.is_authenticated and actor.is_staff
                and actor.has_perm('store.manage_payment_configuration')):
            raise PermissionDenied('An authorized configuration manager is required.')
    elif kind == 'proof':
        if not (actor and actor.is_authenticated and not actor.is_staff and owner_order
                and owner_order.customer_id == actor.pk and owner_order.payment_status == 'Pending'
                and owner_order.status != 'Cancelled'):
            raise PermissionDenied('The customer can only submit proof for their own payable order.')
    else:
        raise ValidationError('Invalid private payment image category.')

    sanitized, detected = sanitize_payment_image(upload)
    relative_name = _random_upload_path(kind, FORMAT_EXTENSIONS[detected])
    saved_name = None
    try:
        with transaction.atomic(durable=True):
            saved_name = private_payment_storage.save(relative_name, sanitized)
            result = persist_record(saved_name)
        return result
    except Exception:
        if saved_name:
            try:
                private_payment_storage.delete(saved_name)
            except (OSError, SuspiciousFileOperation, PrivatePaymentStorageError):
                logger.error('Could not clean an unreferenced private payment file after a failed transaction.')
        raise


def private_storage_available():
    try:
        private_payment_storage._ensure_private_root()
        probe_name = f'.storage-check/{uuid.uuid4().hex}.tmp'
        private_payment_storage.save(probe_name, ContentFile(b'private-storage-check'))
        private_payment_storage.delete(probe_name)
        return True
    except (OSError, PrivatePaymentStorageError, SuspiciousFileOperation):
        logger.error('Private payment storage availability check failed.')
        return False
