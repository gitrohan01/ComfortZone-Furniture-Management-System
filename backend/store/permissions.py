from rest_framework.permissions import BasePermission, SAFE_METHODS


class StoreModelPermissions(BasePermission):
    """Require an explicit store permission for every staff resource action."""

    def has_permission(self, request, view):
        user = request.user
        # Product and category catalog reads are intentionally public. Staff
        # users still need the full-data view permission.
        if (getattr(view, 'public_catalog_read', False) and request.method in SAFE_METHODS
                and (not user or not user.is_authenticated or not user.is_staff)):
            return True
        if not user or not user.is_authenticated:
            return False
        if not user.is_staff:
            return False
        action = getattr(view, 'action', None)
        if action == 'create' and getattr(view, 'disable_staff_create', False):
            return False
        model = getattr(getattr(view, 'queryset', None), 'model', None)
        if model is None:
            return False
        if action == 'receive':
            return user.has_perm('store.receive_vendorpurchase')
        if (model and model._meta.model_name == 'product'
                and action in ('update', 'partial_update')
                and set(request.data.keys()).issubset({'stock', 'stock_reason', 'stock_source_key'})
                and 'stock' in request.data):
            return user.has_perm('store.adjust_stock')
        if model and model._meta.model_name == 'customerorder' and action == 'cancel':
            return user.has_perm('store.cancel_customerorder')
        if model._meta.model_name == 'customerorder' and action in ('update', 'partial_update'):
            return user.has_perm('store.change_order_fulfillment')
        if action in ('list', 'retrieve') or request.method in ('GET', 'HEAD', 'OPTIONS'):
            codename = f'view_{model._meta.model_name}'
        elif action == 'create' or request.method == 'POST':
            codename = f'add_{model._meta.model_name}'
        elif action in ('update', 'partial_update') or request.method in ('PUT', 'PATCH'):
            codename = f'change_{model._meta.model_name}'
        elif action == 'destroy' or request.method == 'DELETE':
            codename = f'delete_{model._meta.model_name}'
        else:
            codename = None
        if codename is None or not user.has_perm(f'{model._meta.app_label}.{codename}'):
            return False
        if model._meta.model_name == 'user' and action == 'destroy':
            return user.has_perm('store.manage_staff_accounts')
        if action == 'receive':
            return user.has_perm('store.receive_vendorpurchase')
        return True

    def has_object_permission(self, request, view, obj):
        if obj.__class__._meta.model_name == 'user' and getattr(view, 'action', None) == 'destroy':
            return request.user.has_perm('store.manage_staff_accounts')
        return True


class StoreDashboardPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff and
                    user.has_perm('store.view_dashboard'))
