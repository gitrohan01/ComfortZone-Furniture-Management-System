import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../css/Cart.css";

function readCart() {
  try {
    const saved = JSON.parse(localStorage.getItem("cart") || "[]");
    return Array.isArray(saved) ? saved.filter(item => item && item.id) : [];
  } catch { return []; }
}

function Cart() {
  const navigate = useNavigate();
  const [items, setItems] = useState(readCart);

  const save = (next) => {
    setItems(next);
    localStorage.setItem("cart", JSON.stringify(next));
    window.dispatchEvent(new Event("cart:updated"));
  };
  const changeQuantity = (id, quantity) => save(items.map(item => String(item.id) === String(id)
    ? { ...item, quantity: Math.max(1, Math.min(Number(item.stock || quantity), quantity)) }
    : item));
  const remove = id => save(items.filter(item => String(item.id) !== String(id)));
  const total = items.reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 1), 0);
  const checkout = () => {
    if (!items.length) return;
    if (!localStorage.getItem("access")) {
      navigate("/login", { state: { from: "/checkout", message: "Sign in or create an account to complete your purchase." } });
      return;
    }
    navigate("/checkout");
  };

  return <section className="cz-cart-page">
    <div className="cz-cart-heading"><div><p className="cz-cart-kicker">YOUR SELECTION</p><h1>Shopping Cart</h1><p>Review your furniture before checkout.</p></div><Link to="/" className="cz-cart-continue">← Continue shopping</Link></div>
    {items.length === 0 ? <div className="cz-cart-empty"><div className="cz-cart-icon">🛍️</div><h2>Your cart is waiting</h2><p>You have not added any furniture yet.</p><Link className="cz-cart-primary" to="/">Explore products</Link></div> :
      <div className="cz-cart-layout"><div className="cz-cart-items">{items.map(item => {
        const stock = Math.max(0, Number(item.stock || 0));
        return <article className="cz-cart-item" key={item.id}>
          <img src={item.image || item.image_url || "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=300&q=80"} alt={item.name} />
          <div className="cz-cart-item-info"><Link to={`/product/${item.id}`} className="cz-cart-item-name">{item.name}</Link><p>{item.category_name || "Furniture"}</p><strong>₹{Number(item.price || 0).toLocaleString("en-IN")}</strong>
            <div className="cz-quantity"><button type="button" onClick={() => changeQuantity(item.id, Number(item.quantity || 1) - 1)} aria-label={`Decrease ${item.name} quantity`}>−</button><span>{item.quantity || 1}</span><button type="button" onClick={() => changeQuantity(item.id, Number(item.quantity || 1) + 1)} aria-label={`Increase ${item.name} quantity`} disabled={Number(item.quantity || 1) >= stock}>+</button></div>
            {Number(item.quantity || 1) > stock && <small className="cz-cart-stock-warning">Only {stock} currently available. Checkout will recheck stock.</small>}
          </div><div className="cz-cart-item-end"><strong>₹{(Number(item.price || 0) * Number(item.quantity || 1)).toLocaleString("en-IN")}</strong><button type="button" className="cz-remove-item" onClick={() => remove(item.id)}>Remove</button></div>
        </article>;
      })}</div>
      <aside className="cz-order-summary"><h2>Order Summary</h2><div><span>Subtotal estimate</span><strong>₹{total.toLocaleString("en-IN")}</strong></div><div><span>Delivery</span><strong className="cz-free">Free</strong></div><div className="cz-summary-total"><span>Estimated total</span><strong>₹{total.toLocaleString("en-IN")}</strong></div><button type="button" className="cz-cart-primary cz-checkout" onClick={checkout}>Proceed to Checkout →</button><p>Final prices and availability are confirmed by the showroom at checkout.</p><button type="button" className="cz-remove-item" onClick={() => save([])}>Clear cart</button></aside></div>}
  </section>;
}

export default Cart;
