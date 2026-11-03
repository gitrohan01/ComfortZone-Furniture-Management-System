import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../api";
import PaymentPanel from "./PaymentPanel";
import "../css/UserOrders.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value) || 0);

function OrderDetails() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.get(`orders/${id}/`).then(response => { if (active) setOrder(response.data); })
      .catch(() => { if (active) setError("This order could not be found or is not available to this account."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  if (loading) return <main className="customer-order-details-page"><p role="status">Loading order…</p></main>;
  if (error || !order) return <main className="customer-order-details-page"><p role="alert">{error}</p><Link to="/account/orders">Back to My Orders</Link></main>;

  return <main className="customer-order-details-page"><Link to="/account/orders">← My Orders</Link>
    <article className="customer-order-card"><p className="customer-order-eyebrow">SHOWROOM ORDER</p><h1>{order.order_reference || `Order #${order.id}`}</h1><p>Placed {new Date(order.created_at).toLocaleString("en-IN")}</p>
      <p>Fulfilment status: <strong>{order.status}</strong></p><p>Payment status: <strong>{order.payment_status || "Not recorded for this earlier order"}</strong></p>
      <h2>Delivery details</h2><p>{order.customer_name}</p><p>{order.customer_email}</p><p>{order.shipping_address}</p>
      <h2>Items</h2>{(order.items || []).map(item => <div className="customer-order-item" key={item.id}><span>{item.product_name} × {item.quantity} @ {money(item.unit_price)}</span><strong>{money(item.line_subtotal)}</strong></div>)}
      <div className="customer-order-total"><span>Total</span><strong>{money(order.total_amount)}</strong></div>
      <PaymentPanel order={order} onOrderUpdate={setOrder} />
    </article>
  </main>;
}

export default OrderDetails;
