from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from .models import (
    Vendor, Category, Product, CustomerOrder, VendorPurchase, ContactMessage, Feedback,
    InventoryMovement, OrderCancellation, OrderPaymentReconciliation, PaymentRefund,
)

@admin.register(CustomerOrder)
class CustomerOrderAdmin(admin.ModelAdmin):
    # Orders are created only by checkout. Financial and customer snapshots are
    # immutable; fulfillment changes remain in the authorized API workflow.
    readonly_fields = ('customer', 'order_reference', 'customer_name', 'customer_email',
                       'shipping_address', 'total_amount', 'payment_status', 'status', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register([Vendor, Category, ContactMessage, Feedback])


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    readonly_fields = ('stock', 'created_at')
    list_display = ('name', 'category', 'stock', 'is_active')

    def has_delete_permission(self, request, obj=None):
        if obj and obj.inventory_movements.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(VendorPurchase)
class VendorPurchaseAdmin(admin.ModelAdmin):
    readonly_fields = ('purchased_at', 'received_by', 'received_at')
    list_display = ('id', 'vendor', 'product', 'quantity', 'status', 'received_at')

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == 'Received':
            fields.extend(('vendor', 'product', 'quantity', 'unit_cost', 'status'))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAuditAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(InventoryMovement, ReadOnlyAuditAdmin)
admin.site.register(OrderCancellation, ReadOnlyAuditAdmin)
admin.site.register(OrderPaymentReconciliation, ReadOnlyAuditAdmin)
admin.site.register(PaymentRefund, ReadOnlyAuditAdmin)


admin.site.unregister(User)


@admin.register(User)
class StoreUserAdmin(DjangoUserAdmin):
    """Keep privilege-bearing user fields behind the store admin permission."""
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser or request.user.has_perm('store.manage_staff_accounts'):
            return fieldsets
        restricted = {'is_staff', 'is_superuser', 'groups', 'user_permissions'}
        return [(title, {**options, 'fields': tuple(
            field for field in options.get('fields', ()) if field not in restricted
        )}) for title, options in fieldsets]

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not (request.user.is_superuser or request.user.has_perm('store.manage_staff_accounts')):
            fields.extend(['is_staff', 'is_superuser', 'groups', 'user_permissions', 'is_active'])
        return tuple(dict.fromkeys(fields))
