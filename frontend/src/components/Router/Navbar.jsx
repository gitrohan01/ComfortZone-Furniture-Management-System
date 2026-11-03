import { NavLink } from "react-router-dom";

import "./Navbar.css";

function Navbar() {
    return (
        <nav className="cz-navbar">

            <div className="cz-navbar-inner">

                {/* Logo */}
                <NavLink to="/" className="cz-logo">
                    Comfort Zone
                </NavLink>

                {/* Navigation Menu */}
                <ul className="cz-menu">

                    <li>
                        <NavLink
                            to="/"
                            className={({ isActive }) =>
                                isActive
                                    ? "cz-link active"
                                    : "cz-link"
                            }
                        >
                            Home
                        </NavLink>
                    </li>

                    <li>
                        <NavLink
                            to="/about"
                            className={({ isActive }) =>
                                isActive
                                    ? "cz-link active"
                                    : "cz-link"
                            }
                        >
                            About Us
                        </NavLink>
                    </li>


                    <li>
                        <NavLink
                            to="/contact"
                            className={({ isActive }) =>
                                isActive
                                    ? "cz-link active"
                                    : "cz-link"
                            }
                        >
                            Contact Us
                        </NavLink>
                    </li>
                    <li>
                        <NavLink to="/cart" className="cz-link">Cart</NavLink>
                    </li>

                </ul>

                {/* Login */}
                <NavLink
                    to="/login"
                    className="cz-login"
                >
                    Login
                </NavLink>

                

            </div>

        </nav>
    );
}

export default Navbar;