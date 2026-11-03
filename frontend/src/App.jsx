import { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Armchair, Banknote, Boxes, ChartNoAxesCombined, ClipboardList, LayoutDashboard,
  LogOut, Menu, MessageSquare, Plus, RefreshCw, Search, Settings2, ShieldCheck,
  ShoppingBag, Star, Tags, Trash2, Truck, Users,
} from 'lucide-react';
import api from './api';
import { AuthorizationProvider, useAuthorization } from './auth/AuthorizationContext';
import { clearStoredAuth } from './auth/session';
import {
  canAccess, customerOrderRouteDecision, firstAccessiblePath, hasPermission, RESOURCE_PERMISSIONS,
  STAFF_NAVIGATION, visibleNavigationWithIcons,
} from './auth/authorization';
import Home from './pages/Home';
import ProductDetails from './pages/ProductDetails';
import Cart from './pages/cart';
import Checkout from './pages/Checkout';
import Login1 from './pages/Login1';
import Register from './pages/Register';
import UserOrders from './pages/UserOrders';
import OrderDetails from './pages/OrderDetails';
import About from './components/About';
import Contactus from './components/Contactus';
import PaymentReview from './pages/PaymentReview';
import PaymentConfiguration from './pages/PaymentConfiguration';
import ReportsPage from './pages/ReportsPage';
import './css/Payment.css';
import './css/ProductImageUpload.css';

const icons = {
  dashboard: LayoutDashboard,
  users: Users,
  categories: Tags,
  products: Armchair,
  orders: ClipboardList,
  'payment-review': Banknote,
  'payment-config': Settings2,
  stock: Boxes,
  vendors: Truck,
  purchases: ShoppingBag,
  refunds: Banknote,
  reconciliation: RefreshCw,
  reports: ChartNoAxesCombined,
  contacts: MessageSquare,
  feedback: Star,
};
const navigation = STAFF_NAVIGATION.map((item) => ({ ...item, icon: icons[item.key] }));
let fallbackRequestCounter = 0;

const resources = {
  users: {
    title: 'Manage Users', endpoint: 'users/',
    fields: [['username', 'Username', 'text', true], ['password', 'Password (required for new users)', 'password'], ['first_name', 'First name', 'text'], ['last_name', 'Last name', 'text'], ['email', 'Email', 'email']],
    columns: ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active'],
  },
  categories: {
    title: 'Manage Categories', endpoint: 'categories/',
    fields: [['name', 'Category name', 'text', true], ['description', 'Description', 'textarea']],
    columns: ['id', 'name', 'description'],
  },
  products: {
    title: 'Manage Products', endpoint: 'products/',
    fields: [['name', 'Product name', 'text', true], ['category', 'Category ID', 'number', true], ['vendor', 'Vendor ID (optional)', 'number'], ['description', 'Description', 'textarea'], ['price', 'Price (₹)', 'number', true], ['stock', 'Stock quantity', 'number', true], ['stock_reason', 'Stock adjustment reason', 'text'], ['image_url', 'Image URL', 'url'], ['is_active', 'Active', 'boolean']],
    columns: ['id', 'image', 'name', 'category_name', 'vendor_name', 'price', 'stock', 'is_active'],
  },
  vendors: {
    title: 'Vendor Information', endpoint: 'vendors/',
    fields: [['name', 'Vendor name', 'text', true], ['email', 'Email', 'email', true], ['phone', 'Phone', 'text'], ['address', 'Address', 'textarea'], ['is_active', 'Active', 'boolean']],
    columns: ['id', 'name', 'email', 'phone', 'address', 'is_active'],
  },
  purchases: {
    title: 'Vendor Purchases', endpoint: 'vendor-purchases/',
    fields: [['vendor', 'Vendor ID', 'number', true], ['product', 'Product ID', 'number', true], ['quantity', 'Quantity', 'number', true], ['unit_cost', 'Unit cost (₹)', 'number', true], ['status', 'Status', 'select', true, ['Requested', 'Approved', 'Rejected']]],
    columns: ['id', 'vendor_name', 'product_name', 'quantity', 'unit_cost', 'status', 'purchased_at', 'received_at'],
  },
  contacts: {
    title: 'Contact Us Messages', endpoint: 'contact-messages/',
    fields: [['name', 'Name', 'text', true], ['email', 'Email', 'email', true], ['subject', 'Subject', 'text'], ['message', 'Message', 'textarea', true]],
    columns: ['id', 'name', 'email', 'subject', 'message', 'created_at'],
  },
  feedback: {
    title: 'Customer Feedback', endpoint: 'feedback/',
    fields: [['name', 'Name', 'text'], ['email', 'Email', 'email'], ['rating', 'Rating (1–5)', 'number', true], ['comments', 'Comments', 'textarea', true]],
    columns: ['id', 'name', 'email', 'rating', 'comments', 'created_at'],
  },
};

function clearAuth() {
  clearStoredAuth();
  window.dispatchEvent(new Event('auth:changed'));
}

function errorText(error) {
  const data = error.response?.data;
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    return Object.entries(data).map(([field, messages]) => {
      const text = Array.isArray(messages) ? messages.join(' ') : typeof messages === 'string'
        ? messages : JSON.stringify(messages);
      return field === 'detail' ? text : `${field}: ${text}`;
    }).join(' ');
  }
  return error.message || 'The request could not be completed.';
}

function rowsFromResponse(response) {
  const data = response.data;
  return Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
}

function newRequestKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  if (!globalThis.crypto?.getRandomValues) {
    fallbackRequestCounter += 1;
    return `stock-${Date.now()}-${fallbackRequestCounter}`;
  }
  const values = new Uint8Array(16);
  globalThis.crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, '0')).join('');
}

