
// frontend/src/pages/VendorManageProducts.jsx

import { useCallback, useEffect, useState } from "react";
import api, { API_BASE_URL } from "../servicess/api";
import { Link } from "react-router-dom";
import "../css/VendorPages.css";
import VendorPageNav from "../components/Router/VendorPageNav";

const API = "vendor/products/";

const getHeaders = () => {
  const token =
    localStorage.getItem("access") || localStorage.getItem("token");

  return {
    Authorization: `Bearer ${token}`,
  };
};

const getList = (data) => {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.products)) return data.products;
  return [];
};

function VendorManageProducts() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadProducts = useCallback(async () => {
    try {
      const response = await api.get(API, {
        headers: getHeaders(),
      });
      setProducts(getList(response.data));
      setError("");
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          "Could not load your products. Check your login and Django API."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.get(API, { headers: getHeaders() }).then((response) => {
      if (active) {
        setProducts(getList(response.data));
        setError("");
      }
    }).catch((err) => {
      if (active) setError(err.response?.data?.detail || "Could not load your products.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const refreshProducts = () => {
    setLoading(true);
    setError("");
    loadProducts();
  };

  const deleteProduct = async (product) => {
    if (!window.confirm(`Delete "${product.name}"?`)) return;

    setError("");
    setMessage("");

    try {
      await api.delete(`${API}${product.id}/`, {
        headers: getHeaders(),
      });

      setProducts((previous) =>
        previous.filter((item) => item.id !== product.id)
      );
      setMessage("Product deleted successfully.");
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Unable to delete this product. Check the backend delete endpoint."
      );
    }
  };

  const filteredProducts = products.filter((product) =>
    [
      product.name,
      product.category,
      product.description,
      String(product.id),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const getImageUrl = (image) => {
    if (!image) return "";
    if (image.startsWith("http://") || image.startsWith("https://")) {
      return image;
    }
    return image.startsWith("http") ? image : new URL(image, API_BASE_URL).href;
  };

  return (
    <main className="vendor-page">
      <div className="vendor-page-header">
        <div>
          <p className="vendor-eyebrow">VENDOR INVENTORY</p>
          <h1>Manage Products</h1>
          <p>Products you add are saved in your Django database.</p>
        </div>

        <Link className="vendor-primary-button" to="/vendor/add-product">
          + Add Product
        </Link>
      </div>

      <VendorPageNav />

      <div className="vendor-stats">
        <div className="vendor-stat-card">
          <span>Total Products</span>
          <strong>{products.length}</strong>
        </div>
        <div className="vendor-stat-card">
          <span>Total Stock Units</span>
          <strong>
            {products.reduce(
              (sum, product) => sum + Number(product.quantity || 0),
              0
            )}
          </strong>
        </div>
        <div className="vendor-stat-card">
          <span>Out of Stock</span>
          <strong>
            {products.filter((product) => Number(product.quantity || 0) <= 0)
              .length}
          </strong>
        </div>
      </div>

      <section className="vendor-panel">
        <div className="vendor-toolbar">
          <h2>Your Products</h2>
          <input
            type="search"
            placeholder="Search by name or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="vendor-secondary-button"
            type="button"
            onClick={refreshProducts}
          >
            Refresh
          </button>
        </div>

        {error && <p className="vendor-alert error">{error}</p>}
        {message && <p className="vendor-alert success">{message}</p>}

        {loading ? (
          <p className="vendor-empty">Loading products...</p>
        ) : filteredProducts.length === 0 ? (
          <div className="vendor-empty">
            <p>{search ? "No matching products." : "You have not added any products yet."}</p>
            {!search && (
              <Link to="/vendor/add-product">Add your first product</Link>
            )}
          </div>
        ) : (
          <div className="vendor-table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Category</th>
                  <th>Price</th>
                  <th>Quantity</th>
                  <th>Stock Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((product) => (
                  <tr key={product.id}>
                    <td>
                      <div className="vendor-product-cell">
                        {product.image && (
                          <img
                            src={getImageUrl(product.image)}
                            alt={product.name}
                            className="vendor-product-image"
                          />
                        )}
                        <div>
                          <strong>{product.name}</strong>
                          <small>ID: {product.id}</small>
                        </div>
                      </div>
                    </td>
                    <td>{product.category || "—"}</td>
                    <td>₹{Number(product.price || 0).toLocaleString("en-IN")}</td>
                    <td>{Number(product.quantity || 0)}</td>
                    <td>
                      <span
                        className={`vendor-stock ${
                          Number(product.quantity || 0) > 0
                            ? "in-stock"
                            : "out-stock"
                        }`}
                      >
                        {Number(product.quantity || 0) > 0
                          ? "In stock"
                          : "Out of stock"}
                      </span>
                    </td>
                    <td>
                      <button
                        className="vendor-danger-button"
                        type="button"
                        onClick={() => deleteProduct(product)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default VendorManageProducts;
