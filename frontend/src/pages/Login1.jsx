import { useState } from "react";
import api from "../api";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { normalizeAuthorization, firstAccessiblePath } from "../auth/authorization";
import "./Login1.css";


function Login1() {

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [message, setMessage] = useState("");

    const navigate = useNavigate();
    const location = useLocation();


    const login = async (e) => {

        e.preventDefault();

        setMessage("");

        try {

            const response = await api.post(
                "auth/login/",
                {
                    username: username,
                    password: password
                }
            );


            // -----------------------------------------
            // Save JWT
            // -----------------------------------------

            localStorage.setItem(
                "access",
                response.data.access
            );

            localStorage.setItem(
                "refresh",
                response.data.refresh
            );
            window.dispatchEvent(new Event("auth:changed"));


            // -----------------------------------------
            // Save user information
            // -----------------------------------------

            localStorage.setItem(
                "user",
                JSON.stringify(response.data.user)
            );


            // -----------------------------------------
            // Get role
            // -----------------------------------------

            const permissionResponse = await api.get("auth/permissions/");
            const authorization = normalizeAuthorization(permissionResponse.data);
            if (!authorization) {
                throw new Error("The server did not return valid account permissions.");
            }


            // -----------------------------------------
            // Redirect
            // -----------------------------------------

            const requestedPath = location.state?.from;
            const safePath = typeof requestedPath === "string" && requestedPath.startsWith("/") && !requestedPath.startsWith("//")
                ? requestedPath
                : "/account/orders";
            navigate(authorization.isStaff ? firstAccessiblePath(authorization) : safePath, { replace: true });

        } catch (error) {
            localStorage.removeItem("access");
            localStorage.removeItem("refresh");
            localStorage.removeItem("user");
            window.dispatchEvent(new Event("auth:expired"));

            if (error.response) {

                setMessage(
                        error.response.data.detail || error.response.data.message ||
                    "Login failed."
                );

            } else {

                setMessage(
                    "Unable to connect to server."
                );

            }

        }

    };


    return (

        <div className="login-page">

            <div className="login-container">

                <h1>Login</h1>

                <p>
                    {location.state?.message || "Login to your Comfort Zone account"}
                </p>


                <form onSubmit={login}>

                    <input
                        type="text"
                        placeholder="Username"
                        value={username}
                        onChange={(e) =>
                            setUsername(e.target.value)
                        }
                        required
                    />


                    <input
                        type="password"
                        placeholder="Password"
                        value={password}
                        onChange={(e) =>
                            setPassword(e.target.value)
                        }
                        required
                    />


                    <button type="submit">
                        Login
                    </button>

                </form>


                {message && (
                    <p className="login-message">
                        {message}
                    </p>
                )}


                <p className="register-link">

                    Don't have an account?

                    {" "}

                    <Link to="/register" state={location.state}>
                        Register
                    </Link>

                </p>
                <p className="register-link"><Link to="/admin/login">Administrator sign in</Link></p>

            </div>

        </div>

    );
}


export default Login1;
