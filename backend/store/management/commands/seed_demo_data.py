import os
import re
import secrets
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from store.management.commands.provision_staff_roles import ROLE_CODENAMES
from store.models import (
    Category,
    CustomerOrder,
    InventoryMovement,
    OrderCancellation,
    PaymentAttempt,
    PaymentReceipt,
    PaymentRefund,
    Product,
    Vendor,
    VendorPurchase,
)
from store.serializers import (
    CustomerOrderCreateSerializer,
    CustomerOrderSerializer,
    VendorPurchaseSerializer,
)
from store.services import (
    adjust_product_stock,
    cancel_customer_order,
    receive_vendor_purchase,
)


ADMIN_ACCOUNT = {
    'username': 'demo_admin',
    'email': 'demo-admin@example.test',
    'first_name': 'Ananya',
    'last_name': 'Rao',
    'group': 'Administrator',
    'role': 'Administrator',
    'is_staff': True,
    'is_superuser': True,
}

STAFF_ACCOUNTS = (
    ADMIN_ACCOUNT,
    {
        'username': 'demo_store_manager',
        'email': 'demo-store-manager@example.test',
        'first_name': 'Kavita',
        'last_name': 'Rao',
        'group': 'Store Manager',
        'role': 'Store Manager',
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'username': 'demo_inventory_manager',
        'email': 'demo-inventory-manager@example.test',
        'first_name': 'Arjun',
        'last_name': 'Nair',
        'group': 'Inventory Manager',
        'role': 'Inventory Manager',
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'username': 'demo_sales_staff',
        'email': 'demo-sales-staff@example.test',
        'first_name': 'Priya',
        'last_name': 'Mehta',
        'group': 'Sales/Order Staff',
        'role': 'Sales/Order Staff',
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'username': 'demo_payment_reviewer',
        'email': 'demo-payment-reviewer@example.test',
        'first_name': 'Neha',
        'last_name': 'Kulkarni',
        'group': 'Payment Reviewer',
        'role': 'Payment Reviewer',
        'is_staff': True,
        'is_superuser': False,
    },
    {
        'username': 'demo_reports_staff',
        'email': 'demo-reports-staff@example.test',
        'first_name': 'Dev',
        'last_name': 'Patel',
        'group': 'Reports-only Staff',
        'role': 'Reports-only Staff',
        'is_staff': True,
        'is_superuser': False,
    },
)

CUSTOMER_NAMES = (
    ('Aarav', 'Sharma', 'Pune', 'Maharashtra'),
    ('Aditi', 'Verma', 'Jaipur', 'Rajasthan'),
    ('Ishaan', 'Iyer', 'Chennai', 'Tamil Nadu'),
    ('Ananya', 'Rao', 'Bengaluru', 'Karnataka'),
    ('Vivaan', 'Desai', 'Ahmedabad', 'Gujarat'),
    ('Saanvi', 'Nair', 'Kochi', 'Kerala'),
    ('Reyansh', 'Kapoor', 'New Delhi', 'Delhi'),
    ('Diya', 'Mukherjee', 'Kolkata', 'West Bengal'),
    ('Advik', 'Reddy', 'Hyderabad', 'Telangana'),
    ('Myra', 'Joshi', 'Nagpur', 'Maharashtra'),
    ('Kabir', 'Chopra', 'Chandigarh', 'Chandigarh'),
    ('Kiara', 'Menon', 'Thiruvananthapuram', 'Kerala'),
    ('Arjun', 'Bhat', 'Mysuru', 'Karnataka'),
    ('Ira', 'Saxena', 'Lucknow', 'Uttar Pradesh'),
    ('Rohan', 'Pillai', 'Coimbatore', 'Tamil Nadu'),
    ('Tara', 'Banerjee', 'Bhubaneswar', 'Odisha'),
    ('Dhruv', 'Malhotra', 'Gurugram', 'Haryana'),
    ('Meera', 'Kulkarni', 'Nashik', 'Maharashtra'),
    ('Vihaan', 'Chatterjee', 'Howrah', 'West Bengal'),
    ('Sara', 'Khanna', 'Indore', 'Madhya Pradesh'),
    ('Neil', 'Fernandes', 'Panaji', 'Goa'),
    ('Avni', 'Srinivasan', 'Madurai', 'Tamil Nadu'),
    ('Krish', 'Thakur', 'Shimla', 'Himachal Pradesh'),
    ('Riya', 'Ghosh', 'Guwahati', 'Assam'),
    ('Yash', 'Shetty', 'Mangaluru', 'Karnataka'),
)