function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const { reloadAuthorization } = useAuthorization();

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      const response = await api.post('auth/login/', { username, password });
      localStorage.setItem('access', response.data.access);
      localStorage.setItem('refresh', response.data.refresh);
      const authorization = await reloadAuthorization();
      if (!authorization?.isStaff || authorization.status !== 'ready') {
        clearAuth();
        throw new Error('This sign-in requires an authorized Django staff account and available permission data.');
      }
      localStorage.setItem('user', JSON.stringify(response.data.user || { username }));
      navigate(firstAccessiblePath(authorization), { replace: true });
    } catch (requestError) {
      clearAuth();
      setError(errorText(requestError) || 'Login failed. Check your credentials and staff access.');
    } finally {
      setBusy(false);
    }
  }

  return <div className="login-screen"><form className="login-card" onSubmit={submit}>
    <div className="brand-mark">CZ</div><p className="eyebrow">COMFORT ZONE</p><h1>Staff sign in</h1>
    <p className="muted">Sign in with your authorized Django staff account.</p>
    {error && <div className="error" role="alert">{error}</div>}
    <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required autoFocus /></label>
    <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
    <button className="primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in securely'}</button>
    <small>Access is determined by your current backend permissions.</small>
  </form></div>;
}

function AccessState({ unavailable = false, onRetry }) {
  return <div className="error" role="alert">
    {unavailable
      ? 'Staff permissions could not be verified. Restricted pages and actions remain unavailable.'
      : 'Your staff account does not have permission to access this section.'}
    {onRetry && <button type="button" className="text-button" onClick={onRetry}>Retry permission check</button>}
  </div>;
}

function RequirePermission({ permissions, children }) {
  const { authorization } = useAuthorization();
  if (authorization.status === 'loading') return <div className="empty-state" role="status">Checking staff permissions…</div>;
  if (authorization.status === 'unavailable') return <AccessState unavailable />;
  if (!canAccess(authorization, permissions)) return <AccessState />;
  return children;
}

function Shell() {
  const [mobile, setMobile] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { authorization } = useAuthorization();
  const visible = visibleNavigationWithIcons(authorization, icons);
  const active = visible.find((item) => location.pathname === item.path
    || (item.path !== '/admin' && location.pathname.startsWith(`${item.path}/`)));

  function logout() {
    clearStoredAuth();
    window.dispatchEvent(new Event('auth:logout'));
    navigate('/login', { replace: true });
  }

  return <div className="app-shell">
    <aside className={`sidebar ${mobile ? 'show' : ''}`}>
      <div className="brand"><div className="brand-mark">CZ</div><div><b>Comfort Zone</b><small>STAFF WORKSPACE</small></div></div>
      <div className="side-label">WORKSPACE</div>
      <nav aria-label="Staff navigation">{visible.map((item) => {
        const Icon = item.icon;
        return <button key={item.key} type="button" className={`nav-link ${active?.key === item.key ? 'active' : ''}`} aria-current={active?.key === item.key ? 'page' : undefined} onClick={() => { navigate(item.path); setMobile(false); }}>
          <Icon size={18} /><span>{item.label}</span>{item.key === 'stock' && <i className="nav-dot" />}
        </button>;
      })}</nav>
      <div className="sidebar-bottom"><div className="admin-avatar"><ShieldCheck size={19} /></div><div className="admin-copy"><b>{authorization.username || 'Staff account'}</b><small>Permission-verified access</small></div>
      </div>
    </aside>
    <main className="main-area"><header className="topbar">
      <button type="button" className="icon-button mobile-menu" aria-label="Toggle navigation" aria-expanded={mobile} onClick={() => setMobile((value) => !value)}><Menu /></button>
      <div className="crumb">Workspace <span>/</span> <b>{active?.label || 'Access'}</b></div><div className="top-actions"><span className="status-pill"><i /> System online</span><button type="button" className="secondary" onClick={logout} title="Sign out of the staff workspace"><LogOut size={16} /> Log out</button><div className="top-avatar" aria-hidden="true">S</div></div>
    </header><div className="page-wrap">
      <Routes>
        <Route index element={<RequirePermission permissions="store.view_dashboard"><Dashboard /></RequirePermission>} />
        <Route path="users" element={<RequirePermission permissions="auth.view_user"><ResourcePage resourceKey="users" /></RequirePermission>} />
        <Route path="categories" element={<RequirePermission permissions="store.view_category"><ResourcePage resourceKey="categories" /></RequirePermission>} />
        <Route path="products" element={<RequirePermission permissions="store.view_product"><ResourcePage resourceKey="products" /></RequirePermission>} />
        <Route path="orders" element={<RequirePermission permissions="store.view_customerorder"><OrderManagementPage /></RequirePermission>} />
        <Route path="payment-review" element={<RequirePermission permissions="store.verify_payment"><PaymentReview /></RequirePermission>} />
        <Route path="payment-configuration" element={<RequirePermission permissions="store.manage_payment_configuration"><PaymentConfiguration /></RequirePermission>} />
        <Route path="stock" element={<RequirePermission permissions={['store.view_product', 'store.view_inventorymovement']}><InventoryPage /></RequirePermission>} />
        <Route path="vendors" element={<RequirePermission permissions="store.view_vendor"><ResourcePage resourceKey="vendors" /></RequirePermission>} />
        <Route path="purchases" element={<RequirePermission permissions="store.view_vendorpurchase"><ResourcePage resourceKey="purchases" /></RequirePermission>} />
        <Route path="refunds" element={<RequirePermission permissions="store.view_paymentrefund"><RefundManagementPage /></RequirePermission>} />
        <Route path="reconciliation" element={<RequirePermission permissions="store.view_orderpaymentreconciliation"><ReconciliationPage /></RequirePermission>} />
        <Route path="reports" element={<RequirePermission permissions="store.view_reports"><ReportsPage authorization={authorization} canViewCategories={hasPermission(authorization, 'store.view_category')} canViewVendors={hasPermission(authorization, 'store.view_vendor')} /></RequirePermission>} />
        <Route path="contacts" element={<RequirePermission permissions="store.view_contactmessage"><ResourcePage resourceKey="contacts" /></RequirePermission>} />
        <Route path="feedback" element={<RequirePermission permissions="store.view_feedback"><ResourcePage resourceKey="feedback" /></RequirePermission>} />
        <Route path="access-denied" element={<AccessState />} />
        <Route path="*" element={<AccessState />} />
      </Routes>
    </div></main>
  </div>;
}

