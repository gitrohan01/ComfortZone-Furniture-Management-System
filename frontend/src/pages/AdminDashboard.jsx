import { useEffect, useState } from "react";
import api, { clearAuth } from "../servicess/api";
import { useNavigate } from "react-router-dom";

import AdminSidebar from "../components/Router/AdminSidebar";

import "../css/AdminDashboard.css";


function AdminDashboard() {

    const [user, setUser] = useState(null);
    const [totalUsers, setTotalUsers] = useState(0);

    const navigate = useNavigate();


    useEffect(() => {

        const token = localStorage.getItem("access");

        if (!token) {
            navigate("/login");
            return;
        }


        api.get("admin-dashboard/")
        .then((response) => {

            setUser(response.data.user);

            setTotalUsers(
                response.data.total_users
            );

        })
        .catch((error) => {

            if (
                error.response &&
                error.response.status === 403
            ) {

                navigate("/dashboard");

            }
            else {

                clearAuth();

                navigate("/login");

            }

        });

    }, [navigate]);


    const logout = async () => {
        const refresh = localStorage.getItem("refresh");
        try {
            if (refresh) await api.post("logout/", { refresh });
        } finally {
            clearAuth();
            navigate("/login");
        }
    };


    if (!user) {

        return (
            <h2 className="dashboard-loading">
                Loading...
            </h2>
        );

    }


    return (

        <div className="admin-dashboard">

            {/* LEFT SIDEBAR */}
            <AdminSidebar />


            {/* RIGHT SIDE */}
            <main className="admin-main">

                <div className="dashboard-container">


                    {/* Header */}
                    <div className="dashboard-header">

                        <div>

                            <p className="welcome-small">
                                ADMIN PANEL
                            </p>

                            <h1>
                                Welcome, {user.username}
                            </h1>

                        </div>


                        <button
                            className="dashboard-logout"
                            onClick={logout}
                        >
                            Logout
                        </button>

                    </div>


                    {/* Cards */}
                    <div className="dashboard-content">


                        <div className="dashboard-card">

                            <h2>
                                Admin Account
                            </h2>

                            <h3>
                                {user.username}
                            </h3>

                            <p>
                                Email: {user.email}
                            </p>

                            <p>
                                Role: Administrator
                            </p>

                        </div>


                        <div className="dashboard-card">

                            <h2>
                                Total Users
                            </h2>

                            <h3>
                                {totalUsers}
                            </h3>

                            <p>
                                Registered users
                            </p>

                        </div>


                    </div>


                </div>

            </main>

        </div>

    );

}


export default AdminDashboard;
