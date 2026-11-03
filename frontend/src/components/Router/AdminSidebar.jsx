import { useState } from "react";
import { NavLink } from "react-router-dom";
import api from "../../servicess/api";
import "../../css/AdminSidebar.css";

async function getErrorMessage(error) {
    const data = error.response?.data;
    if (data instanceof Blob) {
        const text = await data.text();
        try {
            const parsed = JSON.parse(text);
            return parsed.detail || parsed.message || text;
        } catch {
            return text || "The server could not create this report.";
        }
    }
    if (typeof data === "string") return data;
    return data?.detail || data?.message || error.message || "The report could not be downloaded.";
}

function AdminSidebar() {
    const [downloadError, setDownloadError] = useState("");
    const [downloading, setDownloading] = useState("");

    const downloadReport = async (name) => {
        setDownloadError("");
        setDownloading(name);
        try {
            const response = await api.get(`admin/reports/${name}.csv`, {
                responseType: "blob",
            });
            const contentType = response.headers["content-type"] || "";
            if (!contentType.toLowerCase().includes("text/csv")) {
                throw new Error("The server returned an invalid report format.");
            }

            const disposition = response.headers["content-disposition"] || "";
            const fileName = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i)?.[1]
                ?.replace(/["']/g, "") || `${name}.csv`;
            const blob = response.data instanceof Blob
                ? response.data
                : new Blob([response.data], { type: contentType });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = fileName;
            link.style.display = "none";
            document.body.appendChild(link);
            link.click();
            link.remove();
            // Keep the object URL alive long enough for the browser to start saving it.
            window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) {
            setDownloadError(await getErrorMessage(error));
        } finally {
            setDownloading("");
        }
    };

    return (
        <aside className="admin-sidebar">
            <div className="admin-logo">Comfort Zone</div>
            <div className="admin-sidebar-line" />
            <div className="admin-title">Admin Panel</div>
            <NavLink to="/admin/manageuser" className="admin-sidebar-link">Manage Users</NavLink>
            <NavLink to="/admin/manage-products" className="admin-sidebar-link">Manage Products</NavLink>
            <NavLink to="/admin/orders" className="admin-sidebar-link">View Orders</NavLink>
            <NavLink to="/admin/vendor-purchase" className="admin-sidebar-link">Vendor Stock Purchases</NavLink>
            <button
                type="button"
                className="sidebar-menu-btn"
                onClick={() => downloadReport("inventory")}
                disabled={Boolean(downloading)}
            >
                {downloading === "inventory" ? "Preparing Inventory CSV..." : "Export Inventory CSV"}
            </button>
            <button
                type="button"
                className="sidebar-menu-btn"
                onClick={() => downloadReport("sales")}
                disabled={Boolean(downloading)}
            >
                {downloading === "sales" ? "Preparing Sales CSV..." : "Export Sales CSV"}
            </button>
            {downloadError && <p className="admin-export-error" role="alert">{downloadError}</p>}
        </aside>
    );
}

export default AdminSidebar;
