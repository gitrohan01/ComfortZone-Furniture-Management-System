import { useEffect, useState } from "react";
import api, { clearAuth } from "../servicess/api";
import {
    NavLink,
    useNavigate
} from "react-router-dom";

import "../css/Dashboard.css";


function Dashboard() {

    const [user, setUser] = useState(null);

    const navigate = useNavigate();


    useEffect(() => {

        const token = localStorage.getItem("access");

        if (!token) {
            navigate("/login");
            return;
        }


        api.get("dashboard/")
        .then((response) => {

            setUser(response.data.user);

        })
        .catch(() => {

            clearAuth();

            navigate("/login");

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
            <div className="dashboard-loading">
                <h2>Loading...</h2>
            </div>
        );

    }


    return (

        <div className="dashboard-page">


            {/* =========================
                LEFT SIDEBAR
            ========================= */}

            <aside className="dashboard-sidebar">

                <div className="sidebar-logo">
                    Comfort Zone
                </div>


                <div className="sidebar-user">

                    <div className="user-circle">
                        {user.username.charAt(0).toUpperCase()}
                    </div>

                    <h3>
                        {user.username}
                    </h3>

                    <p>
                        User Account
                    </p>

                </div>


                <nav className="sidebar-menu">


                    <NavLink
                        to="/dashboard"
                        className={({ isActive }) =>
                            isActive
                                ? "sidebar-link active"
                                : "sidebar-link"
                        }
                    >
                        <span>⌂</span>
                        Dashboard
                    </NavLink>


                    <NavLink
                        to="/user/orders"
                        className={({ isActive }) =>
                            isActive
                                ? "sidebar-link active"
                                : "sidebar-link"
                        }
                    >
                        My Orders
                    </NavLink>


                    <NavLink
                        to="/sofa"
                        className="sidebar-link"
                    >
                        {/* <span>⌂</span> */}
                        Sofa
                    </NavLink>


                    <NavLink
                        to="/beds"
                        className="sidebar-link"
                    >
                        {/* <span>ⓘ</span> */}
                        Bed
                    </NavLink>


                    <NavLink
                        to="/dinning_table"
                        className="sidebar-link"
                    >
                        {/* <span>🛋</span> */}
                        Dining Tables
                    </NavLink>


                    <NavLink
                        to="/wardrobe"
                        className="sidebar-link"
                    >
                        {/* <span>✉</span> */}
                        Wardrobe
                    </NavLink>

                    <NavLink
                        to="/teapoi"
                        className="sidebar-link"
                    >
                        {/* <span>✉</span> */}
                        Teapoi
                    </NavLink>

                    <NavLink
                        to="/chair"
                        className="sidebar-link"
                    >
                        {/* <span>✉</span> */}
                        Chair
                    </NavLink>

                    <NavLink
                        to="/dressing_table"
                        className="sidebar-link"
                    >
                        {/* <span>✉</span> */}
                        Dressing Table
                    </NavLink>

                    

                </nav>


                <div className="sidebar-bottom">

                    <button
                        className="sidebar-logout"
                        onClick={logout}
                    >
                        <span>↪</span>
                        Logout
                    </button>

                </div>

            </aside>


            {/* =========================
                RIGHT CONTENT
            ========================= */}

            <main className="dashboard-main">


                {/* Dashboard Header */}

                <div className="dashboard-container">


                    <div className="dashboard-header">

                        <div>

                            <p className="welcome-small">
                                WELCOME
                            </p>

                            <h1>
                                {user.username}
                            </h1>

                        </div>


                        <button
                            className="dashboard-logout"
                            onClick={logout}
                        >
                            Logout
                        </button>

                    </div>


                    {/* Dashboard Cards */}

                    <div className="dashboard-content">


                        {/* My Account */}

                        <div className="dashboard-card">

                            <h2>
                                My Account
                            </h2>

                            <h3>
                                {user.username}
                            </h3>

                            <p>
                                Email: {user.email}
                            </p>

                            <p>
                                Role: User
                            </p>

                        </div>


                        {/* Furniture */}

                        <div className="dashboard-card">

                            <h2>
                                Furniture
                            </h2>

                            <p>
                                Browse our furniture collection.
                            </p>


                            <NavLink
                                to="/beds"
                                className="browse-furniture-btn"
                            >
                                Browse Furniture
                            </NavLink>

                        </div>


                    </div>

                </div>

            </main>

        </div>

    );

}


export default Dashboard;
