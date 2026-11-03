import { useCallback, useEffect, useState } from 'react';
import { Search, RefreshCw, Check, X, ExternalLink } from 'lucide-react';
import api from '../api';
import { useAuthorization } from '../auth/AuthorizationContext';
import { hasPermission } from '../auth/authorization';

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value) || 0);
const date = (value) => value ? new Date(value).toLocaleString('en-IN') : '—';

function assetPath(path) { return String(path || '').replace(/^\/api\//, ''); }

export default function PaymentReview() {
  const { authorization } = useAuthorization();
  const canReview = hasPermission(authorization, 'store.verify_payment');
  const [rows, setRows] = useState([]); const [selected, setSelected] = useState(null); const [order, setOrder] = useState(null);
  const [evidence, setEvidence] = useState(''); const [filter, setFilter] = useState({ status: 'Pending', date_from: '', date_to: '', order_reference: '' });
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [dialog, setDialog] = useState(''); const [bankChecked, setBankChecked] = useState(false); const [remarks, setRemarks] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = Object.fromEntries(Object.entries(filter).filter(([, value]) => value));
      const response = await api.get('admin/payment-attempts/', { params });
      setRows(Array.isArray(response.data) ? response.data : []);
      if (selected) {
        const current = await api.get(`admin/payment-attempts/${selected.id}/`);
        setSelected(current.data);
        setOrder(current.data.order);
      }
    } catch (requestError) {
      setError(requestError.response?.status === 403 ? 'Your account does not have payment review permission.' : requestError.response?.data?.detail || 'Unable to load payment attempts.');
      if (requestError.response?.status === 403) setRows([]);
    } finally { setLoading(false); }
  }, [filter, selected?.id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    let objectUrl;
    if (selected?.proof_url) api.get(assetPath(selected.proof_url), { responseType: 'blob' })
      .then((response) => { objectUrl = URL.createObjectURL(response.data); setEvidence(objectUrl); })
      .catch(() => { setEvidence(''); setError('Evidence is unavailable or your review access has expired.'); });
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); setEvidence(''); };
  }, [selected?.proof_url, selected?.id]);

  async function selectAttempt(row) {
    setError(''); setMessage(''); setEvidence(''); setOrder(null);
    try {
      const detail = await api.get(`admin/payment-attempts/${row.id}/`);
      setSelected(detail.data);
      setOrder(detail.data.order);
    } catch (requestError) { setError(requestError.response?.status === 403 ? 'Review permission is required to see this payment.' : 'Unable to load the payment detail and order.'); }
  }

  async function decide() {
    if (saving || !selected || !canReview) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const payload = dialog === 'approve' ? { bank_checked: true } : { remarks: remarks.trim() };
      await api.post(`admin/payment-attempts/${selected.id}/${dialog}/`, payload);
      setMessage(`Payment ${dialog === 'approve' ? 'approved' : 'rejected'} successfully.`); setDialog(''); setBankChecked(false); setRemarks('');
      await load();
      const detail = await api.get(`admin/payment-attempts/${selected.id}/`);
      setSelected(detail.data);
      setOrder(detail.data.order);
    } catch (requestError) {
      setError(requestError.response?.status === 409 ? 'This payment changed while you were reviewing it. Refresh the queue and inspect the latest status.' : requestError.response?.status === 403 ? 'Your review permission is required for this action.' : requestError.response?.data?.detail || 'The review could not be submitted.');
      setDialog('');
    } finally { setSaving(false); }
  }

  return <div className="payment-admin-page">
    <div className="page-heading"><div><p className="eyebrow">PAYMENT OPERATIONS</p><h1>Payment review</h1><p className="muted">Compare uploaded evidence with the actual UPI or bank records.</p></div><button className="secondary" type="button" onClick={load} disabled={loading}><RefreshCw size={16}/>{loading ? 'Refreshing…' : 'Refresh queue'}</button></div>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="payment-admin-success" role="status">{message}</p>}
    <section className="payment-filter-panel" aria-label="Payment attempt filters">
      <label>Status<select value={filter.status} onChange={(event) => setFilter({ ...filter, status: event.target.value })}><option value="">All statuses</option><option>Pending</option><option>Verified</option><option>Rejected</option></select></label>
      <label>From<input type="date" value={filter.date_from} onChange={(event) => setFilter({ ...filter, date_from: event.target.value })}/></label>
      <label>To<input type="date" value={filter.date_to} onChange={(event) => setFilter({ ...filter, date_to: event.target.value })}/></label>
      <label className="payment-ref-filter"><Search size={16}/><span>Order reference</span><input value={filter.order_reference} onChange={(event) => setFilter({ ...filter, order_reference: event.target.value })} placeholder="Search reference"/></label>
    </section>
    <div className="payment-review-layout">
      <section className="payment-queue table-panel"><div className="table-toolbar"><div><h2>Attempts</h2><p className="muted">{rows.length} result{rows.length === 1 ? '' : 's'}</p></div></div>
        {loading ? <div className="empty-state" role="status">Loading payment attempts…</div> : !rows.length ? <div className="empty-state">No payment attempts match these filters.</div> : <div className="payment-queue-list">{rows.map((row) => <button type="button" key={row.id} className={`payment-queue-item ${selected?.id === row.id ? 'active' : ''}`} onClick={() => selectAttempt(row)}>
          <span className={`payment-badge ${row.status.toLowerCase()}`}>{row.status}</span><strong>{row.order.reference || `Order #${row.order.id}`}</strong><small>{row.customer.name} · {date(row.submitted_at)}</small><b>{money(row.expected_amount)}</b>
        </button>)}</div>}
      </section>
      <section className="payment-detail-panel table-panel" aria-live="polite">
        {!selected ? <div className="empty-state">Choose an attempt to inspect its details.</div> : <>
          <header className="payment-detail-heading"><div><p className="eyebrow">ATTEMPT #{selected.id}</p><h2>{selected.order.reference || `Order #${selected.order.id}`}</h2></div><span className={`payment-badge ${selected.status.toLowerCase()}`}>{selected.status}</span></header>
          <div className="payment-detail-grid"><div><h3>Customer</h3><p>{selected.customer.name}</p><p>{selected.customer.email || 'No email recorded'}</p></div><div><h3>Order</h3><p>Reference: {selected.order.reference || '—'}</p><p>Payment: {selected.order.payment_status}</p><p>Fulfilment: {selected.order.fulfillment_status}</p></div></div>
          <div className="payment-order-items"><h3>Order items</h3>{order?.items?.length ? order.items.map((item) => <p key={item.id}><span>{item.product_name} × {item.quantity}</span><strong>{money(item.line_subtotal)}</strong></p>) : <p>{order ? 'No line items recorded.' : 'Loading order items…'}</p>}<p className="payment-admin-total"><span>Expected payment</span><strong>{money(selected.expected_amount)}</strong></p></div>
          {selected.receipt && <div className="payment-review-history"><h3>Immutable receipt history</h3><p>Receipt {selected.receipt.receipt_number}</p><p>{money(selected.receipt.amount)} · {selected.receipt.transaction_reference}</p><p>{selected.receipt.showroom_name} · {selected.receipt.upi_id}</p><small>Verified {date(selected.receipt.verified_at)} by {selected.receipt.reviewer_name}</small></div>}
          <div className="payment-transaction"><h3>Transaction reference</h3><code>{selected.transaction_reference}</code><p>Submitted {date(selected.submitted_at)}</p></div>
          <div className="payment-evidence"><h3>Private payment evidence</h3>{evidence ? <a href={evidence} target="_blank" rel="noreferrer"><img src={evidence} alt={`Payment proof for attempt ${selected.id}`}/><span><ExternalLink size={15}/> Open evidence</span></a> : <p role="status">Loading protected evidence…</p>}</div>
          <div className="payment-review-history"><h3>Review history</h3>{selected.review_history?.length ? selected.review_history.map((event, index) => <article key={`${event.reviewed_at}-${index}`}><strong>{event.action} by {event.reviewer}</strong><p>{event.remarks || 'No remarks'}</p><small>{date(event.reviewed_at)}</small></article>) : <p>No review has been recorded.</p>}</div>
          {canReview && selected.status === 'Pending' && <div className="payment-decision-actions"><button type="button" className="primary" onClick={() => { setBankChecked(false); setDialog('approve'); }}><Check size={16}/> Approve payment</button><button type="button" className="payment-reject-button" onClick={() => { setRemarks(''); setDialog('reject'); }}><X size={16}/> Reject</button></div>}
        </>}
      </section>
    </div>
    {dialog && <div className="payment-dialog-backdrop"><section className="payment-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="payment-confirm-title">
      <h2 id="payment-confirm-title">{dialog === 'approve' ? 'Confirm payment approval' : 'Confirm payment rejection'}</h2>
      {dialog === 'approve' ? <><p>Approve attempt #{selected?.id} for {money(selected?.expected_amount)}?</p><label className="payment-bank-confirm"><input type="checkbox" checked={bankChecked} onChange={(event) => setBankChecked(event.target.checked)}/>I independently checked the actual UPI/bank transaction records.</label></>
        : <><p>Reject attempt #{selected?.id}? The uploaded proof will remain in its history.</p><label>Rejection remarks<textarea value={remarks} onChange={(event) => setRemarks(event.target.value)} required rows={4} placeholder="Explain what needs correction"/></label></>}
      <div className="form-actions"><button type="button" className="secondary" onClick={() => setDialog('')} disabled={saving}>Cancel</button><button type="button" className={dialog === 'approve' ? 'primary' : 'payment-reject-button'} onClick={decide} disabled={saving || (dialog === 'approve' ? !bankChecked : !remarks.trim())}>{saving ? 'Submitting…' : `Confirm ${dialog}`}</button></div>
    </section></div>}
  </div>;
}