CATEGORY_DATA = (
    ('Demo Sofas', 'Synthetic showroom sofas and lounge seating.'),
    ('Demo Beds', 'Synthetic showroom beds and bed frames.'),
    ('Demo Chairs', 'Synthetic showroom dining, lounge, and occasional chairs.'),
    ('Demo Tables', 'Synthetic showroom dining, coffee, and side tables.'),
    ('Demo Wardrobes', 'Synthetic showroom wardrobes and cupboards.'),
    ('Demo Office Furniture', 'Synthetic showroom desks and office seating.'),
    ('Demo Storage', 'Synthetic showroom shelving, cabinets, and storage furniture.'),
)

VENDOR_DATA = (
    ('Demo Furniture Works', 'demo-vendor@example.test', '+91-90000-00001', 'Pune, Maharashtra'),
    ('Deccan Timber House', 'deccan-timber@example.test', '+91-90000-00002', 'Nagpur, Maharashtra'),
    ('Jaipur Homecraft', 'jaipur-homecraft@example.test', '+91-90000-00003', 'Jaipur, Rajasthan'),
    ('Malabar Living', 'malabar-living@example.test', '+91-90000-00004', 'Kochi, Kerala'),
    ('Southern Wood Studio', 'southern-wood@example.test', '+91-90000-00005', 'Bengaluru, Karnataka'),
    ('Eastern Office Furnishings', 'eastern-office@example.test', '+91-90000-00006', 'Kolkata, West Bengal'),
)

PRODUCT_DATA = (
    ('Demo Oak Lounge Chair', 'Demo Chairs', 'demo-vendor@example.test', '12499.00', 32, True, 'Solid-oak lounge chair with a woven seat.'),
    ('Demo Teak Two-Seater Sofa', 'Demo Sofas', 'deccan-timber@example.test', '38999.00', 24, True, 'Compact teak-frame sofa upholstered in neutral fabric.'),
    ('Demo Jaipur Three-Seater Sofa', 'Demo Sofas', 'jaipur-homecraft@example.test', '52999.00', 18, True, 'Three-seater sofa with hand-finished wood details.'),
    ('Demo Malabar L-Shape Sofa', 'Demo Sofas', 'malabar-living@example.test', '74999.00', 12, True, 'Corner sofa designed for a family living room.'),
    ('Demo Cane Accent Chair', 'Demo Chairs', 'malabar-living@example.test', '8999.00', 36, True, 'Lightweight accent chair with a cane back.'),
    ('Demo Sheesham Dining Chair', 'Demo Chairs', 'deccan-timber@example.test', '6499.00', 40, True, 'Sheesham dining chair with a clear protective finish.'),
    ('Demo Upholstered Armchair', 'Demo Chairs', 'jaipur-homecraft@example.test', '15999.00', 26, True, 'Upholstered reading chair with a supportive back.'),
    ('Demo King Teak Bed', 'Demo Beds', 'southern-wood@example.test', '64999.00', 14, True, 'King bed frame made from seasoned teak.'),
    ('Demo Queen Storage Bed', 'Demo Beds', 'deccan-timber@example.test', '57999.00', 16, True, 'Queen bed with under-bed storage compartments.'),
    ('Demo Solid Wood Single Bed', 'Demo Beds', 'jaipur-homecraft@example.test', '32999.00', 20, True, 'Single bed frame for a guest or children’s room.'),
    ('Demo Sheesham Dining Table', 'Demo Tables', 'deccan-timber@example.test', '27999.00', 18, True, 'Six-seat dining table with a solid-wood top.'),
    ('Demo Round Coffee Table', 'Demo Tables', 'demo-vendor@example.test', '10999.00', 30, True, 'Round coffee table with a lower storage shelf.'),
    ('Demo Nesting Side Tables', 'Demo Tables', 'jaipur-homecraft@example.test', '7999.00', 28, True, 'Pair of nesting side tables for compact spaces.'),
    ('Demo Four-Door Wardrobe', 'Demo Wardrobes', 'southern-wood@example.test', '45999.00', 14, True, 'Four-door wardrobe with hanging and shelf storage.'),
    ('Demo Sliding-Door Wardrobe', 'Demo Wardrobes', 'deccan-timber@example.test', '51999.00', 12, True, 'Space-saving wardrobe with sliding doors.'),
    ('Demo Compact Two-Door Wardrobe', 'Demo Wardrobes', 'jaipur-homecraft@example.test', '24999.00', 22, True, 'Compact wardrobe suited to a smaller bedroom.'),
    ('Demo Home Office Desk', 'Demo Office Furniture', 'eastern-office@example.test', '18999.00', 24, True, 'Writing desk with a cable-management opening.'),
    ('Demo Ergonomic Task Chair', 'Demo Office Furniture', 'eastern-office@example.test', '13999.00', 32, True, 'Adjustable task chair for a home office.'),
    ('Demo Executive Desk', 'Demo Office Furniture', 'southern-wood@example.test', '36999.00', 12, True, 'Wide executive desk with two storage drawers.'),
    ('Demo Visitor Chair', 'Demo Office Furniture', 'eastern-office@example.test', '5999.00', 30, True, 'Fixed-frame visitor chair with a cushioned seat.'),
    ('Demo Five-Tier Bookcase', 'Demo Storage', 'deccan-timber@example.test', '11999.00', 24, True, 'Open five-tier bookcase for books and display.'),
    ('Demo Entryway Shoe Cabinet', 'Demo Storage', 'jaipur-homecraft@example.test', '9999.00', 26, True, 'Ventilated shoe cabinet with a compact footprint.'),
    ('Demo Utility Storage Cabinet', 'Demo Storage', 'malabar-living@example.test', '16999.00', 18, False, 'Inactive sample cabinet retained for catalog demonstrations.'),
    ('Demo Archive Shelving Unit', 'Demo Storage', 'eastern-office@example.test', '21999.00', 0, False, 'Inactive archive shelving sample; not available for checkout.'),
)

