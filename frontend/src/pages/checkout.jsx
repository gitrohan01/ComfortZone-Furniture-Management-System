import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import "../css/Checkout.css";

function getUser() {
  try { return JSON.parse(localStorage.getItem("user") || "{}"); }
  catch { return {}; }
}

function Checkout() {
  const navigate = useNavigate();
  const user = getUser();
  const [cart] = useState(() => {
    try { const saved = JSON.parse(localStorage.getItem("cart") || "[]"); return Array.isArray(saved) ? saved : []; }
    catch { return []; }
  });
  const [form, setForm] = useState({ customer_name: user.username || "", customer_email: user.email || "", shipping_address: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const total = useMemo(() => cart.reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 1), 0), [cart]);

  const submit = async (event) => {
    event.preventDefault();
    if (!localStorage.getItem("access")) {
      navigate("/login", { state: { from: "/checkout", message: "Sign in to complete your order." } });
      return;
    }
    if (!cart.length) {
      setError("Your cart is empty. Add a product before checkout.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await api.post("orders/", {
        ...form,
        items: cart.map(item => ({ product_id: Number(item.id), quantity: Number(item.quantity || 1) })),
      });
      localStorage.setItem("cart", "[]");
      window.dispatchEvent(new Event("cart:updated"));
      navigate(`/account/orders/${response.data.id}`, { replace: true });
    } catch (requestError) {
      const data = requestError.response?.data;
      if (data?.items) setError(Array.isArray(data.items) ? data.items.join(" ") : String(data.items));
      else if (data && typeof data === "object") setError(Object.entries(data).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(" ") : value}`).join(" "));
      else setError(requestError.message || "Your order could not be placed. Please try again.");
    } finally { setSubmitting(false); }
  };

  return <main className="cz-checkout-page"><div className="cz-checkout-header"><p className="cz-cart-kicker">SECURE CHECKOUT</p><h1>Delivery details</h1><p>We’ll confirm product availability and calculate your total when your order is submitted.</p></div>
    {!localStorage.getItem("access") ? <section className="cz-checkout-empty"><div><h2>Sign in to continue</h2><p>Your cart will stay saved while you sign in.</p></div><div><Link to="/login" state={{ from: "/checkout" }}>Login</Link><Link to="/register" state={{ from: "/checkout" }}>Create account</Link></div></section> : !cart.length ? <section className="cz-checkout-empty"><h2>Your cart is empty</h2><Link to="/">Browse the collection</Link></section> :
      <div className="cz-checkout-layout"><form className="cz-checkout-form" onSubmit={submit}>
        {error && <p className="cz-checkout-error" role="alert">{error}</p>}
        <label>Full name<input required maxLength="120" value={form.customer_name} onChange={event => setForm({ ...form, customer_name: event.target.value })} /></label>
        <label>Email<input type="email" value={form.customer_email} onChange={event => setForm({ ...form, customer_email: event.target.value })} /></label>
        <label>Delivery address<textarea required rows="4" value={form.shipping_address} onChange={event => setForm({ ...form, shipping_address: event.target.value })} /></label>
        <button className="cz-cart-primary" type="submit" disabled={submitting}>{submitting ? "Submitting order…" : "Place order"}</button>
        <Link to="/cart" className="cz-checkout-back">Return to cart</Link>
      </form><aside className="cz-checkout-summary"><h2>Your items</h2>{cart.map(item => <div className="cz-checkout-line" key={item.id}><span>{item.name} × {item.quantity || 1}</span><strong>₹{(Number(item.price || 0) * Number(item.quantity || 1)).toLocaleString("en-IN")}</strong></div>)}<div className="cz-checkout-total"><span>Current estimate</span><strong>₹{total.toLocaleString("en-IN")}</strong></div><p>The server rechecks stock and calculates the final order total. Payment status starts as Pending; no payment is collected in this step.</p></aside></div>}
  </main>;
}

export default Checkout;
