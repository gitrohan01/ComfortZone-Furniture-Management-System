
import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import "../css/ViewOrder.css";

const API_URL = "admin/orders/";

const ORDER_STATUSES = [
    "pending",
    "confirmed",
    "shipped",
    "delivered",
    "cancelled"
];

function ViewOrders() {
    const [orders, setOrders] = useState([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [savingId, setSavingId] = useState(null);

    const fetchOrders = useCallback(async () => {
        try {
            const response = await api.get(API_URL);
            const data = response.data;

            setOrders(
                Array.isArray(data)
                    ? data
                    : data.results || data.orders || []
            );
            setError("");
        } catch {
            setError(
                "Unable to load orders. Check your Django API URL."
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
            setOrders(Array.isArray(data) ? data : data.results || data.orders || []);
            setError("");
        }).catch(() => {
            if (active) setError("Unable to load orders. Check your Django API URL.");
        }).finally(() => {
            if (active) setLoading(false);
        });
        return () => { active = false; };
    }, []);

    const refreshOrders = () => {
        setLoading(true);
        setError("");
        fetchOrders();
    };

    const updateStatus = async (order, newStatus) => {
        const oldStatus = order.status || "pending";

        if (newStatus === oldStatus) return;

        try {
            setSavingId(order.id);

            await api.patch(`admin/orders/${order.id}/status/`, {
                status: newStatus
            });

            setOrders((previous) =>
                previous.map((item) =>
                    item.id === order.id
                        ? { ...item, status: newStatus }
                        : item
                )
            );
        } catch {
            alert(
                "Unable to update order status. Check your Django API."
            );
        } finally {
            setSavingId(null);
        }
    };

    const filteredOrders = orders.filter((order) => {
        const customer =
            order.customer_name ||
            order.user_name ||
            order.username ||
            order.user?.username ||
            order.user?.email ||
            "";

        return `${order.id} ${customer} ${order.status || ""}`
            .toLowerCase()
            .includes(search.toLowerCase());
    });

    const getAmount = (order) =>
        order.total_amount ??
        order.total_price ??
        order.total ??
        order.amount ??
        0;

    const getCustomer = (order) =>
        order.customer_name ||
        order.user_name ||
        order.username ||
        order.user?.username ||
        order.user?.email ||
        "Customer";

    const getStatusClass = (status) =>
        (status || "Pending")
            .toLowerCase()
            .replace(/\s+/g, "-");

    return (
        <div className="admin-page orders-page">
            <div className="admin-page-header">
                <div>
                    <p className="admin-eyebrow">ORDER MANAGEMENT</p>
                    <h1>View Orders</h1>
                    <p className="admin-subtitle">
                        Track customer purchases and delivery status.
                    </p>
                </div>

                <button
                    className="orders-refresh-btn"
                    onClick={refreshOrders}
                >
                    ↻ Refresh
                </button>
            </div>

            <div className="orders-summary">
                <div className="orders-summary-card">
                    <span>Total Orders</span>
                    <strong>{orders.length}</strong>
                </div>

                <div className="orders-summary-card">
                    <span>Pending Orders</span>
                    <strong>
                        {orders.filter(
                            (order) =>
                                (order.status || "Pending").toLowerCase() ===
                                "pending"
                        ).length}
                    </strong>
                </div>

                <div className="orders-summary-card">
                    <span>Delivered Orders</span>
                    <strong>
                        {orders.filter(
                            (order) =>
                                (order.status || "").toLowerCase() ===
                                "delivered"
                        ).length}
                    </strong>
                </div>
            </div>

            <div className="orders-table-card">
                <div className="orders-toolbar">
                    <h2>Customer Orders</h2>

                    <input
                        type="search"
                        className="orders-search"
                        placeholder="Search order or customer..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                {loading ? (
                    <p className="orders-message">Loading orders...</p>
                ) : error ? (
                    <p className="orders-error">{error}</p>
                ) : (
                    <div className="orders-table-scroll">
                        <table className="orders-table">
                            <thead>
                                <tr>
                                    <th>Order ID</th>
                                    <th>Customer</th>
                                    <th>Order Date</th>
                                    <th>Total</th>
                                    <th>Status</th>
                                </tr>
                            </thead>

                            <tbody>
                                {filteredOrders.map((order) => {
                                    const status =
                                        order.status || "Pending";

                                    return (
                                        <tr key={order.id}>
                                            <td>
                                                <strong>#{order.id}</strong>
                                            </td>

                                            <td>{getCustomer(order)}</td>

                                            <td>
                                                {order.created_at ||
                                                order.order_date
                                                    ? new Date(
                                                        order.created_at ||
                                                        order.order_date
                                                    ).toLocaleDateString()
                                                    : "—"}
                                            </td>

                                            <td>
                                                ₹
                                                {Number(
                                                    getAmount(order)
                                                ).toLocaleString("en-IN")}
                                            </td>

                                            <td>
                                                <div className="order-status-cell">
                                                    <span
                                                        className={`order-status ${getStatusClass(status)}`}
                                                    >
                                                        {status}
                                                    </span>

                                                    <select
                                                        aria-label={`Update status for order ${order.id}`}
                                                        value={status}
                                                        disabled={
                                                            savingId === order.id
                                                        }
                                                        onChange={(e) =>
                                                            updateStatus(
                                                                order,
                                                                e.target.value
                                                            )
                                                        }
                                                        className="order-status-select"
                                                    >
                                                        {!ORDER_STATUSES.includes(
                                                            status
                                                        ) && (
                                                            <option value={status}>
                                                                {status}
                                                            </option>
                                                        )}

                                                        {ORDER_STATUSES.map(
                                                            (option) => (
                                                                <option
                                                                    key={option}
                                                                    value={option}
                                                                >
                                                                    {option}
                                                                </option>
                                                            )
                                                        )}
                                                    </select>

                                                    {savingId === order.id && (
                                                        <small>Saving...</small>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}

                                {filteredOrders.length === 0 && (
                                    <tr>
                                        <td
                                            colSpan="5"
                                            className="orders-empty"
                                        >
                                            No orders found.
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

export default ViewOrders;
