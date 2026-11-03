
import { useCallback, useEffect, useState } from "react";
import api from "../servicess/api";
import "../css/Manageuser.css";

const API_URL = "admin/users/";

function ManageUser() {
    const [users, setUsers] = useState([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const fetchUsers = useCallback(async () => {
        try {
            const response = await api.get(API_URL);
            const data = response.data;

            setUsers(
                Array.isArray(data)
                    ? data
                    : data.results || data.users || []
            );
            setError("");
        } catch {
            setError(
                "Unable to load users. Check your Django API URL."
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
            setUsers(Array.isArray(data) ? data : data.results || data.users || []);
            setError("");
        }).catch(() => {
            if (active) setError("Unable to load users. Check your Django API URL.");
        }).finally(() => {
            if (active) setLoading(false);
        });
        return () => { active = false; };
    }, []);

    const refreshUsers = () => {
        setLoading(true);
        fetchUsers();
    };

    const deleteUser = async (id) => {
        if (!window.confirm("Deactivate this user account? Existing order history will be kept.")) {
            return;
        }

        try {
            await api.delete(`${API_URL}${id}/`);
            setUsers((previous) =>
                previous.filter((user) => user.id !== id)
            );
        } catch {
            alert("Unable to deactivate user. Check your API permissions.");
        }
    };

    const filteredUsers = users.filter((user) =>
        [
            user.username,
            user.name,
            user.first_name,
            user.last_name,
            user.email,
            user.phone
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(search.toLowerCase())
    );

    return (
        <div className="admin-page users-page">
            <div className="admin-page-header">
                <div>
                    <p className="admin-eyebrow">ADMINISTRATION</p>
                    <h1>Manage Users</h1>
                    <p className="admin-subtitle">
                        View and manage registered customers.
                    </p>
                </div>

                <button className="admin-refresh-btn" onClick={refreshUsers}>
                    ↻ Refresh
                </button>
            </div>

            <div className="admin-stats">
                <div className="admin-stat-card">
                    <span>Total Users</span>
                    <strong>{users.length}</strong>
                </div>

                <div className="admin-stat-card">
                    <span>Search Results</span>
                    <strong>{filteredUsers.length}</strong>
                </div>
            </div>

            <div className="admin-table-card">
                <div className="admin-table-toolbar">
                    <h2>Registered Users</h2>

                    <input
                        type="search"
                        placeholder="Search name or email..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="admin-search"
                    />
                </div>

                {loading ? (
                    <p className="admin-message">Loading users...</p>
                ) : error ? (
                    <p className="admin-error">{error}</p>
                ) : (
                    <div className="admin-table-wrapper">
                        <table className="admin-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>User</th>
                                    <th>Email</th>
                                    <th>Phone</th>
                                    <th>Role</th>
                                    <th>Action</th>
                                </tr>
                            </thead>

                            <tbody>
                                {filteredUsers.map((user) => (
                                    <tr key={user.id}>
                                        <td>#{user.id}</td>
                                        <td>
                                            <strong>
                                                {user.username ||
                                                    user.name ||
                                                    `${user.first_name || ""} ${user.last_name || ""}`.trim() ||
                                                    "Unnamed"}
                                            </strong>
                                        </td>
                                        <td>{user.email || "—"}</td>
                                        <td>{user.phone || "—"}</td>
                                        <td>
                                            <span className="admin-role">
                                                {user.role ||
                                                    (user.is_staff
                                                        ? "Admin"
                                                        : "User")}
                                            </span>
                                        </td>
                                        <td>
                                            <button
                                                className="admin-delete-btn"
                                                onClick={() =>
                                                    deleteUser(user.id)
                                                }
                                            >
                                                            Deactivate
                                            </button>
                                        </td>
                                    </tr>
                                ))}

                                {filteredUsers.length === 0 && (
                                    <tr>
                                        <td colSpan="6" className="admin-empty">
                                            No users found.
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

export default ManageUser;
