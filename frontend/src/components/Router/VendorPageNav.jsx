import { NavLink } from "react-router-dom";

export default function VendorPageNav() {
    return (
        <nav className="vendor-page-nav" aria-label="Vendor pages">
            <NavLink to="/vendor/manage-products" className={({ isActive }) =>
                isActive ? "vendor-primary-button" : "vendor-secondary-button"
            }>Inventory</NavLink>
            <NavLink to="/vendor/add-product" className={({ isActive }) =>
                isActive ? "vendor-primary-button" : "vendor-secondary-button"
            }>Add product</NavLink>
            <NavLink to="/vendor/orders" className={({ isActive }) =>
                isActive ? "vendor-primary-button" : "vendor-secondary-button"
            }>Orders</NavLink>
            <NavLink to="/vendor/profile" className={({ isActive }) =>
                isActive ? "vendor-primary-button" : "vendor-secondary-button"
            }>Profile</NavLink>
            <NavLink to="/logout" className="vendor-secondary-button">Logout</NavLink>
        </nav>
    );
}
