import { useCallback, useEffect, useState } from 'react';
import { Check, Plus, RefreshCw } from 'lucide-react';
import api from '../api';
import { useAuthorization } from '../auth/AuthorizationContext';
import { hasPermission } from '../auth/authorization';

export default function PaymentConfiguration() {
  const { authorization } = useAuthorization();
  const canManage = hasPermission(authorization, 'store.manage_payment_configuration');
  const [rows, setRows] = useState([]); const [formOpen, setFormOpen] = useState(false);
  const [displayName, setDisplayName] = useState(''); const [upiId, setUpiId] = useState(''); const [qrImage, setQrImage] = useState(null);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const response = await api.get('admin/payment-configurations/'); setRows(Array.isArray(response.data) ? response.data : []); }
    catch (requestError) { setError(requestError.response?.status === 403 ? 'Your account does not have payment configuration permission.' : requestError.response?.data?.detail || 'Unable to load configurations.'); setRows([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(event) {
    event.preventDefault(); if (saving || !canManage || !qrImage) return;
    setSaving(true); setError(''); setMessage('');
    const body = new FormData(); body.append('display_name', displayName.trim()); body.append('upi_id', upiId.trim()); body.append('qr_image', qrImage);
    try {
      await api.post('admin/payment-configurations/', body);
      setDisplayName(''); setUpiId(''); setQrImage(null); setFormOpen(false); setMessage('New configuration version created. Activate it when ready.'); await load();
    } catch (requestError) { setError(requestError.response?.data?.detail || requestError.response?.data?.qr_image?.join?.(' ') || 'Configuration version could not be created.'); }
    finally { setSaving(false); }
  }

  async function changeActive(row, action) {
    if (saving || !canManage) return;
    setSaving(true); setError(''); setMessage('');
    try { await api.post(`admin/payment-configurations/${row.id}/${action}/`); setMessage(`Configuration ${action === 'activate' ? 'activated' : 'deactivated'}.`); await load(); }
    catch (requestError) { setError(requestError.response?.status === 403 ? 'Configuration permission is required.' : requestError.response?.data?.detail || 'Unable to update configuration status.'); }
    finally { setSaving(false); }
  }

  return <div className="payment-config-page">
    <div className="page-heading"><div><p className="eyebrow">PAYMENT OPERATIONS</p><h1>UPI configuration</h1><p className="muted">Each version is retained. Create a new version to change the payment details or QR.</p></div><button className="secondary" type="button" onClick={load} disabled={loading}><RefreshCw size={16}/>{loading ? 'Refreshing…' : 'Refresh'}</button></div>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="payment-admin-success" role="status">{message}</p>}
    <section className="table-panel"><div className="table-toolbar"><div><h2>Configuration versions</h2><p className="muted">{rows.length} saved version{rows.length === 1 ? '' : 's'}</p></div>{canManage && <button className="primary" type="button" onClick={() => setFormOpen((value) => !value)}><Plus size={16}/>{formOpen ? 'Close form' : 'Create new version'}</button>}</div>
      {formOpen && <form className="payment-config-form" onSubmit={create}>
        <p className="payment-config-note">Existing versions cannot be edited. A new QR image is required for every version.</p>
        <label>Showroom display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={160} required/></label>
        <label>UPI ID<input value={upiId} onChange={(event) => setUpiId(event.target.value)} placeholder="showroom@bank" maxLength={255} required/></label>
        <label>QR image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setQrImage(event.target.files?.[0] || null)} required/><small>JPEG, PNG, or WebP; maximum 5 MB.</small></label>
        <div className="form-actions"><button className="primary" type="submit" disabled={saving || !qrImage}>{saving ? 'Saving…' : 'Create version'}</button></div>
      </form>}
      {loading ? <div className="empty-state" role="status">Loading configurations…</div> : rows.length === 0 ? <div className="empty-state">No UPI configurations have been created.</div> : <div className="payment-config-list">{rows.map((row) => <article className="payment-config-card" key={row.id}>
        <div className="payment-config-status">{row.is_active ? <span className="payment-badge verified"><Check size={13}/>Active configuration</span> : <span className="payment-badge">Inactive version</span>}<small>Created {new Date(row.created_at).toLocaleString('en-IN')}</small></div>
        <h3>{row.display_name}</h3><p><strong>UPI ID:</strong> {row.upi_id}</p><p className="payment-version">Version {row.version}</p>
        <div className="payment-config-actions">{row.qr_url && <a href={row.qr_url} onClick={async (event) => {
          event.preventDefault(); try { const response = await api.get(row.qr_url.replace(/^\/api\//, ''), { responseType: 'blob' }); const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = 'showroom-payment-qr.png'; link.click(); URL.revokeObjectURL(url); }
          catch (requestError) { setError(requestError.response?.status === 403 ? 'Configuration permission is required to access this QR.' : 'QR image is unavailable.'); }
        }}>Download protected QR</a>}
          {canManage && <button type="button" className={row.is_active ? 'payment-reject-button' : 'primary'} disabled={saving} onClick={() => changeActive(row, row.is_active ? 'deactivate' : 'activate')}>{row.is_active ? 'Deactivate' : 'Activate version'}</button>}</div>
      </article>)}</div>}
    </section>
  </div>;
}
