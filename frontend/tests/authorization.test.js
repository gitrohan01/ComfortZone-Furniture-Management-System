import test from 'node:test';
import assert from 'node:assert/strict';
import {
  canAccess,
  canAccessReport,
  classifyApiError,
  customerOrderRouteDecision,
  firstAccessiblePath,
  hasPermission,
  isAuthenticated,
  isStaffAccount,
  normalizeAuthorization,
  RESOURCE_PERMISSIONS,
  shouldExpireSession,
  STAFF_NAVIGATION,
  visibleNavigation,
  visibleNavigationWithIcons,
} from '../src/auth/authorization.js';

const rolePermissions = {
  Administrator: [
    'auth.view_user', 'auth.add_user', 'auth.change_user', 'auth.delete_user',
    'store.view_dashboard', 'store.view_category', 'store.view_product',
    'store.view_customerorder', 'store.verify_payment', 'store.manage_payment_configuration',
    'store.view_inventorymovement', 'store.view_vendor', 'store.view_vendorpurchase',
    'store.view_paymentrefund', 'store.view_orderpaymentreconciliation', 'store.view_reports',
    'store.view_contactmessage', 'store.view_feedback', 'store.adjust_stock',
    'store.cancel_customerorder', 'store.request_refund', 'store.confirm_refund',
    'store.reconcile_order_payment', 'store.receive_vendorpurchase',
  ],
  'Store Manager': [
    'store.view_dashboard', 'store.view_category', 'store.view_product',
    'store.view_customerorder', 'store.view_inventorymovement', 'store.view_vendor',
    'store.view_vendorpurchase', 'store.view_paymentrefund',
    'store.view_orderpaymentreconciliation', 'store.view_contactmessage',
    'store.view_feedback', 'store.cancel_customerorder', 'store.request_refund',
    'store.reconcile_order_payment',
  ],
  'Inventory Manager': [
    'store.view_category', 'store.view_product', 'store.view_inventorymovement',
    'store.view_vendor', 'store.view_vendorpurchase', 'store.adjust_stock',
    'store.receive_vendorpurchase',
  ],
  'Sales/Order Staff': [
    'store.view_dashboard', 'store.view_customerorder', 'store.change_order_fulfillment',
  ],
  'Payment Reviewer': [
    'store.verify_payment', 'store.confirm_refund', 'store.view_paymentrefund',
    'store.view_orderpaymentreconciliation',
  ],
  'Reports-only Staff': ['store.view_reports'],
};

function authorizationFor(permissions, isStaff = true) {
  return normalizeAuthorization({ user_id: 7, is_staff: isStaff, permissions });
}

test('all six provisioned staff permission sets produce only their allowed navigation', () => {
  const expected = {
    Administrator: [
      'dashboard', 'users', 'categories', 'products', 'orders', 'payment-review',
      'payment-config', 'stock', 'vendors', 'purchases', 'refunds', 'reconciliation',
      'reports', 'contacts', 'feedback',
    ],
    'Store Manager': [
      'dashboard', 'categories', 'products', 'orders', 'stock', 'vendors',
      'purchases', 'refunds', 'reconciliation', 'contacts', 'feedback',
    ],
    'Inventory Manager': ['categories', 'products', 'stock', 'vendors', 'purchases'],
    'Sales/Order Staff': ['dashboard', 'orders'],
    'Payment Reviewer': ['payment-review', 'refunds', 'reconciliation'],
    'Reports-only Staff': ['reports'],
  };

  for (const [role, permissions] of Object.entries(rolePermissions)) {
    const navigation = visibleNavigation(authorizationFor(permissions)).map((item) => item.key);
    assert.deepEqual(navigation, expected[role], role);
  }
});

test('permission-filtered navigation always includes a renderable icon for every staff role', () => {
  const icons = Object.fromEntries(
    STAFF_NAVIGATION.map(({ key }) => [key, { displayName: `${key} icon` }]),
  );

  for (const [role, permissions] of Object.entries(rolePermissions)) {
    const navigation = visibleNavigationWithIcons(authorizationFor(permissions), icons);
    assert.ok(navigation.length > 0, role);
    for (const item of navigation) {
      assert.equal(item.icon, icons[item.key], `${role}: ${item.key}`);
    }
  }
});

