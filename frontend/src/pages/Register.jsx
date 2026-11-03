import { useState } from "react";
import api from "../api";
import { Link, useLocation, useNavigate } from "react-router-dom";
import "../css/Register.css";


function Register() {

    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");

    const [message, setMessage] = useState("");

    const navigate = useNavigate();
    const location = useLocation();


    const register = async (e) => {

        e.preventDefault();

        setMessage("");


        // Check password

        if (password !== confirmPassword) {

            setMessage("Passwords do not match.");

            return;
        }


        try {

            const response = await api.post(
                "register/",
                {
                    username: username,
                    email: email,
                    password: password,
                    confirm_password: confirmPassword
                }
            );


            // Show success message

            setMessage(
                response.data.message
            );


            // Clear form

            setUsername("");
            setEmail("");
            setPassword("");
            setConfirmPassword("");


            // Go to login page

            navigate("/login", { replace: true, state: { from: location.state?.from, message: "Your account is ready. Sign in to continue." } });


        } catch (error) {

            if (error.response) {

                const data = error.response.data;


                if (data.username) {

                    setMessage(
                        Array.isArray(data.username)
                            ? data.username[0]
                            : data.username
                    );

                }

                else if (data.email) {

                    setMessage(
                        Array.isArray(data.email)
                            ? data.email[0]
                            : data.email
                    );

                }

                else if (data.password) {

                    setMessage(
                        Array.isArray(data.password)
                            ? data.password[0]
                            : data.password
                    );

                }

                else if (data.confirm_password) {

                    setMessage(
                        Array.isArray(data.confirm_password)
                            ? data.confirm_password[0]
                            : data.confirm_password
                    );

                }

                else if (data.message) {

                    setMessage(data.message);

                }

                else {

                    setMessage(
                        "Registration failed."
                    );

                }

            }

            else {

                setMessage(
                    "Unable to connect to server."
                );

            }

        }

    };


    return (

        <div className="register-page">

            <div className="register-container">

                <h1>
                    Create Account
                </h1>

                <p>
                    Register as a new user
                </p>


                <form onSubmit={register}>

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
                        type="email"
                        placeholder="Email"
                        value={email}
                        onChange={(e) =>
                            setEmail(e.target.value)
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


                    <input
                        type="password"
                        placeholder="Confirm Password"
                        value={confirmPassword}
                        onChange={(e) =>
                            setConfirmPassword(e.target.value)
                        }
                        required
                    />


                    <button type="submit">
                        Register
                    </button>

                </form>


                {message && (

                    <p className="register-message">
                        {message}
                    </p>

                )}


                <p className="register-link">

                    Already have an account?

                    {" "}

                    <Link to="/login">
                        Login
                    </Link>

                </p>

            </div>

        </div>

    );

}


export default Register;