PURCHASE_DATA = (
    ('deccan-timber@example.test', 'Demo Teak Two-Seater Sofa', 6, '27500.00', 112, True),
    ('jaipur-homecraft@example.test', 'Demo Jaipur Three-Seater Sofa', 4, '36500.00', 105, True),
    ('malabar-living@example.test', 'Demo Malabar L-Shape Sofa', 3, '52000.00', 98, True),
    ('southern-wood@example.test', 'Demo King Teak Bed', 4, '43500.00', 91, True),
    ('deccan-timber@example.test', 'Demo Queen Storage Bed', 5, '38200.00', 84, True),
    ('deccan-timber@example.test', 'Demo Sheesham Dining Table', 6, '16800.00', 77, True),
    ('southern-wood@example.test', 'Demo Four-Door Wardrobe', 4, '29800.00', 70, True),
    ('eastern-office@example.test', 'Demo Home Office Desk', 8, '11200.00', 63, True),
    ('eastern-office@example.test', 'Demo Ergonomic Task Chair', 10, '7900.00', 7, False),
    ('jaipur-homecraft@example.test', 'Demo Entryway Shoe Cabinet', 8, '5600.00', 6, False),
    ('demo-vendor@example.test', 'Demo Oak Lounge Chair', 8, '7200.00', 5, False),
    ('malabar-living@example.test', 'Demo Cane Accent Chair', 8, '5100.00', 4, False),
)

ORDER_COUNT = 45
CUSTOMER_ROLE = 'Customer'
CREDENTIALS_ENV = 'COMFORTZONE_DEMO_PASSWORD'
CREDENTIALS_FILENAME = 'DEMO_CREDENTIALS.txt'


def _customer_accounts():
    accounts = []
    for index, (first_name, last_name, city, state) in enumerate(CUSTOMER_NAMES):
        username = 'demo_customer' if index == 0 else f'demo_customer_{index + 1:02d}'
        email = (
            'demo-customer@example.test'
            if index == 0
            else f'demo-customer-{index + 1:02d}@example.test'
        )
        accounts.append({
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': CUSTOMER_ROLE,
            'group': None,
            'is_staff': False,
            'is_superuser': False,
            'city': city,
            'state': state,
            'address': f'Flat {index + 1}, Demo Residency, {city}, {state}, India',
        })
    return tuple(accounts)


