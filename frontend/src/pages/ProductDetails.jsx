import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../api";
import "../css/ProductDetails.css";

function ProductDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [product, setProduct] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [cartMessage, setCartMessage] = useState("");

  useEffect(() => {
    let active = true;
    api.get(`products/${id}/`).then(({ data }) => {
      if (active) setProduct(data);
    }).catch(() => {
      if (active) setMessage("This product could not be loaded. Please check the backend.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  const addToCart = (buyNow = false) => {
    if (!product) return;
    const item = { ...product, quantity };
    let cart = [];
    try { cart = JSON.parse(localStorage.getItem("cart") || "[]"); } catch { cart = []; }
    if (!Array.isArray(cart)) cart = [];
    const existing = cart.find(row => String(row.id) === String(product.id));
    if (existing && Number(existing.quantity || 1) + quantity > Number(product.stock || 0)) {
      setCartMessage(`Only ${product.stock} of ${product.name} are available in total.`);
      return;
    }
    if (existing) existing.quantity = Number(existing.quantity || 1) + quantity;
    else cart.push(item);
    localStorage.setItem("cart", JSON.stringify(cart));
    window.dispatchEvent(new Event("cart:updated"));
    navigate(buyNow ? "/checkout" : "/cart");
  };

  if (loading) return <p className="cz-detail-status">Loading product…</p>;
  if (!product) return <div className="cz-detail-status" role="alert">{message || "Product not found."}<p><Link to="/">Back to home</Link></p></div>;

  const stock = Number(product.stock ?? product.quantity ?? 0);
  return <main className="cz-product-detail-page">
    <p className="cz-detail-breadcrumb"><Link to="/">Home</Link> / <Link to="/#products">Products</Link> / {product.name}</p>
    <section className="cz-product-detail">
      <div className="cz-detail-image"><img src={product.image || product.image_url || "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=1000&q=80"} alt={product.name} /></div>
      <div className="cz-detail-copy">
        <p className="cz-detail-category">{product.category_name || "COMFORT ZONE COLLECTION"}</p>
        <h1>{product.name}</h1>
        <p className="cz-detail-description">{product.description || "Thoughtfully selected furniture to bring comfort and style into your home."}</p>
        <h2>₹{Number(product.price || 0).toLocaleString("en-IN")}</h2>
        <p className={stock > 0 ? "cz-detail-stock" : "cz-detail-stock unavailable"}>{stock > 0 ? `${stock} available in stock` : "Currently out of stock"}</p>
        {stock > 0 && <>
          <label className="cz-detail-quantity">Quantity <input type="number" min="1" max={stock} value={quantity} onChange={e => setQuantity(Math.max(1, Math.min(stock, Number(e.target.value) || 1)))} /></label>
          <div className="cz-detail-actions"><button onClick={() => addToCart(false)} className="cz-detail-add">Add to Cart</button><button onClick={() => addToCart(true)} className="cz-detail-buy">Buy Now →</button></div>
        </>}
        {message && <p role="alert" className="cz-detail-message">{message}</p>}
        {cartMessage && <p role="status" className="cz-detail-message">{cartMessage}</p>}
        <div className="cz-detail-note">✓ Quality furniture &nbsp; · &nbsp; ✓ Customer support</div>
      </div>
    </section>
  </main>;
}
export default ProductDetails;
