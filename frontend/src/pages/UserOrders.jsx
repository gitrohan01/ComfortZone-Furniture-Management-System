import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import "../css/Dashboard.css";
import "../css/UserOrders.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value) || 0);

function UserOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get("orders/");
      setOrders(Array.isArray(response.data) ? response.data : response.data.results || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to load your orders. Please try again.");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const logout = () => {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    localStorage.removeItem("user");
    navigate("/", { replace: true });
  };

  return <main className="customer-orders-page">
    <header className="customer-orders-top"><Link to="/" className="cz-home-brand">Comfort<span>Zone</span></Link><nav><Link to="/">Continue shopping</Link><button type="button" onClick={logout}>Log out</button></nav></header>
    <section className="dashboard-container customer-orders-content"><header className="dashboard-header customer-orders-header"><div><p className="welcome-small">ORDER HISTORY</p><h1>My Orders</h1></div><button type="button" className="customer-orders-refresh" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh orders"}</button></header>
      {loading && <p className="customer-orders-state" role="status">Loading your orders…</p>}
      {error && <section className="customer-orders-state customer-orders-error" role="alert"><p>{error}</p><button type="button" onClick={load}>Try again</button></section>}
      {!loading && !error && !orders.length && <section className="customer-orders-state customer-orders-empty"><h2>No orders yet</h2><p>Your confirmed orders will appear here.</p><Link to="/">Browse furniture</Link></section>}
      {!error && orders.length > 0 && <div className="customer-order-list">{orders.map(order => <article className="customer-order-card" key={order.id}>
        <div className="customer-order-heading"><div><p className="customer-order-eyebrow">SHOWROOM ORDER</p><h2>{order.order_reference || `Order #${order.id}`}</h2><small>{new Date(order.created_at).toLocaleDateString("en-IN")}</small></div><span className={`customer-order-status ${(order.status || "Pending").toLowerCase()}`}>{order.status || "Pending"}</span></div>
        <div className="customer-order-items"><h3>Items</h3>{(order.items || []).map(item => <div className="customer-order-item" key={item.id}><span>{item.product_name} × {item.quantity}</span><span>{money(item.line_subtotal)}</span></div>)}</div>
        <div className="customer-order-total"><span>Order total</span><strong>{money(order.total_amount)}</strong></div>
        <p className="customer-payment-status">Payment status: <strong>{order.payment_status || "Not recorded for this earlier order"}</strong></p>
        <Link className="customer-order-details-link" to={`/account/orders/${order.id}`}>View order details</Link>
      </article>)}</div>}
    </section>
  </main>;
}

export default UserOrders;