function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { authorization } = useAuthorization();
  const allowedNavigation = visibleNavigationWithIcons(authorization, icons);
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { const response = await api.get('dashboard/'); setStats(response.data); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const cards = [['Total users', 'users', Users], ['Product categories', 'categories', Tags], ['Active products', 'products', Armchair], ['Customer orders', 'orders', ClipboardList], ['Registered vendors', 'vendors', Truck], ['Low stock items', 'low_stock', Boxes]];

  return <>
    <div className="page-heading"><div><p className="eyebrow">OVERVIEW</p><h1>Dashboard</h1><p className="muted">Here’s what’s happening in your furniture store today.</p></div>
      <button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={16} />{loading ? 'Refreshing…' : 'Refresh statistics'}</button>
    </div>
    {error && <div className="error" role="alert">{error}<button type="button" className="text-button" onClick={load}>Try again</button></div>}
    <div className="stats-grid" aria-busy={loading}>{cards.map(([label, key, Icon], index) => <div className="stat-card" key={key}>
      <div className={`stat-icon icon-${index}`}><Icon size={20} /></div><p>{label}</p><strong>{loading ? '…' : (stats?.[key] ?? '—')}</strong><small>{key === 'low_stock' ? 'At or below 5 units' : 'Live database count'}</small>
    </div>)}</div>
    <div className="welcome-panel"><div><p className="eyebrow">STORE CONTROL CENTER</p><h2>Good work starts with a clear view.</h2><p>Use the menu to manage the store areas available to your account.</p></div><div className="welcome-art"><Armchair size={76} strokeWidth={1.2} /><span>DESIGNED FOR COMFORT</span></div></div>
    <div className="quick-grid">{allowedNavigation.filter((item) => item.key !== 'dashboard').slice(0, 4).map((item) => <button type="button" key={item.key} onClick={() => navigate(item.path)} className="quick-link"><item.icon size={18} /><span>Open {item.label}</span><b>↗</b></button>)}</div>
  </>;
}

