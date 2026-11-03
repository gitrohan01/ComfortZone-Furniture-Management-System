export function normalizeAuthorization(payload) {
  if (!payload || typeof payload !== 'object'
      || typeof payload.is_staff !== 'boolean'
      || !Array.isArray(payload.permissions)
      || !payload.permissions.every((permission) => typeof permission === 'string')) {
    return null;
  }

  return {
    status: 'ready',
    userId: Number.isInteger(payload.user_id) ? payload.user_id : null,
    username: typeof payload.username === 'string' ? payload.username : '',
    isStaff: payload.is_staff,
    permissions: new Set(payload.permissions),
  };
}

export function hasPermission(authorization, permission) {
  return Boolean(
    authorization?.status === 'ready'
    && isStaffAccount(authorization)
    && typeof permission === 'string'
    && authorization.permissions instanceof Set
    && authorization.permissions.has(permission),
  );
}

export function isAuthenticated(authorization, hasAccessToken) {
  return Boolean(hasAccessToken && authorization?.status !== 'anonymous');
}

export function isStaffAccount(authorization) {
  return Boolean(authorization?.status === 'ready' && authorization.isStaff);
}

export function canAccess(authorization, requiredPermissions) {
  const required = Array.isArray(requiredPermissions) ? requiredPermissions : [requiredPermissions];
  return required.length > 0 && required.every((permission) => hasPermission(authorization, permission));
}

export function visibleNavigation(authorization) {
  return STAFF_NAVIGATION.filter((item) => canAccess(authorization, item.permissions));
}

export function visibleNavigationWithIcons(authorization, icons) {
  return visibleNavigation(authorization).map((item) => {
    const icon = icons?.[item.key];
    if (!icon) {
      throw new Error(`Missing navigation icon for "${item.key}".`);
    }
    return { ...item, icon };
  });
}

export function firstAccessiblePath(authorization) {
  return visibleNavigation(authorization)[0]?.path || '/admin/access-denied';
}

export function customerOrderRouteDecision(authorization, hasAccessToken) {
  if (!isAuthenticated(authorization, hasAccessToken)) return { allowed: false, redirect: '/login' };
  if (isStaffAccount(authorization)) {
    return { allowed: false, redirect: firstAccessiblePath(authorization) };
  }
  return { allowed: true, redirect: null };
}

export function canAccessReport(authorization, reportKey) {
  const required = ['store.view_reports'];
  if (reportKey === 'payment-verification') required.push('store.verify_payment');
  return canAccess(authorization, required);
}

export function classifyApiError(error) {
  const status = error?.response?.status;
  if (status === 401) return 'unauthenticated';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not-found';
  if (status >= 500) return 'server-error';
  if (status === 400) return 'validation';
  return 'unknown';
}

export function shouldExpireSession(error) {
  return error?.response?.status === 401;
}

export const STAFF_NAVIGATION = [
  { key: 'dashboard', label: 'Dashboard', path: '/admin', permissions: ['store.view_dashboard'] },
  { key: 'users', label: 'Manage Users', path: '/admin/users', permissions: ['auth.view_user'] },
  { key: 'categories', label: 'Manage Categories', path: '/admin/categories', permissions: ['store.view_category'] },
  { key: 'products', label: 'Manage Products', path: '/admin/products', permissions: ['store.view_product'] },
  { key: 'orders', label: 'Manage Orders', path: '/admin/orders', permissions: ['store.view_customerorder'] },
  { key: 'payment-review', label: 'Payment Review', path: '/admin/payment-review', permissions: ['store.verify_payment'] },
  { key: 'payment-config', label: 'UPI Configuration', path: '/admin/payment-configuration', permissions: ['store.manage_payment_configuration'] },
  { key: 'stock', label: 'Inventory & Movements', path: '/admin/stock', permissions: ['store.view_product', 'store.view_inventorymovement'] },
  { key: 'vendors', label: 'Vendor Info', path: '/admin/vendors', permissions: ['store.view_vendor'] },
  { key: 'purchases', label: 'Vendor Purchase', path: '/admin/purchases', permissions: ['store.view_vendorpurchase'] },
  { key: 'refunds', label: 'Refunds', path: '/admin/refunds', permissions: ['store.view_paymentrefund'] },
  { key: 'reconciliation', label: 'Payment Reconciliation', path: '/admin/reconciliation', permissions: ['store.view_orderpaymentreconciliation'] },
  { key: 'reports', label: 'Reports', path: '/admin/reports', permissions: ['store.view_reports'] },
  { key: 'contacts', label: 'Contact Us', path: '/admin/contacts', permissions: ['store.view_contactmessage'] },
  { key: 'feedback', label: 'Feedback', path: '/admin/feedback', permissions: ['store.view_feedback'] },
];

export const RESOURCE_PERMISSIONS = {
  users: {
    read: 'auth.view_user', create: 'auth.add_user', edit: 'auth.change_user',
    delete: 'auth.delete_user', deleteExtra: 'store.manage_staff_accounts',
  },
  categories: {
    read: 'store.view_category', create: 'store.add_category',
    edit: 'store.change_category', delete: 'store.delete_category',
  },
  products: {
    read: 'store.view_product', create: 'store.add_product',
    edit: 'store.change_product', delete: 'store.delete_product',
    adjustStock: 'store.adjust_stock',
  },
  orders: {
    read: 'store.view_customerorder', fulfill: 'store.change_order_fulfillment',
    cancel: 'store.cancel_customerorder', requestRefund: 'store.request_refund',
  },
  vendors: {
    read: 'store.view_vendor', create: 'store.add_vendor',
    edit: 'store.change_vendor', delete: 'store.delete_vendor',
  },
  purchases: {
    read: 'store.view_vendorpurchase', create: 'store.add_vendorpurchase',
    edit: 'store.change_vendorpurchase', delete: 'store.delete_vendorpurchase',
    receive: 'store.receive_vendorpurchase',
  },
  contacts: {
    read: 'store.view_contactmessage', create: 'store.add_contactmessage',
    edit: 'store.change_contactmessage', delete: 'store.delete_contactmessage',
  },
  feedback: {
    read: 'store.view_feedback', create: 'store.add_feedback',
    edit: 'store.change_feedback', delete: 'store.delete_feedback',
  },
};
