
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import Navbar from "./Navbar";
import Footer from "./Footer";

import Home from "../../pages/Home";
import About from "../About";
import Contactus from "../Contactus";
import Login1 from "../../pages/Login1";
import Register from "../../pages/Register";
import Dashboard from "../../pages/Dashboard";
import AdminDashboard from "../../pages/AdminDashboard";
import Sofa from "../../pages/Sofa";
import Beds from "../../pages/Beds";
import Dining from "../../pages/Dining";
import Wardrobe from "../../pages/Wardrobe";
import Teapoi from "../../pages/Teapoi";
import Chair from "../../pages/Chair";
import Dressing from "../../pages/Dressing";

import VendorAddProduct from "../../pages/VendorAddProduct";
import VendorManageProducts from "../../pages/VendorManageProducts";
import VendorOrders from "../../pages/VendorOrders";
import VendorProfile from "../../pages/VendorProfile";

import AdminVendorPurchase from "../../pages/AdminVendorPurchase";
import UserOrders from "../../pages/UserOrders";
import ProductList from "../../pages/ProductList";
import ProductDetails from "../../pages/ProductDetails";
import Cart from "../../pages/cart";
import ManageUsers from "../../pages/ManageUsers";
import ManageProduct from "../../pages/AdminManageProduct";
import ViewOrders from "../../pages/ViewOrders";
import Logout from "../../pages/Logout";

function RoleRoute({ roles, children }) {
    const token = localStorage.getItem("access");
    let user;
    try {
        user = JSON.parse(localStorage.getItem("user") || "null");
    } catch { /* Invalid stored data is treated as a signed-out session. */ }
    if (!token || !user) return <Navigate to="/login" replace />;
    if (roles && !roles.includes(user.role)) {
        return <Navigate to={user.role === "admin" ? "/admin-dashboard" : "/dashboard"} replace />;
    }
    return children;
}



function App1() {
    const location = useLocation();

    const dashboardPaths = [
        "/dashboard",
        "/admin-dashboard",
        "/admin/manageuser",
        "/admin/manage-products",
        "/admin/orders",
        "/admin/vendor-purchase",
        "/vendor/add-product",
        "/vendor/manage-products",
        "/vendor/orders",
        "/vendor/profile",
        "/user/orders",
        "/my-orders",
        "/admin/purchase-stock",
        "/logout",
    ];

    const isDashboardPage =
        dashboardPaths.includes(location.pathname);

    return (
        <>
            {!isDashboardPage && <Navbar />}

            <Routes>
                {/* Home */}
                <Route path="/" element={<Home />} />

                {/* General pages */}
                <Route path="/about" element={<About />} />
                <Route path="/contact" element={<Contactus />} />

                {/* Authentication */}
                <Route path="/login" element={<Login1 />} />
                <Route path="/register" element={<Register />} />
                <Route path="/logout" element={<Logout />} />

                {/* Dashboards */}
                <Route path="/dashboard" element={<RoleRoute roles={["user"]}><Dashboard /></RoleRoute>} />
                <Route
                    path="/admin-dashboard"
                    element={<RoleRoute roles={["admin"]}><AdminDashboard /></RoleRoute>}
                />

                {/* Products */}
                <Route path="/sofa" element={<Sofa />} />
                <Route path="/beds" element={<Beds />} />
                <Route path="/dining" element={<Dining />} />
                <Route path="/dinning_table" element={<Dining />} />
                <Route path="/wardrobe" element={<Wardrobe />} />
                <Route path="/teapoi" element={<Teapoi />} />
                <Route path="/chair" element={<Chair />} />
                <Route path="/dressing" element={<Dressing />} />
                <Route path="/dressing_table" element={<Dressing />} />
                <Route path="/products" element={<ProductList />} />
                <Route path="/cart" element={<Cart />} />
                <Route
                    path="/product/:id"
                    element={<ProductDetails />}
                />

                {/* Vendor pages */}
                <Route path="/vendor/add-product" element={<RoleRoute roles={["vendor"]}><VendorAddProduct /></RoleRoute>} />
                <Route path="/vendor/manage-products" element={<RoleRoute roles={["vendor"]}><VendorManageProducts /></RoleRoute>} />
                <Route path="/vendor/orders" element={<RoleRoute roles={["vendor"]}><VendorOrders /></RoleRoute>} />
                <Route path="/vendor/profile" element={<RoleRoute roles={["vendor"]}><VendorProfile /></RoleRoute>} />

                {/* Admin pages */}
                <Route
                    path="/admin/vendor-purchase"
                    element={<RoleRoute roles={["admin"]}><AdminVendorPurchase /></RoleRoute>}
                />
                <Route path="/admin/manageuser" element={<RoleRoute roles={["admin"]}><ManageUsers /></RoleRoute>} />
                <Route path="/admin/manage-products" element={<RoleRoute roles={["admin"]}><ManageProduct /></RoleRoute>} />
                <Route path="/admin/orders" element={<RoleRoute roles={["admin"]}><ViewOrders /></RoleRoute>} />

                {/* User pages */}
                <Route
                    path="/user/orders"
                    element={<RoleRoute roles={["user", "vendor"]}><UserOrders /></RoleRoute>}
                />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>

            {!isDashboardPage && <Footer />}
        </>
    );
}

export default App1;
