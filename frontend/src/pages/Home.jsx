import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api";
import { useAuthorization } from "../auth/AuthorizationContext";
import { firstAccessiblePath } from "../auth/authorization";
import "../css/Home.css";

function Home() {
  const { authorization } = useAuthorization();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState(["All Products"]);
  const [selectedCategory, setSelectedCategory] = useState("All Products");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cartMessage, setCartMessage] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    Promise.all([api.get("products/"), api.get("categories/")]).then(([productResponse, categoryResponse]) => {
      if (!active) return;
      const productData = productResponse.data;
      const categoryData = categoryResponse.data;
      setProducts(Array.isArray(productData) ? productData : (productData.results || []));
      const categoryRows = Array.isArray(categoryData) ? categoryData : (categoryData.results || []);
      setCategories(["All Products", ...categoryRows.map(category => category.name)]);
    }).catch(() => {
      if (active) setError("Products could not be loaded. Please check that the backend is running.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const visibleProducts = useMemo(() => products.filter(p => {
    const category = String(p.category_name || "").toLowerCase();
    const matchCategory = selectedCategory === "All Products" || category === selectedCategory.toLowerCase();
    const matchSearch = `${p.name || ""} ${p.description || ""} ${p.category_name || ""}`.toLowerCase().includes(search.toLowerCase());
    return matchCategory && matchSearch;
  }), [products, selectedCategory, search]);

  const addToCart = (product, buyNow = false) => {
    const item = { ...product, quantity: 1 };
    let cart = [];
    try { cart = JSON.parse(localStorage.getItem("cart") || "[]"); } catch { cart = []; }
    if (!Array.isArray(cart)) cart = [];
    const existing = cart.find(row => String(row.id) === String(product.id));
    if (existing && Number(existing.quantity || 0) >= Number(product.stock || 0)) {
      setCartMessage(`Only ${product.stock} of ${product.name} are available.`);
      return;
    }
    if (existing) existing.quantity = Math.min(Number(product.stock), Number(existing.quantity || 0) + 1);
    else cart.push(item);
    localStorage.setItem("cart", JSON.stringify(cart));
    window.dispatchEvent(new Event("cart:updated"));
    setCartMessage(`${product.name} added to your cart.`);
    if (buyNow) navigate("/checkout");
  };

  return <div className="cz-home">
    <header className="cz-home-header">
      <Link to="/" className="cz-home-brand">Comfort<span>Zone</span></Link>
      <nav className="cz-home-nav">
        <Link className="selected" to="/">Home</Link>
        <Link to="/about">About</Link>
        <a href="#categories">Categories</a>
        <Link to="/contact">Contact</Link>
      </nav>
      <div className="cz-home-actions">
        <Link className="cz-cart-link" to="/cart">🛒 Cart</Link>
        {localStorage.getItem("access")
          ? <Link className="cz-login-link" to={authorization.status === "ready" && authorization.isStaff
            ? firstAccessiblePath(authorization) : "/account/orders"}>My Account</Link>
          : <Link className="cz-login-link" to="/login">Login</Link>}
      </div>
    </header>

    <section className="cz-home-hero">
      <div className="cz-hero-copy">
        <p className="cz-eyebrow">WELCOME TO COMFORT ZONE</p>
        <h1>Make room for<br /><span>better living.</span></h1>
        <p>Thoughtfully designed furniture for every corner of your home. Discover comfort, quality, and timeless style.</p>
        <a className="cz-primary-btn" href="#products">Explore Products <span>→</span></a>
      </div>
      <div className="cz-hero-photo">
        <img src="https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1300&q=85" alt="Warm modern living room with comfortable furniture" />
        <div className="cz-photo-note"><strong>Designed for living</strong><span>Comfort in every detail</span></div>
      </div>
    </section>

    <section className="cz-shop-layout" id="products">
      <aside className="cz-category-panel" id="categories">
        <h2>Browse</h2>
        <p className="cz-panel-subtitle">Find your perfect piece</p>
        {categories.map(category => <button key={category} onClick={() => setSelectedCategory(category)} className={selectedCategory === category ? "cz-category active" : "cz-category"}>{category}<span>›</span></button>)}
        <div className="cz-help-card"><span>Need help?</span><p>We can help you find the right fit for your home.</p><Link to="/contact">Contact us →</Link></div>
      </aside>

      <main className="cz-products-area">
        <div className="cz-section-heading">
          <div><p className="cz-eyebrow">OUR COLLECTION</p><h2>{selectedCategory === "All Products" ? "Furniture for every space" : selectedCategory}</h2><p className="cz-muted">Explore pieces made to feel like home.</p></div>
          <input aria-label="Search products" className="cz-product-search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search furniture..." />
        </div>
        {error && <p className="cz-error">{error}</p>}
        {cartMessage && <p className="cz-cart-notice" role="status">{cartMessage} <Link to="/cart">View cart</Link></p>}
        {!error && loading && <p className="cz-muted" role="status">Loading products…</p>}
        {!error && !loading && products.length === 0 && <div className="cz-empty">No furniture is currently available.</div>}
        {visibleProducts.length > 0 ? <div className="cz-product-grid">
          {visibleProducts.map(product => {
            const stock = Number(product.stock ?? product.quantity ?? 0);
            return <article className="cz-product-card" key={product.id}>
              <Link className="cz-product-image" to={`/product/${product.id}`}><img src={product.image || product.image_url || "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=700&q=80"} alt={product.name} /><span className="cz-view-label">View details ↗</span></Link>
              <div className="cz-product-info">
                <p className="cz-product-category">{product.category_name || "Comfort Zone"}</p>
                <Link className="cz-product-name" to={`/product/${product.id}`}>{product.name}</Link>
                <div className="cz-product-bottom"><strong>₹{Number(product.price || 0).toLocaleString("en-IN")}</strong><span className={stock > 0 ? "cz-stock" : "cz-stock out"}>{stock > 0 ? "In stock" : "Out of stock"}</span></div>
                <div className="cz-product-buttons">
                  <Link className="cz-view-btn" to={`/product/${product.id}`}>View Product</Link>
                  <button className="cz-add-btn" disabled={stock <= 0} onClick={() => addToCart(product)}>Add to Cart +</button>
                </div>
              </div>
            </article>;
          })}
        </div> : !error && !loading && products.length > 0 && <div className="cz-empty">No products found. Try another category or search.</div>}
      </main>
    </section>
    <footer className="cz-home-footer"><div><Link to="/" className="cz-home-brand">Comfort<span>Zone</span></Link><p>Furniture that makes every day feel better.</p></div><div className="cz-footer-links"><Link to="/about">About Us</Link><Link to="/contact">Contact</Link><Link to="/cart">Shopping Cart</Link></div><small>© {new Date().getFullYear()} Comfort Zone. All rights reserved.</small></footer>
  </div>;
}
export default Home;