function ResourcePage({ resourceKey }) {
  const config = resources[resourceKey];
  const rights = RESOURCE_PERMISSIONS[resourceKey];
  const { authorization } = useAuthorization();
  const can = (permission) => hasPermission(authorization, permission);
  const fields = useMemo(() => config.fields.filter(([key]) => (
    key !== 'stock' && key !== 'stock_reason'
      ? true
      : can('store.adjust_stock')
  )), [config, authorization]);
  const blank = useMemo(() => Object.fromEntries(fields.map(([key, , type, , options]) => [
    key, type === 'boolean' ? true : type === 'select' ? options[0] : '',
  ])), [fields]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(blank);
  const [stockRequestKey, setStockRequestKey] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState('');
  const canDelete = can(rights.delete) && (!rights.deleteExtra || can(rights.deleteExtra));

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setRows(rowsFromResponse(await api.get(config.endpoint))); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, [config.endpoint]);
  useEffect(() => { setShowForm(false); setEditingId(null); setForm(blank); void load(); }, [blank, load]);
  useEffect(() => () => {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
  }, [imagePreview]);

  function change(key, value) {
    if (key === 'stock' || key === 'stock_reason') setStockRequestKey('');
    setForm((current) => ({ ...current, [key]: value }));
  }
  function startAdd() {
    setEditingId(null);
    setStockRequestKey('');
    setImageFile(null);
    setImagePreview('');
    setForm(blank);
    setShowForm(true);
  }
  function startEdit(row) {
    setEditingId(row.id);
    setStockRequestKey('');
    setImageFile(null);
    setImagePreview('');
    setForm(Object.fromEntries(fields.map(([key]) => [key, row[key] ?? ''])));
    setShowForm(true);
  }
  function selectProductImage(event) {
    const file = event.target.files?.[0] || null;
    if (file && !/\.(jpe?g|png|webp)$/i.test(file.name)) {
      setError('Choose a JPEG, PNG, or WebP product image.');
      event.target.value = '';
      setImageFile(null);
      setImagePreview('');
      return;
    }
    if (file && file.size > 5 * 1024 * 1024) {
      setError('Product images must be 5 MB or smaller.');
      event.target.value = '';
      setImageFile(null);
      setImagePreview('');
      return;
    }
    setError('');
    setImageFile(file);
    setImagePreview(file ? URL.createObjectURL(file) : '');
  }
  async function save(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    const payload = { ...form };
    fields.forEach(([key, , type]) => {
      if (type === 'number' && payload[key] !== '' && payload[key] !== null) payload[key] = Number(payload[key]);
      if (type === 'number' && payload[key] === '') {
        if (editingId !== null && key === 'vendor') payload[key] = null;
        else delete payload[key];
      }
      if (type === 'boolean') payload[key] = Boolean(payload[key]);
      if (payload[key] === '') {
        if (editingId !== null && key === 'vendor') payload[key] = null;
        else if (key === 'stock_reason') delete payload[key];
        else if (editingId === null || key === 'password') delete payload[key];
      }
    });
    const stockChanged = resourceKey === 'products' && Object.hasOwn(payload, 'stock')
      && (editingId === null
        ? Number(payload.stock) > 0
        : Number(payload.stock) !== Number(rows.find((row) => row.id === editingId)?.stock));
    if (stockChanged) {
      const requestKey = stockRequestKey || newRequestKey();
      payload.stock_source_key = requestKey;
      setStockRequestKey(requestKey);
    }
    try {
      let requestPayload = payload;
      if (resourceKey === 'products' && imageFile) {
        requestPayload = new FormData();
        Object.entries(payload).forEach(([key, value]) => requestPayload.append(key, value));
        requestPayload.append('image', imageFile);
      }
      if (editingId === null) await api.post(config.endpoint, requestPayload);
      else await api.patch(`${config.endpoint}${editingId}/`, requestPayload);
      setShowForm(false);
      setEditingId(null);
      setStockRequestKey('');
      setImageFile(null);
      setImagePreview('');
      await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setSaving(false); }
  }
  async function remove(row) {
    if (busyAction || !window.confirm(`Delete record #${row.id}? This action cannot be undone.`)) return;
    setBusyAction(String(row.id));
    setError('');
    try { await api.delete(`${config.endpoint}${row.id}/`); await load(); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setBusyAction(''); }
  }
  async function receive(row) {
    if (busyAction || row.status !== 'Approved') return;
    if (!window.confirm(`Receive purchase #${row.id}? This records the receipt and increases product stock by ${row.quantity}. It cannot be received twice.`)) return;
    setBusyAction(String(row.id));
    setError('');
    try { await api.post(`${config.endpoint}${row.id}/receive/`); await load(); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setBusyAction(''); }
  }
  const filtered = useMemo(() => rows.filter((row) => Object.values(row).join(' ').toLowerCase().includes(query.toLowerCase())), [rows, query]);
  const canCreate = can(rights.create);
  const canEdit = can(rights.edit);

  return <>
    <div className="page-heading"><div><p className="eyebrow">STORE MANAGEMENT</p><h1>{config.title}</h1><p className="muted">View and maintain records allowed by your staff permissions.</p></div>
      {canCreate && <button type="button" className="primary" onClick={startAdd}><Plus size={17} /> Add new</button>}
    </div>
    {error && <div className="error" role="alert">{error}</div>}
    {showForm && <section className="form-panel"><div className="panel-head"><div><h2>{editingId === null ? 'Add record' : `Edit record #${editingId}`}</h2><p className="muted">Changes are validated by the store API.</p></div>
      <button type="button" className="text-button" onClick={() => { setShowForm(false); setEditingId(null); }}>Cancel</button>
    </div><form onSubmit={save} className="record-form">{fields.map(([key, label, type, required, options]) => <label key={key} className={type === 'textarea' ? 'wide-field' : ''}>{label}
      {type === 'textarea' ? <textarea value={form[key] ?? ''} required={Boolean(required)} onChange={(event) => change(key, event.target.value)} />
        : type === 'select' ? <select value={form[key] ?? ''} required={Boolean(required)} onChange={(event) => change(key, event.target.value)}>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select>
          : type === 'boolean' ? <input type="checkbox" checked={Boolean(form[key])} onChange={(event) => change(key, event.target.checked)} />
            : <input type={type} value={form[key] ?? ''} min={type === 'number' ? '0' : undefined} step={['price', 'unit_cost'].includes(key) ? '0.01' : type === 'number' ? '1' : undefined} required={Boolean(required) || (key === 'password' && editingId === null) || (key === 'stock_reason' && (editingId === null ? Number(form.stock) > 0 : Number(form.stock) !== Number(rows.find((row) => row.id === editingId)?.stock)))} onChange={(event) => change(key, event.target.value)} />}
    </label>)}{resourceKey === 'products' && <div className="product-image-upload wide-field"><label>Product image (JPEG, PNG or WebP; maximum 5 MB)<input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={selectProductImage} /></label>{(imagePreview || (editingId !== null && rows.find((row) => row.id === editingId)?.image) || form.image_url) && <img className="product-image-preview" src={imagePreview || (editingId !== null && rows.find((row) => row.id === editingId)?.image) || form.image_url} alt="Product image preview" />}</div>}<div className="form-actions"><button type="button" className="secondary" onClick={() => { setShowForm(false); setEditingId(null); setImageFile(null); setImagePreview(''); }}>Cancel</button><button className="primary" disabled={saving}>{saving ? 'Saving…' : editingId === null ? 'Create record' : 'Save changes'}</button></div></form></section>}
    <section className="table-panel"><div className="table-toolbar"><div><h2>Records</h2><p className="muted">{filtered.length} record{filtered.length === 1 ? '' : 's'} found</p></div><div className="toolbar-actions"><div className="search-box"><Search size={16} /><input aria-label="Search records" placeholder="Search records…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><button type="button" className="icon-button" onClick={load} disabled={loading} title="Refresh" aria-label="Refresh records"><RefreshCw size={17} /></button></div></div>
      <div className="table-scroll">{loading ? <div className="empty-state" role="status">Loading records…</div> : filtered.length === 0 ? <div className="empty-state">No records found.</div> : <table><thead><tr>{config.columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}{(canEdit || canDelete || (resourceKey === 'purchases' && can(rights.receive))) && <th>Actions</th>}</tr></thead><tbody>{filtered.map((row) => <tr key={row.id}>{config.columns.map((column) => <td key={column}>{column === 'image' ? formatCell(row.image || row.image_url, column) : formatCell(row[column], column)}</td>)}{(canEdit || canDelete || (resourceKey === 'purchases' && can(rights.receive))) && <td className="row-actions">
        {canEdit && !(resourceKey === 'purchases' && row.status === 'Received') && <button type="button" className="edit-button" disabled={Boolean(busyAction)} onClick={() => startEdit(row)} aria-label={`Edit record ${row.id}`}>Edit</button>}
        {resourceKey === 'purchases' && can(rights.receive) && row.status === 'Approved' && <button type="button" className="edit-button" disabled={Boolean(busyAction)} onClick={() => receive(row)}>{busyAction === String(row.id) ? 'Receiving…' : 'Receive stock'}</button>}
        {canDelete && resourceKey !== 'purchases' && <button type="button" className="delete-button" disabled={Boolean(busyAction)} onClick={() => remove(row)} title="Delete record" aria-label={`Delete record ${row.id}`}><Trash2 size={16} /></button>}
      </td>}</tr>)}</tbody></table>}</div>
    </section>
    {resourceKey === 'users' && <p className="footnote">This API manages ordinary accounts only. Staff status and group/role assignments are not editable here.</p>}
    {resourceKey === 'purchases' && <p className="footnote">Received purchases are immutable and can never be received a second time.</p>}
  </>;
}

