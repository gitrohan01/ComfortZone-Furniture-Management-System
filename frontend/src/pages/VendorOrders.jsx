
// frontend/src/pages/VendorOrders.jsx

import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import "../css/VendorPages.css";
import VendorPageNav from "../components/Router/VendorPageNav";

const API = "vendor/orders/";

const getHeaders = () => {
  const token =
    localStorage.getItem("access") || localStorage.getItem("token");
  return { Authorization: `Bearer ${token}` };
};

const getList = (data) => {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.orders)) return data.orders;
  return [];
};

const getStatus = (order) =>
  order.status || order.order_status || "Pending";

const getCustomer = (order) =>
  order.customer_name ||
  order.customer?.username ||
  order.user_name ||
  order.user?.username ||
  order.user?.email ||
  "Customer";

const getTotal = (order) =>
  order.total_amount ?? order.total ?? order.grand_total ?? order.amount ?? 0;

function VendorOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadOrders = useCallback(async () => {
    try {
      const response = await api.get(API, { headers: getHeaders() });
      setOrders(getList(response.data));
      setError("");
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          "Could not load orders. Confirm that /api/vendor/orders/ exists in Django."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api.get(API, { headers: getHeaders() }).then((response) => {
      if (active) {
        setOrders(getList(response.data));
        setError("");
      }
    }).catch((err) => {
      if (active) setError(err.response?.data?.detail || "Could not load orders.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const refreshOrders = () => {
    setLoading(true);
    setError("");
    loadOrders();
  };

  const totalSales = orders.reduce(
    (sum, order) => sum + Number(getTotal(order) || 0),
    0
  );

  return (
    <main className="vendor-page">
      <div className="vendor-page-header">
        <div>
          <p className="vendor-eyebrow">SALES MANAGEMENT</p>
          <h1>Vendor Orders</h1>
          <p>Review orders associated with your products.</p>
        </div>

        <button
          className="vendor-secondary-button"
          type="button"
          onClick={refreshOrders}
        >
          Refresh Orders
        </button>
      </div>

      <VendorPageNav />

      <div className="vendor-stats">
        <div className="vendor-stat-card">
          <span>Total Orders</span>
          <strong>{orders.length}</strong>
        </div>
        <div className="vendor-stat-card">
          <span>Total Order Value</span>
          <strong>₹{totalSales.toLocaleString("en-IN")}</strong>
        </div>
        <div className="vendor-stat-card">
          <span>Pending Orders</span>
          <strong>
            {orders.filter(
              (order) => getStatus(order).toLowerCase() === "pending"
            ).length}
          </strong>
        </div>
      </div>

      <section className="vendor-panel">
        <h2>Orders List</h2>

        {error && <p className="vendor-alert error">{error}</p>}

        {loading ? (
          <p className="vendor-empty">Loading orders...</p>
        ) : orders.length === 0 ? (
          <p className="vendor-empty">No orders found for your products.</p>
        ) : (
          <div className="vendor-table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Customer</th>
                  <th>Order Date</th>
                  <th>Status</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>#{order.order_number || order.id}</td>
                    <td>{getCustomer(order)}</td>
                    <td>
                      {order.created_at || order.order_date
                        ? new Date(
                            order.created_at || order.order_date
                          ).toLocaleDateString("en-IN")
                        : "—"}
                    </td>
                    <td>
                      <span className="vendor-stock">
                        {getStatus(order)}
                      </span>
                    </td>
                    <td>
                      ₹{Number(getTotal(order) || 0).toLocaleString("en-IN")}
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

export default VendorOrders;
