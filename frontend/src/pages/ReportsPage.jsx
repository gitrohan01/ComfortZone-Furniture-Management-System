import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, RefreshCw, Search } from 'lucide-react';
import api from '../api';
import { canAccessReport } from '../auth/authorization';
import '../css/Reports.css';

const REPORTS = [
  { key: 'sales', label: 'Sales', endpoint: 'sales/', export: 'sales/export/', dates: true },
  { key: 'orders', label: 'Orders', endpoint: 'orders/', export: 'orders/export/', dates: true },
  { key: 'inventory', label: 'Inventory', endpoint: 'inventory/', export: 'inventory/export/', dates: false },
  { key: 'low-stock', label: 'Low stock', endpoint: 'low-stock/', export: 'low-stock/export/', dates: false },
  { key: 'customers', label: 'Customers', endpoint: 'customers/', export: 'customers/export/', dates: true },
  { key: 'vendor-purchases', label: 'Vendor purchases', endpoint: 'vendor-purchases/', export: 'vendor-purchases/export/', dates: true },
  { key: 'payment-verification', label: 'Payment verification', endpoint: 'payment-verification/', export: 'payment-verification/export/', dates: true },
];

const todayISO = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const defaultStart = () => {
  const date = new Date(); date.setDate(date.getDate() - 29);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const money = (value) => `₹${Number(value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const display = (value) => value === null || value === undefined || value === '' ? '—' : String(value);
const dateTime = (value) => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
async function errorMessage(error) {
  let data = error.response?.data;
  if (data instanceof Blob) {
    const text = await data.text();
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    return Object.entries(data).map(([field, messages]) => {
      const text = Array.isArray(messages) ? messages.join(' ') : String(messages);
      return field === 'detail' ? text : `${field}: ${text}`;
    }).join(' ');
  }
  return error.message || 'The report could not be loaded. Please try again.';
}

function columnsFor(key) {
  const base = {
    sales: [['date', 'Date'], ['order_count', 'Orders'], ['order_value', 'Order value'], ['cancelled_order_count', 'Cancelled'], ['cancelled_order_value', 'Cancelled value'], ['pending_payment_value', 'Pending payment'], ['verified_revenue', 'Verified revenue'], ['rejected_attempt_count', 'Rejected attempts']],
    orders: [['order_reference', 'Order reference'], ['customer_name', 'Customer'], ['created_at', 'Date'], ['item_summary', 'Items'], ['total_amount', 'Total'], ['payment_status', 'Payment'], ['fulfillment_status', 'Fulfilment']],
    inventory: [['product', 'Product'], ['category', 'Category'], ['current_stock', 'Available stock'], ['current_price', 'Price'], ['active', 'Status']],
    'low-stock': [['product', 'Product'], ['category', 'Category'], ['current_stock', 'Current stock'], ['threshold', 'Threshold'], ['reorder_recommendation', 'Recommendation'], ['active', 'Status']],
    customers: [['customer_name', 'Customer'], ['username', 'Username'], ['email', 'Email'], ['order_count', 'Orders'], ['verified_payment_total', 'Verified payments'], ['pending_order_value', 'Pending order value'], ['last_order_date', 'Last order']],
    'vendor-purchases': [['vendor', 'Vendor'], ['product', 'Product'], ['quantity', 'Quantity'], ['unit_cost', 'Unit cost'], ['purchase_value', 'Purchase value'], ['status', 'Status'], ['purchased_at', 'Purchase date']],
    'payment-verification': [['order_reference', 'Order reference'], ['customer_name', 'Customer'], ['attempt_id', 'Attempt'], ['transaction_reference', 'Transaction reference'], ['expected_amount', 'Expected amount'], ['status', 'Status'], ['submitted_at', 'Submitted'], ['reviewer', 'Reviewer'], ['reviewed_at', 'Reviewed'], ['rejection_remarks', 'Rejection remarks']],
  };
  return base[key];
}

function renderValue(value, key) {
  if (['order_value', 'cancelled_order_value', 'pending_payment_value', 'verified_revenue', 'total_amount', 'current_price', 'verified_payment_total', 'pending_order_value', 'unit_cost', 'purchase_value', 'expected_amount'].includes(key)) return money(value);
  if (key.endsWith('_at') || key.endsWith('_date')) return dateTime(value);
  if (key === 'active') return value ? 'Active' : 'Inactive';
  return display(value);
}

export default function ReportsPage({ authorization, canViewCategories, canViewVendors }) {
  const [report, setReport] = useState('sales');
  const [dateFrom, setDateFrom] = useState(defaultStart);
  const [dateTo, setDateTo] = useState(todayISO);
  const [filters, setFilters] = useState({ search: '', status: '', payment_status: '', fulfillment_status: '', active: '', category_id: '', vendor_id: '' });
  const [categories, setCategories] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [summary, setSummary] = useState(null);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const reportRequestId = useRef(0);
  const summaryRequestId = useRef(0);
  const selected = useMemo(() => REPORTS.find((item) => item.key === report), [report]);

  const loadSummary = useCallback(async () => {
    const requestId = ++summaryRequestId.current;
    try {
      const response = await api.get('admin/reports/summary/', { params: { date_from: dateFrom, date_to: dateTo } });
      if (requestId === summaryRequestId.current) setSummary(response.data);
    } catch (requestError) {
      if (requestId === summaryRequestId.current) {
        if (requestError.response?.status === 403) setError('Your staff account does not have permission to view reports.');
        else setError(await errorMessage(requestError));
      }
    }
  }, [dateFrom, dateTo]);

  const load = useCallback(async (targetPage = page) => {
    const requestId = ++reportRequestId.current;
    setLoading(true); setError('');
    const params = { page: targetPage, page_size: pageSize };
    if (selected.dates) { params.date_from = dateFrom; params.date_to = dateTo; }
    Object.entries(filters).forEach(([key, value]) => { if (value !== '') params[key] = value; });
    try {
      const response = await api.get(`admin/reports/${selected.endpoint}`, { params });
      if (requestId === reportRequestId.current) setPayload(response.data);
    } catch (requestError) {
      if (requestId === reportRequestId.current) { setPayload(null); setError(await errorMessage(requestError)); }
    } finally {
      if (requestId === reportRequestId.current) setLoading(false);
    }
  }, [dateFrom, dateTo, filters, page, pageSize, selected]);

  useEffect(() => {
    let active = true;
    const optionRequests = [];
    if (canViewCategories) optionRequests.push(['categories', api.get('categories/')]);
    if (canViewVendors) optionRequests.push(['vendors', api.get('vendors/')]);
    Promise.allSettled(optionRequests.map(([, request]) => request)).then(async (results) => {
      if (!active) return;
      for (const [index, [name]] of optionRequests.entries()) {
        const result = results[index];
        if (result.status === 'fulfilled') {
          const rows = Array.isArray(result.value.data) ? result.value.data : result.value.data.results || [];
          if (name === 'categories') setCategories(rows);
          else setVendors(rows);
        } else {
          setError(await errorMessage(result.reason));
        }
      }
    });
    return () => { active = false; };
  }, [canViewCategories, canViewVendors]);
  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { setPage(1); setPayload(null); }, [report]);
  useEffect(() => { load(page); }, [load, page]);

  const updateFilter = (key, value) => { setPage(1); setFilters((current) => ({ ...current, [key]: value })); };
  const setFilter = (key, label, options) => <label key={key}>{label}<select value={filters[key]} onChange={(event) => updateFilter(key, event.target.value)}><option value="">All</option>{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>;

  async function download(format) {
    const key = `${report}-${format}`; setExporting(key); setError('');
    const params = { format };
    if (selected.dates) { params.date_from = dateFrom; params.date_to = dateTo; }
    Object.entries(filters).forEach(([name, value]) => { if (value !== '') params[name] = value; });
    try {
      const response = await api.get(`admin/reports/${selected.export}`, { params, responseType: 'blob' });
      const disposition = response.headers['content-disposition'] || '';
      const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `${report}_report.${format}`;
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (requestError) {
      setError(await errorMessage(requestError));
    } finally { setExporting(''); }
  }

  const rows = report === 'sales' ? payload?.daily?.results || [] : payload?.results || [];
  const pagination = report === 'sales' ? payload?.daily : payload;
  const metrics = summary?.metrics || {};
  const cards = [
    ['Non-cancelled order value', money(metrics.order_value), 'Customer orders created in selected range'],
    ['Verified revenue', money(metrics.verified_revenue), 'Receipt-backed; based on verification date'],
    ['Pending payment value', money(metrics.pending_payment_value), 'Current pending orders in selected range'],
    ['Cancelled orders', `${display(metrics.cancelled_order_count)} · ${money(metrics.cancelled_order_value)}`, 'Count and value shown separately'],
    ['Paid without receipts', `${display(metrics.paid_orders_without_receipts_count)} · ${money(metrics.paid_orders_without_receipts_value)}`, 'Reconciliation exceptions'],
    ['Rejected attempts', display(metrics.rejected_payment_attempt_count), 'Review events in selected range'],
  ];

  return <main className="reports-page">
    <div className="page-heading"><div><p className="eyebrow">BUSINESS INSIGHTS</p><h1>Reports</h1><p className="muted">Explore showroom activity and download filtered reports.</p></div><button className="secondary" type="button" onClick={() => load(page)} disabled={loading}><RefreshCw size={16} /> Refresh</button></div>
    <section className="report-overview">
      <div className="report-date-filters"><label>Date from<input type="date" value={dateFrom} max={dateTo} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} /></label><label>Date to<input type="date" value={dateTo} min={dateFrom} max={todayISO()} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} /></label><span>Dates use the report’s documented date basis.</span></div>
      <div className="report-summary-grid" aria-busy={loading}>{cards.map(([label, value, note]) => <article className="report-summary-card" key={label}><span>{label}</span><strong>{loading && !summary ? '…' : value}</strong><small>{note}</small></article>)}</div>
    </section>
    <div className="report-tabs" role="tablist" aria-label="Reports">{REPORTS.filter((item) => canAccessReport(authorization, item.key)).map((item) => <button type="button" role="tab" aria-selected={report === item.key} className={report === item.key ? 'selected' : ''} key={item.key} onClick={() => { setReport(item.key); setFilters({ search: '', status: '', payment_status: '', fulfillment_status: '', active: '', category_id: '', vendor_id: '' }); }}>{item.label}</button>)}</div>
    <section className="table-panel report-table-panel">
      <div className="report-panel-title"><div><h2>{selected.label}</h2><p className="muted">{payload?.date_basis || (selected.dates ? 'Date-filtered report' : 'Current inventory snapshot')}</p></div><div className="report-download-actions"><button type="button" className="secondary" disabled={Boolean(exporting)} onClick={() => download('csv')}><Download size={15} />{exporting === `${report}-csv` ? 'Preparing CSV…' : 'CSV'}</button><button type="button" className="secondary" disabled={Boolean(exporting)} onClick={() => download('pdf')}><Download size={15} />{exporting === `${report}-pdf` ? 'Preparing PDF…' : 'PDF'}</button></div></div>
      <div className="report-filters">
        {['orders', 'customers', 'vendor-purchases', 'payment-verification', 'inventory', 'low-stock'].includes(report) && <label className="report-search"><span>Search</span><div className="search-box"><Search size={15} /><input value={filters.search} placeholder="Search this report" onChange={(event) => updateFilter('search', event.target.value)} /></div></label>}
        {report === 'orders' && setFilter('payment_status', 'Payment status', [['Pending', 'Pending'], ['Paid', 'Paid'], ['unrecorded', 'Unrecorded']])}
        {report === 'orders' && setFilter('fulfillment_status', 'Fulfilment', [['Pending', 'Pending'], ['Processing', 'Processing'], ['Shipped', 'Shipped'], ['Delivered', 'Delivered'], ['Cancelled', 'Cancelled']])}
        {['vendor-purchases', 'payment-verification'].includes(report) && setFilter('status', 'Status', report === 'vendor-purchases' ? [['Requested', 'Requested'], ['Approved', 'Approved'], ['Received', 'Received'], ['Rejected', 'Rejected']] : [['Pending', 'Pending'], ['Verified', 'Verified'], ['Rejected', 'Rejected']])}
        {report === 'payment-verification' && setFilter('review_action', 'Review action', [['Verified', 'Verified'], ['Rejected', 'Rejected'], ['unreviewed', 'Unreviewed']])}
        {['inventory', 'low-stock'].includes(report) && <label>Product status<select value={filters.active || (report === 'low-stock' ? 'true' : '')} onChange={(event) => updateFilter('active', event.target.value)}>{report === 'low-stock' ? <><option value="true">Active</option><option value="false">Inactive</option><option value="all">All statuses</option></> : <><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></>}</select></label>}
        {canViewCategories && ['inventory', 'low-stock'].includes(report) && <label>Category<select value={filters.category_id} onChange={(event) => updateFilter('category_id', event.target.value)}><option value="">All categories</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {canViewVendors && report === 'vendor-purchases' && <label>Vendor<select value={filters.vendor_id} onChange={(event) => updateFilter('vendor_id', event.target.value)}><option value="">All vendors</option>{vendors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      </div>
      {error && <div className="error report-error" role="alert">{error}<button type="button" className="text-button" onClick={() => load(page)}>Try again</button></div>}
      <div className="table-scroll report-results" aria-busy={loading}>
        {loading ? <div className="empty-state" role="status">Loading {selected.label.toLowerCase()}…</div> : error && !payload ? null : rows.length === 0 ? <div className="empty-state">No records match these filters.</div> : <table><thead><tr>{columnsFor(report).map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id || row.product_id || row.purchase_id || row.attempt_id || row.customer_id || row.date || index}>{columnsFor(report).map(([key]) => <td key={key}>{renderValue(row[key], key)}</td>)}</tr>)}</tbody></table>}
      </div>
      <div className="report-pagination"><span>{pagination ? `${pagination.count} records · Page ${pagination.page} of ${pagination.total_pages}` : ' '}</span><div><button type="button" className="secondary" disabled={loading || !pagination || page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><button type="button" className="secondary" disabled={loading || !pagination || page >= pagination.total_pages} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
    </section>
    {report === 'sales' && <p className="footnote">Order value follows order creation date. Verified revenue follows receipt verification date. These measures are intentionally distinct.</p>}
  </main>;
}