function formatCell(value, key) {
  if (value === true) return <span className="badge success">Yes</span>;
  if (value === false) return <span className="badge muted-badge">No</span>;
  if (value === null || value === undefined || value === '') return '—';
  if (key === 'image') return <img className="product-image-thumbnail" src={value} alt="" />;
  if (key.includes('amount') || key === 'price' || key === 'unit_cost') return `₹${value}`;
  if (key.endsWith('_at')) return String(value).replace('T', ' ').slice(0, 16);
  if (typeof value === 'string' && value.length > 65) return `${value.slice(0, 65)}…`;
  return String(value);
}

function OrderManagementPage() {
  const { authorization } = useAuthorization();
  const navigate = useNavigate();
  const can = (permission) => hasPermission(authorization, permission);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [cancelling, setCancelling] = useState(null);
  const [reason, setReason] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try { setOrders(rowsFromResponse(await api.get('orders/'))); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function fulfill(order) {
    const next = { Pending: 'Processing', Processing: 'Shipped', Shipped: 'Delivered' }[order.status];
    if (!next || busyId) return;
    setBusyId(String(order.id));
    setError('');
    try { await api.patch(`orders/${order.id}/`, { status: next }); await load(); }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setBusyId(''); }
  }
  async function cancelOrder(event) {
    event.preventDefault();
    if (!cancelling || !reason.trim() || busyId) return;
    setBusyId(String(cancelling.id));
    setError('');
    try {
      await api.post(`orders/${cancelling.id}/cancel/`, { reason: reason.trim() });
      setCancelling(null);
      setReason('');
      await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setBusyId(''); }
  }

  return <div>
    <div className="page-heading"><div><p className="eyebrow">ORDER OPERATIONS</p><h1>Manage Orders</h1><p className="muted">Order and customer snapshots are read-only; fulfillment follows the authorized workflow.</p></div><button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={16} />{loading ? 'Refreshing…' : 'Refresh orders'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    <section className="table-panel"><div className="table-scroll">{loading ? <div className="empty-state" role="status">Loading orders…</div> : !orders.length ? <div className="empty-state">No customer orders found.</div> : <table><thead><tr><th>Order</th><th>Customer</th><th>Total</th><th>Payment</th><th>Fulfillment</th><th>Actions</th></tr></thead><tbody>{orders.map((order) => {
      const next = { Pending: 'Processing', Processing: 'Shipped', Shipped: 'Delivered' }[order.status];
      const cancelBlock = order.status === 'Shipped' || order.status === 'Delivered'
        ? 'Shipped or delivered orders cannot be cancelled.'
        : order.payment_status === 'Paid'
          ? 'A verified receipt or confirmed-paid reconciliation and full confirmed refund are required.'
          : order.payment_status === null
            ? 'Legacy payment status must be reconciled before cancellation.'
            : order.payment_status === 'Pending'
              ? 'Any pending payment attempt must be resolved before cancellation.'
              : '';
      return <tr key={order.id}><td>#{order.id}<br /><small>{order.order_reference || 'Legacy order'}</small></td><td>{order.customer_name}<br /><small>{order.customer_email}</small></td><td>₹{order.total_amount}</td><td>{order.payment_status || 'Legacy / unresolved'}</td><td>{order.status}</td><td className="row-actions">
        {next && can('store.change_order_fulfillment') && <button type="button" className="edit-button" disabled={Boolean(busyId)} onClick={() => fulfill(order)}>{busyId === String(order.id) ? 'Saving…' : `Mark ${next}`}</button>}
        {can('store.request_refund') && order.payment_status === 'Paid' && <button type="button" className="edit-button" onClick={() => navigate(`/admin/refunds?order=${order.id}`)}>Request refund</button>}
        {can('store.cancel_customerorder') && !['Cancelled', 'Shipped', 'Delivered'].includes(order.status) && <button type="button" className="delete-button" disabled={Boolean(busyId)} onClick={() => { setCancelling(order); setReason(''); }}>Cancel order</button>}
        {cancelBlock && can('store.cancel_customerorder') && order.status !== 'Cancelled' && <small title={cancelBlock}>{cancelBlock}</small>}
      </td></tr>;
    })}</tbody></table>}</div></section>
    {cancelling && <div className="payment-dialog-backdrop"><form className="payment-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="cancel-order-title" onSubmit={cancelOrder}>
      <h2 id="cancel-order-title">Cancel order #{cancelling.id}?</h2>
      <p>The backend verifies pending payment attempts, reconciliation, refund completion, and fulfillment status before changing the order or restoring stock.</p>
      <label>Cancellation reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} required maxLength={2000} rows={4} /></label>
      <div className="form-actions"><button type="button" className="secondary" disabled={Boolean(busyId)} onClick={() => setCancelling(null)}>Keep order</button><button type="submit" className="payment-reject-button" disabled={!reason.trim() || Boolean(busyId)}>{busyId ? 'Submitting…' : 'Confirm cancellation'}</button></div>
    </form></div>}
  </div>;
}

