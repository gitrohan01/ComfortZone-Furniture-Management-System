import { useCallback, useEffect, useState } from "react";
import AdminSidebar from "../components/Router/AdminSidebar";
import api from "../servicess/api";
import "../css/AdminDashboard.css";
import "../css/AdminVendorPurchase.css";

function getApiError(error) {
    const data = error.response?.data;
    if (typeof data === "string") return data;
    if (data?.detail || data?.message) return data.detail || data.message;
    if (data && typeof data === "object") {
        return Object.entries(data)
            .map(([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join(" ") : messages}`)
            .join(" ");
    }
    return error.message || "Please check your connection and try again.";
}

function AdminVendorPurchase() {
    const [vendors, setVendors] = useState([]);
    const [products, setProducts] = useState([]);
    const [vendor, setVendor] = useState("");
    const [product, setProduct] = useState("");
    const [quantity, setQuantity] = useState("");
    const [purchasePrice, setPurchasePrice] = useState("");
    const [vendorsLoading, setVendorsLoading] = useState(true);
    const [productsLoading, setProductsLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState(null);

    const loadProducts = useCallback(async (vendorId) => {
        if (!vendorId) {
            setProducts([]);
            setProductsLoading(false);
            return;
        }

        setProductsLoading(true);
        try {
            const response = await api.get("admin/products/");
            const data = Array.isArray(response.data)
                ? response.data
                : response.data.results || [];
            setProducts(data.filter((item) => Number(item.vendor) === Number(vendorId)));
        } catch (error) {
            setProducts([]);
            setMessage({ type: "error", text: `Unable to load products: ${getApiError(error)}` });
        } finally {
            setProductsLoading(false);
        }
    }, []);

    useEffect(() => {
        let active = true;
        api.get("admin/vendors/").then((response) => {
            const data = Array.isArray(response.data)
                ? response.data
                : response.data.results || [];
            if (active) setVendors(data);
        }).catch((error) => {
            if (active) {
                setMessage({ type: "error", text: `Unable to load vendors: ${getApiError(error)}` });
            }
        }).finally(() => {
            if (active) setVendorsLoading(false);
        });
        return () => { active = false; };
    }, []);

    const handleVendorChange = (event) => {
        const value = event.target.value;
        setVendor(value);
        setProduct("");
        setMessage(null);
        loadProducts(value);
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        setMessage(null);
        setSubmitting(true);

        try {
            const response = await api.post("admin/purchases/", {
                vendor: Number(vendor),
                product: Number(product),
                quantity: Number(quantity),
                purchase_price: purchasePrice,
            });
            setMessage({
                type: "success",
                text: `Purchase successful. New stock: ${response.data.new_stock}`,
            });
            setProducts((current) => current.map((item) => (
                item.id === Number(product)
                    ? { ...item, quantity: response.data.new_stock }
                    : item
            )));
            setQuantity("");
            setPurchasePrice("");
        } catch (error) {
            setMessage({ type: "error", text: `Purchase failed: ${getApiError(error)}` });
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="admin-dashboard">
            <AdminSidebar />
            <main className="admin-main">
                <div className="dashboard-container avp-container">
                    <header className="dashboard-header avp-header">
                        <div>
                            <p className="welcome-small">INVENTORY MANAGEMENT</p>
                            <h1>Purchase Stock From Vendor</h1>
                        </div>
                    </header>

                    <section className="dashboard-card avp-card" aria-labelledby="purchase-stock-title">
                        <div className="avp-card-heading">
                            <h2 id="purchase-stock-title">Vendor Stock Purchase</h2>
                            <p>Select a vendor and product, then enter the quantity and purchase price.</p>
                        </div>

                        {message && (
                            <p className={`avp-message avp-message-${message.type}`} role={message.type === "error" ? "alert" : "status"}>
                                {message.text}
                            </p>
                        )}

                        {vendorsLoading ? (
                            <p className="avp-state" role="status">Loading vendors...</p>
                        ) : vendors.length === 0 ? (
                            <p className="avp-state">No vendors are available for stock purchases.</p>
                        ) : (
                            <>
                            {vendor && !productsLoading && products.length === 0 && (
                                <p className="avp-state">This vendor has no products available.</p>
                            )}
                            <form className="avp-form" onSubmit={handleSubmit}>
                                <label htmlFor="purchase-vendor">Vendor</label>
                                <select
                                    id="purchase-vendor"
                                    value={vendor}
                                    onChange={handleVendorChange}
                                    required
                                >
                                    <option value="">Select Vendor</option>
                                    {vendors.map((item) => (
                                        <option key={item.id} value={item.id}>{item.business_name}</option>
                                    ))}
                                </select>

                                <label htmlFor="purchase-product">Product</label>
                                <select
                                    id="purchase-product"
                                    value={product}
                                    onChange={(event) => setProduct(event.target.value)}
                                    disabled={!vendor || productsLoading || products.length === 0}
                                    required
                                >
                                    <option value="">
                                        {productsLoading ? "Loading products..." : "Select Product"}
                                    </option>
                                    {products.map((item) => (
                                        <option key={item.id} value={item.id}>
                                            {item.name} - Current Stock: {item.quantity}
                                        </option>
                                    ))}
                                </select>
                                <label htmlFor="purchase-quantity">Quantity</label>
                                <input
                                    id="purchase-quantity"
                                    type="number"
                                    min="1"
                                    step="1"
                                    value={quantity}
                                    onChange={(event) => setQuantity(event.target.value)}
                                    required
                                />

                                <label htmlFor="purchase-price">Purchase Price</label>
                                <input
                                    id="purchase-price"
                                    type="number"
                                    min="0.01"
                                    step="0.01"
                                    value={purchasePrice}
                                    onChange={(event) => setPurchasePrice(event.target.value)}
                                    required
                                />

                                <div className="avp-form-actions">
                                    <button
                                        type="submit"
                                        className="avp-submit"
                                        disabled={submitting || productsLoading || !product}
                                    >
                                        {submitting ? "Processing Purchase..." : "Purchase Stock"}
                                    </button>
                                </div>
                            </form>
                            </>
                        )}
                    </section>
                </div>
            </main>
        </div>
    );
}

export default AdminVendorPurchase;
