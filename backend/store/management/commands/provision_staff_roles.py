from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError


ROLE_CODENAMES = {
    'Store Manager': {
        'view_product', 'add_product', 'change_product',
        'view_category', 'add_category', 'change_category',
        'view_vendor', 'add_vendor', 'change_vendor',
        'view_vendorpurchase', 'add_vendorpurchase', 'change_vendorpurchase',
        'view_customerorder', 'change_order_fulfillment',
        'view_contactmessage', 'view_feedback', 'view_dashboard',
        'cancel_customerorder', 'request_refund', 'reconcile_order_payment',
        'view_ordercancellation', 'view_paymentrefund',
        'view_orderpaymentreconciliation', 'view_inventorymovement',
    },
    'Inventory Manager': {
        'view_product', 'view_category', 'view_vendor', 'view_vendorpurchase',
        'adjust_stock', 'receive_vendorpurchase', 'view_inventorymovement',
    },
    'Sales/Order Staff': {
        'view_customerorder', 'change_order_fulfillment', 'view_dashboard',
    },
    'Payment Reviewer': {
        'verify_payment', 'confirm_refund', 'view_paymentrefund',
        'view_orderpaymentreconciliation',
    },
    'Reports-only Staff': {'view_reports'},
}


class Command(BaseCommand):
    help = 'Create the six staff role groups and add their approved permissions.'

    def handle(self, *args, **options):
        store_permissions = list(Permission.objects.filter(content_type__app_label='store'))
        admin_user_perms = Permission.objects.filter(
            content_type__app_label='auth',
            content_type__model__in=('user', 'group'),
        )
        all_admin_permissions = list(store_permissions) + list(admin_user_perms)

        administrator, _ = Group.objects.get_or_create(name='Administrator')
        administrator.permissions.set(all_admin_permissions)
        self.stdout.write('Provisioned Administrator (permissions only; no user assignment or superuser grant).')

        for name, codenames in ROLE_CODENAMES.items():
            group, _ = Group.objects.get_or_create(name=name)
            permissions = list(Permission.objects.filter(
                content_type__app_label='store', codename__in=codenames,
            ))
            found = {permission.codename for permission in permissions}
            missing = codenames - found
            if missing:
                raise CommandError(
                    f'{name}: permissions not found: {", ".join(sorted(missing))}'
                )
            group.permissions.set(permissions)
            self.stdout.write(f'Provisioned {name}.')
