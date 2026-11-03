import { NavLink } from "react-router-dom";

function VendorSidebar() {

    return (

        <aside className="vendor-sidebar">

            <h2>
                Comfort Zone
            </h2>

            <h3>
                Vendor Panel
            </h3>

            <nav>

                <NavLink
                    to="/vendor/add-product"
                >
                    ➕ Add Product
                </NavLink>

                <NavLink
                    to="/vendor/products"
                >
                    🛋️ My Products
                </NavLink>

                <NavLink
                    to="/vendor/orders"
                >
                    📦 Orders
                </NavLink>

                <NavLink
                    to="/vendor/profile"
                >
                    👤 Profile
                </NavLink>

            </nav>

        </aside>
    );
}

export default VendorSidebar;