function RefundManagementPage() {
  const { authorization } = useAuthorization();
  const canRequest = hasPermission(authorization, 'store.request_refund');
  const canReview = hasPermission(authorization, 'store.confirm_refund');
  const location = useLocation();
  const [refunds, setRefunds] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [orderId, setOrderId] = useState(() => new URLSearchParams(location.search).get('order') || '');
  const [amount, setAmount] = useState('');
  const [requestReason, setRequestReason] = useState('');
  const [review, setReview] = useState(null);
  const [reference, setReference] = useState('');
  const [remarks, setRemarks] = useState('');
  const [busyId, setBusyId] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('admin/refunds/', { params: { page } });
      setRefunds(rowsFromResponse(response));
      setTotalPages(response.data.total_pages || 1);
      setTotalCount(response.data.count || 0);
    }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, [page]);
  useEffect(() => { void load(); }, [load]);

  async function requestRefund(event) {
    event.preventDefault();
    if (saving || !canRequest || !orderId || !Number.isFinite(Number(amount)) || Number(amount) <= 0 || !requestReason.trim()) return;
    setSaving(true);
    setError('');
    try {
      await api.post(`admin/orders/${Number(orderId)}/refunds/`, {
        amount: Number(amount).toFixed(2), reason: requestReason.trim(),
      });
      setAmount('');
      setRequestReason('');
      if (page !== 1) setPage(1);
      else await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setSaving(false); }
  }
  async function reviewRefund(event) {
    event.preventDefault();
    if (!review || saving || !remarks.trim() || (review.decision === 'confirm' && !reference.trim())) return;
    setSaving(true);
    setBusyId(String(review.refund.id));
    setError('');
    try {
      const payload = { remarks: remarks.trim() };
      if (review.decision === 'confirm') payload.manual_transaction_reference = reference.trim();
      await api.post(`admin/refunds/${review.refund.id}/${review.decision}/`, payload);
      setReview(null);
      setReference('');
      setRemarks('');
      if (page !== 1) setPage(1);
      else await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setSaving(false); setBusyId(''); }
  }

  return <div>
    <div className="page-heading"><div><p className="eyebrow">PAYMENT OPERATIONS</p><h1>Refunds</h1><p className="muted">Refund requests and reviewer decisions remain in the audit history.</p></div><button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={16} />{loading ? 'Refreshing…' : 'Refresh refunds'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    {canRequest && <form className="form-panel record-form" onSubmit={requestRefund}>
      <h2>Request manual refund</h2>
      <label>Order ID<input type="number" min="1" value={orderId} onChange={(event) => setOrderId(event.target.value)} required /></label>
      <label>Amount (₹)<input type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required /></label>
      <label className="wide-field">Reason<textarea maxLength={2000} value={requestReason} onChange={(event) => setRequestReason(event.target.value)} required /></label>
      <div className="form-actions"><button type="submit" className="primary" disabled={saving || !orderId || !amount || !requestReason.trim()}>{saving ? 'Submitting…' : 'Submit refund request'}</button></div>
    </form>}
    <section className="table-panel"><div className="table-toolbar"><div><h2>Refund history</h2><p className="muted">{totalCount} recorded request{totalCount === 1 ? '' : 's'}</p></div></div>
      {loading ? <div className="empty-state" role="status">Loading refund history…</div> : !refunds.length ? <div className="empty-state">No refund requests recorded.</div> : <div className="table-scroll"><table><thead><tr><th>Order</th><th>Amount</th><th>Status</th><th>Reason</th><th>Payment history</th><th>Review</th></tr></thead><tbody>{refunds.map((refund) => {
        const ownRequest = refund.requested_by_id === authorization.userId;
        const mayReview = canReview && refund.status === 'Pending' && !ownRequest;
        return <tr key={refund.id}><td>{refund.order_reference || `#${refund.order_id}`}</td><td>₹{refund.amount}</td><td><span className={`badge ${refund.status === 'Confirmed' ? 'success' : 'muted-badge'}`}>{refund.status}</span></td><td>{refund.reason}<br /><small>Requested by account #{refund.requested_by_id}</small></td><td>{refund.source_payment ? <>{refund.source_payment.kind} · ₹{refund.source_payment.amount}<br /><small>{refund.source_payment.reference}</small>{refund.source_payment.receipt_number && <><br /><small>Receipt {refund.source_payment.receipt_number}</small></>}</> : 'Confirmed through reconciliation'}<br /><small>{refund.manual_transaction_reference || 'No refund reference yet'}</small></td><td>{mayReview ? <><button type="button" className="edit-button" disabled={Boolean(busyId)} onClick={() => { setReview({ refund, decision: 'confirm' }); setReference(''); setRemarks(''); }}>Confirm</button><button type="button" className="delete-button" disabled={Boolean(busyId)} onClick={() => { setReview({ refund, decision: 'reject' }); setRemarks(''); }}>Reject</button></> : ownRequest && canReview && refund.status === 'Pending' ? <small>You cannot review your own request.</small> : refund.reviewer_remarks || '—'}</td></tr>;
      })}</tbody></table></div>}
      <div className="report-pagination"><span>Page {page} of {totalPages}</span><div><button type="button" className="secondary" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" className="secondary" disabled={loading || page >= totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
    </section>
    {review && <div className="payment-dialog-backdrop"><form className="payment-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="refund-review-title" onSubmit={reviewRefund}>
      <h2 id="refund-review-title">{review.decision === 'confirm' ? 'Confirm manual refund' : 'Reject refund request'}</h2>
      <p>{review.decision === 'confirm'
        ? `Confirm that ₹${review.refund.amount} was manually refunded for order ${review.refund.order_reference || `#${review.refund.order_id}`}. This records the reviewer and transaction reference.`
        : `Reject the pending refund request for order ${review.refund.order_reference || `#${review.refund.order_id}`}. The decision and remarks are retained.`}</p>
      {review.decision === 'confirm' && <label>Manual transaction reference<input value={reference} onChange={(event) => setReference(event.target.value)} maxLength={128} required /></label>}
      <label>Reviewer remarks<textarea value={remarks} onChange={(event) => setRemarks(event.target.value)} maxLength={2000} rows={3} required /></label>
      <div className="form-actions"><button type="button" className="secondary" disabled={saving} onClick={() => setReview(null)}>Back</button><button type="submit" className={review.decision === 'confirm' ? 'primary' : 'payment-reject-button'} disabled={saving || !remarks.trim() || (review.decision === 'confirm' && !reference.trim())}>{saving ? 'Submitting…' : `Confirm ${review.decision}`}</button></div>
    </form></div>}
  </div>;
}

function ReconciliationPage() {
  const { authorization } = useAuthorization();
  const mayReconcile = hasPermission(authorization, 'store.reconcile_order_payment');
  const [events, setEvents] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ orderId: '', outcome: 'Unknown', confirmedAmount: '', reason: '', evidence: '' });
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('admin/payment-reconciliations/', { params: { page } });
      setEvents(rowsFromResponse(response));
      setTotalPages(response.data.total_pages || 1);
      setTotalCount(response.data.count || 0);
    }
    catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, [page]);
  useEffect(() => { void load(); }, [load]);
  function update(key, value) { setForm((current) => ({ ...current, [key]: value })); }
  async function submit(event) {
    event.preventDefault();
    if (saving || !mayReconcile || !form.orderId || !form.reason.trim() || !form.evidence.trim()) return;
    if (form.outcome === 'Paid' && (!Number.isFinite(Number(form.confirmedAmount)) || Number(form.confirmedAmount) <= 0)) return;
    setSaving(true);
    setError('');
    const payload = {
      outcome: form.outcome,
      reason: form.reason.trim(),
      evidence_reference: form.evidence.trim(),
    };
    if (form.outcome === 'Paid') payload.confirmed_amount = Number(form.confirmedAmount).toFixed(2);
    try {
      await api.post(`admin/orders/${Number(form.orderId)}/payment-reconciliation/`, payload);
      setForm({ orderId: '', outcome: 'Unknown', confirmedAmount: '', reason: '', evidence: '' });
      if (page !== 1) setPage(1);
      else await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setSaving(false); }
  }

  return <div>
    <div className="page-heading"><div><p className="eyebrow">PAYMENT OPERATIONS</p><h1>Payment reconciliation</h1><p className="muted">Review recorded evidence and outcomes for legacy or exceptional payment states.</p></div><button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={16} />{loading ? 'Refreshing…' : 'Refresh history'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    {mayReconcile && <form className="form-panel record-form" onSubmit={submit}>
      <h2>Record reconciliation decision</h2>
      <label>Order ID<input type="number" min="1" value={form.orderId} onChange={(event) => update('orderId', event.target.value)} required /></label>
      <label>Decision<select value={form.outcome} onChange={(event) => update('outcome', event.target.value)}><option value="Unknown">Unknown</option><option value="Unpaid">Confirmed unpaid</option><option value="Paid">Confirmed paid</option></select></label>
      {form.outcome === 'Paid' && <label>Confirmed amount (₹)<input type="number" min="0.01" step="0.01" value={form.confirmedAmount} onChange={(event) => update('confirmedAmount', event.target.value)} required /></label>}
      <label className="wide-field">Reason<textarea maxLength={2000} value={form.reason} onChange={(event) => update('reason', event.target.value)} required /></label>
      <label className="wide-field">Evidence reference<input maxLength={255} value={form.evidence} onChange={(event) => update('evidence', event.target.value)} required /></label>
      <div className="form-actions"><button type="submit" className="primary" disabled={saving || !form.orderId || !form.reason.trim() || !form.evidence.trim() || (form.outcome === 'Paid' && !form.confirmedAmount)}>{saving ? 'Saving…' : 'Record decision'}</button></div>
    </form>}
    <section className="table-panel"><div className="table-toolbar"><div><h2>Reconciliation history</h2><p className="muted">{totalCount} recorded decision{totalCount === 1 ? '' : 's'}</p></div></div>
      {loading ? <div className="empty-state" role="status">Loading reconciliation history…</div> : !events.length ? <div className="empty-state">No reconciliation decisions recorded.</div> : <div className="table-scroll"><table><thead><tr><th>Order</th><th>Decision</th><th>Amount</th><th>Reason</th><th>Evidence reference</th><th>Recorded by</th><th>Date</th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td>{event.order_reference || `#${event.order_id}`}</td><td>{event.outcome}</td><td>{event.confirmed_amount ? `₹${event.confirmed_amount}` : '—'}</td><td>{event.reason}</td><td>{event.evidence_reference}</td><td>{event.actor}</td><td>{formatCell(event.reconciled_at, 'reconciled_at')}</td></tr>)}</tbody></table></div>}
      <div className="report-pagination"><span>Page {page} of {totalPages}</span><div><button type="button" className="secondary" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" className="secondary" disabled={loading || page >= totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
    </section>
  </div>;
}

