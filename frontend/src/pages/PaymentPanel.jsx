import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Upload } from 'lucide-react';
import api from '../api';

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value) || 0);
const date = (value) => value ? new Date(value).toLocaleString('en-IN') : '—';

export default function PaymentPanel({ order, onOrderUpdate }) {
  const [instructions, setInstructions] = useState(null);
  const [qrUrl, setQrUrl] = useState('');
  const [attempts, setAttempts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [reference, setReference] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(false);
  const [receiptBusy, setReceiptBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const orderResponse = await api.get(`orders/${order.id}/`);
      onOrderUpdate?.(orderResponse.data);
      const history = await api.get(`orders/${order.id}/payment-attempts/`);
      setAttempts(Array.isArray(history.data) ? history.data : []);
      if (orderResponse.data.payment_status !== 'Paid' && orderResponse.data.status !== 'Cancelled') {
        try {
          const response = await api.post(`orders/${order.id}/payment-instructions/`);
          setInstructions(response.data);
        } catch (requestError) {
          setInstructions(null);
          setError(requestError.response?.data?.detail?.join?.(' ') || requestError.response?.data?.detail || 'Payment instructions are not available right now.');
        }
      }
    } catch (requestError) {
      setError(requestError.response?.status === 403 ? 'You do not have access to this order.' : requestError.response?.data?.detail || 'Unable to load payment history.');
    } finally { setLoading(false); }
  }, [order.id, order.payment_status, order.status]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    let active = true; let objectUrl;
    if (instructions?.qr_url) api.get(instructions.qr_url.replace(/^\/api\//, ''), { responseType: 'blob' })
      .then((response) => { if (active) { objectUrl = URL.createObjectURL(response.data); setQrUrl(objectUrl); } })
      .catch(() => { if (active) setError('The protected payment QR could not be loaded.'); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [instructions?.qr_url]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function chooseFile(event) {
    const selected = event.target.files?.[0];
    setError(''); setMessage('');
    if (preview) URL.revokeObjectURL(preview);
    setPreview(''); setFile(null);
    if (!selected) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) {
      setError('Choose a JPEG, PNG, or WebP image.'); event.target.value = ''; return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      setError('The image must be 5 MB or smaller.'); event.target.value = ''; return;
    }
    setFile(selected); setPreview(URL.createObjectURL(selected));
  }

  async function submit(event) {
    event.preventDefault();
    if (busy || !instructions || !file) return;
    setBusy(true); setError(''); setMessage(''); setProgress(0);
    const body = new FormData();
    body.append('transaction_reference', reference.trim());
    body.append('proof_image', file);
    try {
      await api.post(`orders/${order.id}/payment-attempts/`, body, {
        onUploadProgress: (event) => setProgress(event.total ? Math.round(event.loaded * 100 / event.total) : 0),
      });
      setMessage('Your payment details were submitted for staff review. Uploading proof does not verify payment.');
      setReference(''); setFile(null); setPreview('');
      await load();
    } catch (requestError) {
      const data = requestError.response?.data;
      setError(data?.detail || data?.transaction_reference?.join?.(' ') || data?.proof_image?.join?.(' ') || 'Submission failed. Please check the details and try again.');
    } finally { setBusy(false); setProgress(0); }
  }

  async function copyUpi() {
    try { await navigator.clipboard.writeText(instructions.upi_id); setCopied(true); setTimeout(() => setCopied(false), 1800); }
    catch { setError('Could not copy the UPI ID. Select and copy it manually.'); }
  }

  async function downloadReceipt() {
    if (receiptBusy || order.payment_status !== 'Paid') return;
    setReceiptBusy(true); setError('');
    try {
      const response = await api.get(`orders/${order.id}/receipt/`, { responseType: 'blob' });
      if (response.data.type !== 'application/pdf') throw new Error('The receipt response was not a PDF.');
      const objectUrl = URL.createObjectURL(response.data);
      const safeReference = String(order.order_reference || order.id).replace(/[^A-Za-z0-9-]/g, '');
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `ComfortZone-Payment-Receipt-${safeReference}.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setMessage('Your verified payment receipt has been downloaded.');
    } catch (requestError) {
      if (requestError.response?.status === 401) setError('Your session has expired. Please sign in again.');
      else if (requestError.response?.status === 403) setError('You do not have permission to download this receipt.');
      else if (requestError.response?.status === 404) setError('The verified receipt is not available for this order yet.');
      else setError(requestError.message || 'The receipt could not be downloaded. Please try again.');
    } finally { setReceiptBusy(false); }
  }

  const pending = attempts.some((attempt) => attempt.status === 'Pending');
  const canSubmit = order.payment_status !== 'Paid' && order.status !== 'Cancelled' && !pending && Boolean(instructions);

  return <section className="payment-panel" aria-labelledby="payment-title">
    <div className="payment-panel-heading"><div><p className="customer-order-eyebrow">UPI PAYMENT</p><h2 id="payment-title">Payment and verification</h2></div><button className="payment-refresh" type="button" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button></div>
    {loading && <p role="status">Loading payment details…</p>}
    {error && <p className="payment-alert error" role="alert">{error}</p>}
    {message && <p className="payment-alert success" role="status">{message}</p>}
    {order.payment_status === 'Paid' ? <div className="payment-paid"><Check aria-hidden="true"/><div><strong>Payment verified</strong><p>Staff confirmed this payment against the actual UPI/bank records.</p></div></div>
      : order.status === 'Cancelled' ? <p className="payment-alert">Payment cannot be submitted for a cancelled order.</p>
        : instructions && <>
          <div className="payment-instructions"><div><p><span>Order reference</span><strong>{instructions.order_reference}</strong></p><p><span>Exact amount</span><strong>{money(instructions.amount)}</strong></p><p><span>Showroom</span><strong>{instructions.showroom_name}</strong></p><p><span>UPI ID</span><strong className="upi-copy-row">{instructions.upi_id}<button type="button" onClick={copyUpi} aria-label="Copy UPI ID"><Copy size={15}/>{copied ? 'Copied' : 'Copy'}</button></strong></p></div>
            {qrUrl && <img className="payment-qr" src={qrUrl} alt={`Protected UPI QR code for ${instructions.showroom_name}`} />}
          </div>
          <p className="payment-guidance">Pay this exact amount using your external UPI application. After payment, enter the transaction reference and upload a screenshot. Staff will check the transaction separately.</p>
          {pending ? <p className="payment-pending-note">A submission is awaiting review. You can submit again if staff reject it.</p>
            : canSubmit && <form className="payment-submit-form" onSubmit={submit}>
              <label>Transaction reference<input value={reference} onChange={(event) => setReference(event.target.value)} maxLength={128} required autoComplete="off" /></label>
              <label>Payment screenshot<input type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseFile} required aria-describedby="payment-file-help" /></label>
              <small id="payment-file-help">JPEG, PNG, or WebP; maximum 5 MB.</small>
              {preview && <img className="payment-proof-preview" src={preview} alt="Selected payment screenshot preview" />}
              {busy && <div className="payment-progress" role="status"><span style={{ width: `${progress}%` }} />Uploading proof… {progress}%</div>}
              <button className="customer-orders-refresh" type="submit" disabled={busy || !file || !reference.trim()}><Upload size={16}/>{busy ? 'Submitting…' : 'Submit for review'}</button>
            </form>}
        </>}
    <div className="payment-history"><h3>Payment attempt history</h3>{!loading && !attempts.length ? <p>No payment submissions yet.</p> : <ol>{attempts.map((attempt, index) => <li key={attempt.id}>
      <div className="payment-history-head"><strong>Attempt {index + 1}</strong><span className={`payment-badge ${attempt.status.toLowerCase()}`}>{attempt.status}</span></div>
      <p>Transaction reference: <strong>{attempt.transaction_reference}</strong></p><p>Expected amount: <strong>{money(attempt.expected_amount)}</strong></p><p>Submitted: {date(attempt.submitted_at)}</p>
      {attempt.reviewed_at && <p>Reviewed: {date(attempt.reviewed_at)}</p>}{attempt.review_remarks && <p className="payment-rejection">Review remarks: {attempt.review_remarks}</p>}
    </li>)}</ol>}</div>
    {order.payment_status === 'Paid' && <button type="button" className="customer-invoice-button payment-receipt-download" onClick={downloadReceipt} disabled={receiptBusy}>
      {receiptBusy ? 'Preparing receipt…' : 'Download verified payment receipt'}
    </button>}
  </section>;
}