test('permission-filtered navigation fails explicitly when an icon mapping is missing', () => {
  const authorization = authorizationFor(rolePermissions['Sales/Order Staff']);
  const icons = { dashboard: { displayName: 'dashboard icon' } };

  assert.throws(
    () => visibleNavigationWithIcons(authorization, icons),
    /Missing navigation icon for "orders"/,
  );
});

test('missing and malformed permission data denies protected navigation and actions', () => {
  for (const payload of [null, {}, { is_staff: true, permissions: 'store.view_reports' }]) {
    const authorization = normalizeAuthorization(payload);
    assert.equal(authorization, null);
    assert.equal(canAccess(authorization, 'store.view_reports'), false);
    assert.deepEqual(visibleNavigation(authorization), []);
  }
  assert.equal(hasPermission(authorizationFor(['store.view_reports'], false), 'store.view_reports'), false);
  assert.equal(isAuthenticated(authorizationFor([], false), true), true);
  assert.equal(isAuthenticated(authorizationFor([], false), false), false);
  assert.equal(isStaffAccount(authorizationFor(['store.view_reports'])), true);
  assert.equal(firstAccessiblePath(authorizationFor([])), '/admin/access-denied');
});

test('direct staff routes enforce route permissions and customer order routes stay scoped', () => {
  const sales = authorizationFor(rolePermissions['Sales/Order Staff']);
  const routePermission = (path) => STAFF_NAVIGATION.find((item) => item.path === path)?.permissions;
  assert.equal(canAccess(sales, routePermission('/admin/orders')), true);
  assert.equal(canAccess(sales, routePermission('/admin/users')), false);
  assert.equal(canAccess(sales, routePermission('/admin/refunds')), false);

  assert.deepEqual(customerOrderRouteDecision(sales, false), {
    allowed: false, redirect: '/login',
  });
  assert.deepEqual(customerOrderRouteDecision(
    authorizationFor([], false), true,
  ), { allowed: true, redirect: null });
  assert.deepEqual(customerOrderRouteDecision(sales, true), {
    allowed: false, redirect: '/admin',
  });
});

test('actions use the precise permission for stock, fulfillment, receiving and refunds', () => {
  const manager = authorizationFor(rolePermissions['Store Manager']);
  const inventory = authorizationFor(rolePermissions['Inventory Manager']);
  const sales = authorizationFor(rolePermissions['Sales/Order Staff']);
  const reviewer = authorizationFor(rolePermissions['Payment Reviewer']);

  assert.equal(hasPermission(manager, RESOURCE_PERMISSIONS.products.adjustStock), false);
  assert.equal(hasPermission(inventory, RESOURCE_PERMISSIONS.products.adjustStock), true);
  assert.equal(hasPermission(sales, RESOURCE_PERMISSIONS.orders.fulfill), true);
  assert.equal(hasPermission(manager, RESOURCE_PERMISSIONS.orders.cancel), true);
  assert.equal(hasPermission(reviewer, RESOURCE_PERMISSIONS.orders.cancel), false);
  assert.equal(hasPermission(manager, RESOURCE_PERMISSIONS.orders.requestRefund), true);
  assert.equal(hasPermission(reviewer, 'store.confirm_refund'), true);
  assert.equal(hasPermission(inventory, RESOURCE_PERMISSIONS.purchases.receive), true);
});

test('reports-only staff can export ordinary reports but not payment verification reports', () => {
  const reportsOnly = authorizationFor(rolePermissions['Reports-only Staff']);
  const paymentReviewer = authorizationFor(rolePermissions['Payment Reviewer']);
  const administrator = authorizationFor(rolePermissions.Administrator);

  assert.equal(canAccessReport(reportsOnly, 'sales'), true);
  assert.equal(canAccessReport(reportsOnly, 'payment-verification'), false);
  assert.equal(canAccessReport(paymentReviewer, 'sales'), false);
  assert.equal(canAccessReport(administrator, 'payment-verification'), true);
});

test('HTTP authentication, permission, validation and server errors remain distinct', () => {
  const classify = (status) => classifyApiError({ response: { status } });
  assert.equal(classify(401), 'unauthenticated');
  assert.equal(classify(403), 'forbidden');
  assert.equal(classify(400), 'validation');
  assert.equal(classify(404), 'not-found');
  assert.equal(classify(503), 'server-error');
  assert.equal(shouldExpireSession({ response: { status: 401 } }), true);
  assert.equal(shouldExpireSession({ response: { status: 403 } }), false);
});
