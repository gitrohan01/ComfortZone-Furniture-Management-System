
import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import "../css/AdminManageProduct.css";

const API_URL = "admin/products/";

function ManageProduct() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const getToken = () => localStorage.getItem("access");

  const getProducts = useCallback(async () => {
    try {
      const response = await api.get(API_URL, {
        headers: {
          Authorization: `Bearer ${getToken()}`,
        },
      });

      setProducts(
        Array.isArray(response.data)
          ? response.data
          : response.data.results || []
      );
      setError("");
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Unable to load products. Please check your login and backend."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.get(API_URL).then((response) => {
      if (active) setProducts(Array.isArray(response.data) ? response.data : response.data.results || []);
    }).catch((err) => {
      if (active) setError(err.response?.data?.detail || "Unable to load products.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const refreshProducts = () => {
    setLoading(true);
    getProducts();
  };

  const toggleProductStatus = async (product) => {
    setError("");
    setMessage("");

    try {
      const response = await api.patch(
        `admin/products/${product.id}/status/`,
        { is_active: !product.is_active },
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
          },
        }
      );

      setProducts((previous) =>
        previous.map((item) =>
          item.id === product.id
            ? { ...item, is_active: response.data.is_active }
            : item
        )
      );

      setMessage(
        `Product ${response.data.is_active ? "published" : "hidden"} successfully.`
      );
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Unable to update product status."
      );
    }
  };

  const filteredProducts = products.filter((product) => {
    const text = [
      product.name,
      product.category,
      product.vendor_name,
      product.id,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return text.includes(search.toLowerCase());
  });

  return (
    <div className="manage-product-page">
      <div className="manage-product-header">
        <div>
          <p className="manage-product-subtitle">ADMINISTRATION</p>
          <h1>Manage Products</h1>
          <p className="manage-product-description">
            Manage furniture products supplied by your vendors.
          </p>
        </div>

        <button
          type="button"
          className="mp-refresh-button"
          onClick={refreshProducts}
        >
          ↻ Refresh
        </button>
      </div>

      <div className="mp-stat-grid">
        <div className="mp-stat-card">
          <span>Total Products</span>
          <h2>{products.length}</h2>
        </div>

        <div className="mp-stat-card">
          <span>Published Products</span>
          <h2>
            {products.filter((product) => product.is_active).length}
          </h2>
        </div>

        <div className="mp-stat-card">
          <span>Hidden Products</span>
          <h2>
            {products.filter((product) => !product.is_active).length}
          </h2>
        </div>
      </div>

      <div className="mp-product-panel">
        <div className="mp-toolbar">
          <div>
            <h2>Product Inventory</h2>
            <p>Review products and manage their visibility.</p>
          </div>

          <input
            type="search"
            className="mp-search"
            placeholder="Search product, category, vendor..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        {error && (
          <div className="mp-alert mp-alert-error">
            {error}
          </div>
        )}

        {message && (
          <div className="mp-alert mp-alert-success">
            {message}
          </div>
        )}

        {loading ? (
          <div className="mp-loading">Loading products...</div>
        ) : (
          <div className="mp-table-wrapper">
            <table className="mp-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Product Name</th>
                  <th>Category</th>
                  <th>Vendor</th>
                  <th>Price</th>
                  <th>Stock</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {filteredProducts.map((product) => (
                  <tr key={product.id}>
                    <td>#{product.id}</td>

                    <td className="mp-product-name">
                      {product.name || "Unnamed Product"}
                    </td>

                    <td>{product.category || "—"}</td>

                    <td>{product.vendor_name || "—"}</td>

                    <td>
                      ₹
                      {Number(product.price || 0).toLocaleString(
                        "en-IN"
                      )}
                    </td>

                    <td>{product.quantity ?? "—"}</td>

                    <td>
                      <span
                        className={`mp-status ${
                          product.is_active
                            ? "mp-status-active"
                            : "mp-status-hidden"
                        }`}
                      >
                        {product.is_active ? "Published" : "Hidden"}
                      </span>
                    </td>

                    <td>
                      <button
                        type="button"
                        className={`mp-action-button ${
                          product.is_active
                            ? "mp-hide-button"
                            : "mp-publish-button"
                        }`}
                        onClick={() => toggleProductStatus(product)}
                      >
                        {product.is_active ? "Hide" : "Publish"}
                      </button>
                    </td>
                  </tr>
                ))}

                {filteredProducts.length === 0 && (
                  <tr>
                    <td colSpan="8" className="mp-empty">
                      {search
                        ? "No matching products found."
                        : "No products available."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default ManageProduct;