function InventoryPage() {
  const { authorization } = useAuthorization();
  const mayAdjust = hasPermission(authorization, 'store.adjust_stock');
  const [products, setProducts] = useState([]);
  const [movements, setMovements] = useState([]);
  const [movementPage, setMovementPage] = useState(1);
  const [movementPages, setMovementPages] = useState(1);
  const [movementCount, setMovementCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [target, setTarget] = useState(null);
  const [stock, setStock] = useState('');
  const [reason, setReason] = useState('');
  const [stockSourceKey, setStockSourceKey] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [productResponse, movementResponse] = await Promise.all([
        api.get('products/'),
        api.get('admin/inventory-movements/', { params: { page: movementPage } }),
      ]);
      setProducts(rowsFromResponse(productResponse));
      setMovements(rowsFromResponse(movementResponse));
      setMovementPages(movementResponse.data.total_pages || 1);
      setMovementCount(movementResponse.data.count || 0);
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setLoading(false); }
  }, [movementPage]);
  useEffect(() => { void load(); }, [load]);
  async function saveAdjustment(event) {
    event.preventDefault();
    if (!target || saving || !reason.trim() || !Number.isInteger(Number(stock)) || Number(stock) < 0) return;
    setSaving(true);
    setError('');
    try {
      await api.patch(`products/${target.id}/`, {
        stock: Number(stock), stock_reason: reason.trim(), stock_source_key: stockSourceKey,
      });
      setTarget(null);
      setReason('');
      setStockSourceKey('');
      if (movementPage !== 1) setMovementPage(1);
      else await load();
    } catch (requestError) { setError(errorText(requestError)); }
    finally { setSaving(false); }
  }

  return <div>
    <div className="page-heading"><div><p className="eyebrow">INVENTORY OPERATIONS</p><h1>Inventory &amp; movements</h1><p className="muted">Stock balances are updated only after the backend confirms a recorded movement.</p></div><button type="button" className="secondary" onClick={load} disabled={loading}><RefreshCw size={16} />{loading ? 'Refreshing…' : 'Refresh inventory'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    <section className="table-panel"><div className="table-toolbar"><div><h2>Product stock</h2><p className="muted">{products.length} products</p></div></div>
      {loading ? <div className="empty-state" role="status">Loading inventory…</div> : !products.length ? <div className="empty-state">No products found.</div> : <div className="table-scroll"><table><thead><tr><th>Product</th><th>Category</th><th>Available stock</th>{mayAdjust && <th>Action</th>}</tr></thead><tbody>{products.map((product) => <tr key={product.id}><td>{product.name}</td><td>{product.category_name}</td><td>{product.stock}</td>      {mayAdjust && <td><button type="button" className="edit-button" onClick={() => { setTarget(product); setStock(String(product.stock)); setReason(''); setStockSourceKey(newRequestKey()); }}>Adjust stock</button></td>}</tr>)}</tbody></table></div>}
    </section>
    <section className="table-panel"><div className="table-toolbar"><div><h2>Stock movement history</h2><p className="muted">{movementCount} recorded movement{movementCount === 1 ? '' : 's'}</p></div></div>
      {!loading && !movements.length ? <div className="empty-state">No stock movements recorded.</div> : movements.length > 0 && <div className="table-scroll"><table><thead><tr><th>Date</th><th>Product</th><th>Movement</th><th>Quantity</th><th>Balance after</th><th>Source</th><th>Actor</th><th>Reason</th></tr></thead><tbody>{movements.map((movement) => <tr key={movement.id}><td>{formatCell(movement.created_at, 'created_at')}</td><td>{movement.product_name}</td><td>{movement.movement_type} ({movement.direction})</td><td>{movement.quantity}</td><td>{movement.resulting_stock}</td><td>{movement.order_id ? `Order #${movement.order_id}` : movement.vendor_purchase_id ? `Purchase #${movement.vendor_purchase_id}` : 'Adjustment'}</td><td>{movement.actor || 'System'}</td><td>{movement.reason}</td></tr>)}</tbody></table></div>}
      <div className="report-pagination"><span>Page {movementPage} of {movementPages}</span><div><button type="button" className="secondary" disabled={loading || movementPage <= 1} onClick={() => setMovementPage((value) => value - 1)}>Previous</button><button type="button" className="secondary" disabled={loading || movementPage >= movementPages} onClick={() => setMovementPage((value) => value + 1)}>Next</button></div></div>
    </section>
    {target && <div className="payment-dialog-backdrop"><form className="payment-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="stock-adjust-title" onSubmit={saveAdjustment}>
      <h2 id="stock-adjust-title">Adjust {target.name} stock</h2><p>This records an auditable stock movement. The displayed balance changes only after confirmation by the server.</p>
      <label>Target stock<input type="number" min="0" step="1" value={stock} onChange={(event) => { setStock(event.target.value); setStockSourceKey(newRequestKey()); }} required /></label>
      <label>Reason<textarea maxLength={255} value={reason} onChange={(event) => { setReason(event.target.value); setStockSourceKey(newRequestKey()); }} required rows={3} /></label>
      <div className="form-actions"><button type="button" className="secondary" disabled={saving} onClick={() => setTarget(null)}>Cancel</button><button className="primary" type="submit" disabled={saving || !reason.trim() || !Number.isInteger(Number(stock))}>{saving ? 'Saving…' : 'Record adjustment'}</button></div>
    </form></div>}
  </div>;
}