def _demo_accounts():
    return STAFF_ACCOUNTS + _customer_accounts()


class Command(BaseCommand):
    help = 'Seed and recover accounts and synthetic showroom data in the isolated demo database.'

    def handle(self, *args, **options):
        self._require_demo_database()
        credential_file = settings.BASE_DIR / '.demo-data' / CREDENTIALS_FILENAME
        account_definitions = _demo_accounts()
        credentials_existed = credential_file.exists()

        existing_admin = User.objects.filter(username=ADMIN_ACCOUNT['username']).first()
        if existing_admin and existing_admin.is_superuser and not credentials_existed:
            raise CommandError(
                'demo_admin is already a superuser but has no demo credential manifest. '
                'It was not changed; preserve it and resolve the account manually first.'
            )

        shared_password = self._load_or_create_demo_password(credential_file, account_definitions)
        try:
            validate_password(shared_password)
        except DjangoValidationError as exc:
            raise CommandError(
                'The shared demo password does not meet the configured password policy: '
                + '; '.join(exc.messages)
            ) from exc

        counts = {}
        with transaction.atomic():
            call_command('provision_staff_roles', verbosity=0)
            self._verify_role_groups()

            users = {}
            for account in account_definitions:
                user, created = self._ensure_account(account, shared_password)
                users[account['username']] = user
                role_counts = counts.setdefault(account['role'], {'created': 0, 'recovered': 0})
                role_counts['created' if created else 'recovered'] += 1

            customers = [users[account['username']] for account in _customer_accounts()]
            categories, vendors, products = self._seed_catalog(users['demo_inventory_manager'])
            purchases = self._seed_purchases(
                vendors, products, users['demo_store_manager'], users['demo_inventory_manager'],
            )
            orders, cancellations = self._seed_orders(
                customers, products, users['demo_store_manager'],
            )
            self._seed_low_stock(products, users['demo_inventory_manager'])

        self.stdout.write(self.style.SUCCESS('Demo account and showroom data summary:'))
        for role in [account['role'] for account in STAFF_ACCOUNTS] + [CUSTOMER_ROLE]:
            role_counts = counts[role]
            self.stdout.write(
                f"  {role}: {role_counts['created']} created, "
                f"{role_counts['recovered']} recovered"
            )
        self.stdout.write(f'  Customer accounts in dataset: {len(customers)}')
        self.stdout.write(f'  Categories: {len(categories)}')
        self.stdout.write(f'  Products: {len(products)}')
        self.stdout.write(f'  Vendors: {len(vendors)}')
        self.stdout.write(f'  Vendor purchases: {len(purchases)}')
        self.stdout.write(f'  Orders: {len(orders)}')
        self.stdout.write(f'  Cancellation events: {len(cancellations)}')
        self.stdout.write('  Payment attempts/receipts/refunds: 0 (no payment evidence is fabricated)')
        self.stdout.write(f'  Credentials: {credential_file}')
        self.stdout.write('  Demo-managed accounts and roles:')
        for account in account_definitions:
            self.stdout.write(f"    {account['username']} - {account['role']}")
        self.stdout.write(self.style.SUCCESS('Demo data is ready; rerunning does not duplicate records.'))

    @staticmethod
    def _require_demo_database():
        expected_path = (settings.BASE_DIR / '.demo-data' / 'showroom.sqlite3').resolve()
        database = settings.DATABASES['default']
        configured_path = Path(database['NAME']).expanduser().resolve()
        if (
            settings.SETTINGS_MODULE != 'config.demo_settings'
            or database['ENGINE'] != 'django.db.backends.sqlite3'
            or configured_path != expected_path
            or configured_path == (settings.BASE_DIR / 'test.sqlite3').resolve()
        ):
            raise CommandError(
                'Use this command only with --settings=config.demo_settings; '
                'it refuses all other databases.'
            )

    @staticmethod
    def _load_or_create_demo_password(credential_file, accounts):
        credential_file.parent.mkdir(parents=True, exist_ok=True)
        configured_password = os.environ.get(CREDENTIALS_ENV)
        if configured_password == '':
            raise CommandError(f'{CREDENTIALS_ENV} cannot be empty.')

        if credential_file.exists():
            contents = credential_file.read_text(encoding='utf-8')
            match = re.search(r'^Shared demo password: (.+)$', contents, re.MULTILINE)
            if not match:
                raise CommandError(
                    f'{credential_file} is missing the shared-password entry; '
                    'restore the credential file rather than generating new credentials.'
                )
            password = match.group(1).strip()
            if configured_password and configured_password != password:
                raise CommandError(
                    f'{CREDENTIALS_ENV} differs from the saved password. '
                    'Edit the local credential file explicitly to rotate demo credentials.'
                )
            return password

        password = configured_password or secrets.token_urlsafe(24)
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise CommandError(
                f'{CREDENTIALS_ENV} does not meet the configured password policy: '
                + '; '.join(exc.messages)
            ) from exc
        contents = Command._render_credentials(password, accounts)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                newline='\n',
                dir=credential_file.parent,
                prefix='.demo-credentials-',
                suffix='.tmp',
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(contents)
            os.replace(temporary_path, credential_file)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
        return password

    @staticmethod
    def _render_credentials(password, accounts):
        lines = [
            'COMFORT ZONE LOCAL DEMO CREDENTIALS',
            'Keep this file private. It is local-only and must not be committed or shared.',
            '',
            'Login URL: http://127.0.0.1:5173/login',
            'Backend token endpoint: http://127.0.0.1:8002/api/auth/login/',
            'Credential policy: one strong, randomly generated shared password for demo-managed accounts.',
            'The password is stable across seed runs and is reset only from this local file.',
            'To rotate it, replace the value on the next line with a password of at least 12 characters,',
            'then rerun: python manage.py seed_demo_data --settings=config.demo_settings',
            '',
            f'Shared demo password: {password}',
            '',
            'USERNAMES AND ROLES',
        ]
        lines.extend(f"{account['username']} | {account['role']}" for account in accounts)
        lines.extend([
            '',
            'Customers have individual accounts and can see only their own orders.',
            'Use the shared password above for each username.',
            'No real payment credentials or payment records are included in this demo.',
            '',
        ])
        return '\n'.join(lines)

    @staticmethod
    def _verify_role_groups():
        administrator = Group.objects.filter(name='Administrator').first()
        if administrator is None:
            raise CommandError('The Administrator role group was not provisioned.')
        expected_administrator = set(
            Permission.objects.filter(
                content_type__app_label='store',
            ).values_list('content_type__app_label', 'codename')
        )
        expected_administrator.update(
            Permission.objects.filter(
                content_type__app_label='auth',
                content_type__model__in=('user', 'group'),
            ).values_list('content_type__app_label', 'codename')
        )
        actual_administrator = set(administrator.permissions.values_list(
            'content_type__app_label', 'codename',
        ))
        if actual_administrator != expected_administrator:
            raise CommandError('Administrator group permissions do not match the provisioned policy.')

        for group_name, codenames in ROLE_CODENAMES.items():
            group = Group.objects.filter(name=group_name).first()
            if group is None:
                raise CommandError(f'The {group_name} role group was not provisioned.')
            expected = {('store', codename) for codename in codenames}
            actual = set(group.permissions.values_list('content_type__app_label', 'codename'))
            if actual != expected:
                raise CommandError(
                    f'{group_name} permissions do not match the least-privilege role policy.'
                )

    @staticmethod
    def _ensure_account(account, password):
        user = User.objects.filter(username=account['username']).first()
        if user and user.is_superuser and not account['is_superuser']:
            raise CommandError(
                f"{account['username']} is an existing superuser and will not be modified."
            )
        if user is None:
            user = User(username=account['username'])
        email_conflict = User.objects.filter(email__iexact=account['email'])
        if user.pk:
            email_conflict = email_conflict.exclude(pk=user.pk)
        if email_conflict.exists():
            raise CommandError(
                f"Cannot assign {account['email']} to {account['username']}; "
                'another account already owns that email.'
            )

        created = user.pk is None
        user.email = account['email']
        user.first_name = account['first_name']
        user.last_name = account['last_name']
        user.is_active = True
        user.is_staff = account['is_staff']
        user.is_superuser = account['is_superuser']
        user.set_password(password)
        user.save()
        user.groups.set([Group.objects.get(name=account['group'])] if account['group'] else [])
        user.user_permissions.clear()
        return user, created

    @staticmethod
    def _seed_catalog(inventory_actor):
        categories = {}
        for name, description in CATEGORY_DATA:
            category, _created = Category.objects.get_or_create(
                name=name, defaults={'description': description},
            )
            categories[name] = category

        vendors = {}
        for name, email, phone, address in VENDOR_DATA:
            vendor, _created = Vendor.objects.get_or_create(
                email=email,
                defaults={'name': name, 'phone': phone, 'address': address, 'is_active': True},
            )
            if vendor.name != name:
                raise CommandError(
                    f'The demo vendor email {email} is already assigned to another vendor.'
                )
            if (vendor.name, vendor.phone, vendor.address, vendor.is_active) != (
                name, phone, address, True,
            ):
                vendor.name = name
                vendor.phone = phone
                vendor.address = address
                vendor.is_active = True
                vendor.save(update_fields=['name', 'phone', 'address', 'is_active'])
            vendors[email] = vendor

        products = {}
        for name, category_name, vendor_email, price, opening_stock, active, description in PRODUCT_DATA:
            demo_key = f'demo:product:{name.casefold().replace(" ", "-")}'
            matches = list(Product.objects.filter(demo_key=demo_key)[:2])
            if not matches:
                matches = list(Product.objects.filter(name=name, demo_key__isnull=True)[:2])
            if len(matches) > 1:
                raise CommandError(f'Multiple products named {name!r} prevent safe demo seeding.')
            product = matches[0] if matches else Product(
                name=name,
                stock=0,
            )
            if product.pk and product.vendor_id and product.vendor.email not in vendors:
                raise CommandError(
                    f'The product {name!r} already belongs to a non-demo vendor; it was not changed.'
                )
            product.category = categories[category_name]
            product.vendor = vendors[vendor_email]
            product.description = description
            product.price = price
            product.is_active = active
            product.demo_key = demo_key
            product.save()
            products[name] = product

            opening_key = f'demo:opening-stock:{product.pk}'
            if not InventoryMovement.objects.filter(source_key=opening_key).exists():
                try:
                    adjust_product_stock(
                        product.pk,
                        target_stock=opening_stock,
                        actor=inventory_actor,
                        reason='Opening stock for the local synthetic showroom dataset.',
                        source_key=opening_key,
                    )
                except DjangoValidationError as exc:
                    detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
                    raise CommandError(f'Could not initialize stock for {name}: {detail}') from exc
        return categories, vendors, products

    @staticmethod
    def _seed_low_stock(products, inventory_actor):
        adjustments = (
            ('Demo Oak Lounge Chair', 1),
            ('Demo Teak Two-Seater Sofa', 2),
        )
        for product_name, target_stock in adjustments:
            product = products[product_name]
            if not product.is_active:
                raise CommandError(f'Low-stock demo product {product_name!r} must remain active.')
            try:
                adjust_product_stock(
                    product.pk,
                    target_stock=target_stock,
                    actor=inventory_actor,
                    reason='Seeded low-stock demo record for inventory reporting.',
                    source_key=f'demo:low-stock:{product.demo_key}',
                )
            except DjangoValidationError as exc:
                detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
                raise CommandError(f'Could not seed low stock for {product_name}: {detail}') from exc

    @staticmethod
    def _seed_purchases(vendors, products, store_manager, inventory_manager):
        purchases = []
        seen_keys = set()
        for vendor_email, product_name, quantity, unit_cost, days_ago, receive in PURCHASE_DATA:
            vendor = vendors[vendor_email]
            product = products[product_name]
            dedupe_key = (vendor.pk, product.pk, quantity, unit_cost)
            if dedupe_key in seen_keys:
                raise CommandError('The demo vendor purchase definitions contain duplicate identifiers.')
            seen_keys.add(dedupe_key)

            matches = list(VendorPurchase.objects.filter(
                vendor=vendor, product=product, quantity=quantity, unit_cost=unit_cost,
            )[:2])
            if len(matches) > 1:
                raise CommandError(
                    f'Duplicate demo purchase for {vendor.name} and {product.name}; '
                    'resolve it before rerunning the seed.'
                )
            if matches:
                purchase = matches[0]
            else:
                requested_status = 'Approved' if receive else 'Requested'
                serializer = VendorPurchaseSerializer(data={
                    'vendor': vendor.pk,
                    'product': product.pk,
                    'quantity': quantity,
                    'unit_cost': unit_cost,
                    'status': requested_status,
                })
                serializer.is_valid(raise_exception=True)
                purchase = serializer.save()
                purchased_at = timezone.now() - timedelta(days=days_ago)
                VendorPurchase.objects.filter(pk=purchase.pk).update(purchased_at=purchased_at)
                purchase.refresh_from_db()

            if receive and purchase.status == 'Approved':
                try:
                    purchase = receive_vendor_purchase(purchase.pk, inventory_manager)
                except (DjangoValidationError, ValueError) as exc:
                    raise CommandError(f'Could not receive demo purchase {purchase.pk}: {exc}') from exc
            elif receive and purchase.status != 'Received':
                raise CommandError(
                    f'Demo purchase {purchase.pk} should be received but is {purchase.status}.'
                )
            elif not receive and purchase.status not in ('Requested', 'Approved', 'Received'):
                raise CommandError(
                    f'Demo purchase {purchase.pk} has unexpected status {purchase.status}.'
                )
            purchases.append(purchase)
        return purchases

    @staticmethod
    def _seed_orders(customers, products, store_manager):
        active_products = [
            products[row[0]] for row in PRODUCT_DATA if row[5]
        ]
        orders = []
        cancellations = []
        today = timezone.now()
        for index in range(ORDER_COUNT):
            reference = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f'comfortzone-local-demo-order-{index + 1:03d}',
            ))
            order = CustomerOrder.objects.filter(order_reference=reference).first()
            if order is None:
                customer = customers[index % len(customers)]
                product_indexes = (
                    (index * 3) % len(active_products),
                    (index * 3 + 7) % len(active_products),
                )
                items = []
                for position, product_index in enumerate(product_indexes):
                    product = active_products[product_index]
                    quantity = 2 if (index + position) % 9 == 0 else 1
                    items.append({'product_id': product.pk, 'quantity': quantity})
                order_data = {
                    'customer_name': f'{customer.first_name} {customer.last_name}',
                    'customer_email': customer.email,
                    'shipping_address': (
                        f'{index + 11}, Demo Residency, '
                        f'{CUSTOMER_NAMES[index % len(CUSTOMER_NAMES)][2]}, '
                        f'{CUSTOMER_NAMES[index % len(CUSTOMER_NAMES)][3]}, India'
                    ),
                    'items': items,
                }
                request = SimpleNamespace(user=customer)
                checkout = CustomerOrderCreateSerializer(
                    data=order_data, context={'request': request},
                )
                checkout.is_valid(raise_exception=True)
                order = checkout.save(order_reference=reference)

                order_date = today - timedelta(days=(index * 3) % 151)
                CustomerOrder.objects.filter(pk=order.pk).update(created_at=order_date)

                target_status = (
                    'Cancelled' if index < 5
                    else 'Pending' if index < 15
                    else 'Processing' if index < 23
                    else 'Shipped' if index < 33
                    else 'Delivered'
                )
                if target_status == 'Cancelled':
                    cancellations.append(cancel_customer_order(
                        order.pk,
                        store_manager,
                        reason='Synthetic demo cancellation for an unpaid order.',
                    ))
                else:
                    transitions = {
                        'Pending': [],
                        'Processing': ['Processing'],
                        'Shipped': ['Processing', 'Shipped'],
                        'Delivered': ['Processing', 'Shipped', 'Delivered'],
                    }
                    for next_status in transitions[target_status]:
                        update = CustomerOrderSerializer(
                            order, data={'status': next_status}, partial=True,
                        )
                        update.is_valid(raise_exception=True)
                        order = update.save()
            elif order.customer_id is None or not order.order_reference:
                raise CommandError(f'Demo order {reference} has invalid ownership or reference data.')
            orders.append(order)
            cancellation = OrderCancellation.objects.filter(order=order).first()
            if cancellation:
                cancellations.append(cancellation)

        cancellation_by_id = {event.pk: event for event in cancellations}
        return orders, list(cancellation_by_id.values())
