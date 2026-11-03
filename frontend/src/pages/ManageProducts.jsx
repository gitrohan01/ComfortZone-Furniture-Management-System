
import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import "../css/ManageProducts.css";

const API_URL = "admin/products/";

function ManageProducts() {
    const [products, setProducts] = useState([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const fetchProducts = useCallback(async () => {
        try {
            const response = await api.get(API_URL);
            const data = response.data;

            setProducts(
                Array.isArray(data)
                    ? data
                    : data.results || data.products || []
            );
            setError("");
        } catch {
            setError(
                "Unable to load products. Check your Django API URL."
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        let active = true;
        api.get(API_URL).then((response) => {
            if (!active) return;
            const data = response.data;
            setProducts(Array.isArray(data) ? data : data.results || data.products || []);
            setError("");
        }).catch(() => {
            if (active) setError("Unable to load products. Check your Django API URL.");
        }).finally(() => {
            if (active) setLoading(false);
        });
        return () => { active = false; };
    }, []);

    const refreshProducts = () => {
        setLoading(true);
        fetchProducts();
    };

    const deleteProduct = async (id) => {
        if (!window.confirm("Delete this product?")) {
            return;
        }

        try {
            await api.delete(`admin/products/${id}/`);
            setProducts((previous) =>
                previous.filter((product) => product.id !== id)
            );
        } catch {
            alert(
                "Unable to delete product. Check your API permissions."
            );
        }
    };

    const filteredProducts = products.filter((product) =>
        [
            product.name,
            product.title,
            product.category,
            product.description
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(search.toLowerCase())
    );

    return (
        <div className="admin-page products-page">
            <div className="admin-page-header">
                <div>
                    <p className="admin-eyebrow">INVENTORY</p>
                    <h1>Manage Products</h1>
                    <p className="admin-subtitle">
                        Monitor your furniture catalog and stock.
                    </p>
                </div>

                <button
                    className="product-refresh-btn"
                    onClick={refreshProducts}
                >
                    ↻ Refresh
                </button>
            </div>

            <div className="product-summary">
                <div className="product-summary-card">
                    <span>Total Products</span>
                    <strong>{products.length}</strong>
                </div>

                <div className="product-summary-card">
                    <span>Search Results</span>
                    <strong>{filteredProducts.length}</strong>
                </div>
            </div>

            <div className="product-table-card">
                <div className="product-toolbar">
                    <h2>Furniture Inventory</h2>

                    <input
                        type="search"
                        className="product-search"
                        placeholder="Search furniture..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                {loading ? (
                    <p className="product-message">Loading products...</p>
                ) : error ? (
                    <p className="product-error">{error}</p>
                ) : (
                    <div className="product-table-scroll">
                        <table className="product-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Product</th>
                                    <th>Category</th>
                                    <th>Price</th>
                                    <th>Stock</th>
                                    <th>Action</th>
                                </tr>
                            </thead>

                            <tbody>
                                {filteredProducts.map((product) => (
                                    <tr key={product.id}>
                                        <td>#{product.id}</td>
                                        <td>
                                            <strong>
                                                {product.name ||
                                                    product.title ||
                                                    "Unnamed product"}
                                            </strong>
                                        </td>
                                        <td>
                                            {product.category || "—"}
                                        </td>
                                        <td>
                                            ₹
                                            {Number(
                                                product.price ??
                                                product.selling_price ??
                                                0
                                            ).toLocaleString("en-IN")}
                                        </td>
                                        <td>
                                            <span
                                                className={
                                                    Number(product.quantity ?? 0) > 0
                                                        ? "stock-available"
                                                        : "stock-out"
                                                }
                                            >
                                                {product.quantity ?? "—"}
                                            </span>
                                        </td>
                                        <td>
                                            <button
                                                className="product-delete-btn"
                                                onClick={() =>
                                                    deleteProduct(product.id)
                                                }
                                            >
                                                Delete
                                            </button>
                                        </td>
                                    </tr>
                                ))}

                                {filteredProducts.length === 0 && (
                                    <tr>
                                        <td
                                            colSpan="6"
                                            className="product-empty"
                                        >
                                            No products found.
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

export default ManageProducts;