function AdminApplication() {
  const { authorization, reloadAuthorization } = useAuthorization();
  const location = useLocation();
  if (location.pathname === '/admin/login') {
    if (authorization.status === 'loading') return <div className="empty-state" role="status">Checking staff session…</div>;
    if (authorization.status === 'ready' && authorization.isStaff) return <Navigate to={firstAccessiblePath(authorization)} replace />;
    return <Login />;
  }
  if (!localStorage.getItem('access')) return <Navigate to="/login" replace />;
  if (authorization.status === 'loading') return <div className="empty-state" role="status">Checking staff permissions…</div>;
  if (authorization.status === 'unavailable') return <div className="page-wrap"><AccessState unavailable onRetry={reloadAuthorization} /></div>;
  if (!authorization.isStaff) return <div className="page-wrap"><AccessState /></div>;
  return <Shell />;
}

function CustomerRoute({ children }) {
  const location = useLocation();
  const { authorization } = useAuthorization();
  const decision = customerOrderRouteDecision(authorization, Boolean(localStorage.getItem('access')));
  if (!decision.allowed) {
    return <Navigate to={decision.redirect} replace state={decision.redirect === '/login'
      ? { from: `${location.pathname}${location.search}` } : undefined} />;
  }
  return children;
}

function ApplicationRoutes() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const onAuthExpired = () => {
      const adminPath = location.pathname.startsWith('/admin');
      navigate(adminPath ? '/admin/login' : '/login', {
        replace: true,
        state: { from: adminPath ? undefined : `${location.pathname}${location.search}`, message: 'Your session expired. Please sign in again.' },
      });
    };
    window.addEventListener('auth:expired', onAuthExpired);
    return () => window.removeEventListener('auth:expired', onAuthExpired);
  }, [location.pathname, location.search, navigate]);
  return <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/about" element={<About />} />
    <Route path="/contact" element={<Contactus />} />
    <Route path="/product/:id" element={<ProductDetails />} />
    <Route path="/products" element={<Home />} />
    <Route path="/cart" element={<Cart />} />
    <Route path="/checkout" element={<Checkout />} />
    <Route path="/login" element={<Login1 />} />
    <Route path="/register" element={<Register />} />
    <Route path="/account/orders" element={<CustomerRoute><UserOrders /></CustomerRoute>} />
    <Route path="/account/orders/:id" element={<CustomerRoute><OrderDetails /></CustomerRoute>} />
    <Route path="/user/orders" element={<Navigate to="/account/orders" replace />} />
    <Route path="/admin/*" element={<AdminApplication />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}

export default function App() {
  return <AuthorizationProvider><ApplicationRoutes /></AuthorizationProvider>;
}
