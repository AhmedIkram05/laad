/*
 * Login Page
 * --------------------
 * Handles user logins.
 */

/* External Libraries */
import { useNavigate, useSearchParams } from "react-router-dom";
import { useState } from "react";

/* Internal Imports */
import { useAuth } from "../auth/AuthProvider";
import "./Login.css";

const API_BASE_URL = "http://localhost:8000";

function Login() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    // Sets states for username, password, error and loading
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const { login } = useAuth();

    // This is used to handle logins in the form
    const handleLogin = async () => {
        setError("");

        // Checks if Username or Password not entered
        if (!username || !password) {
            setError("Please enter your username and password.");
            return;
        }

        // adds username and password to url parameters
        const formData = new URLSearchParams();
        formData.append("username", username);
        formData.append("password", password);

        setLoading(true);

        try {
            // Try to connect to /auth/login endpoint, sending the username and password, and getting JWT back
            const res = await fetch(`${API_BASE_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData.toString(),
            });

            const data = await res.json();

            if (!res.ok) {
                setError(data.detail ?? "Login failed.");
                return;
            }

            // store token via AuthProvider (it will fetch /auth/me API endpoint)
            login(data.access_token);
            navigate("/dashboard");
        } catch {
            setError("Could not reach the server. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="loginPage">
            <div className="loginBox">
                <h1 className="loginTitle">Log In</h1>

                {searchParams.get("registered") === "1" && <p className="loginSuccess">Account created. Please sign in.</p>}
                {error && <p className="loginError">{error}</p>}

                {/* Username */}
                <label htmlFor="username">Username:</label>
                <input type="text" id="username" name="username" className="loginInput" value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLogin()} />

                {/* Password */}
                <label htmlFor="password">Password:</label>
                <input type="password" id="password" name="password" className="loginInput" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLogin()} />

                {/* Login & Sign Up Buttons */}
                <div className="loginButtonContainer">
                    <button className="loginButton--primary" onClick={handleLogin}>
                        Login
                    </button>
                    <button className="loginButton--secondary" onClick={() => navigate('/signup')}>
                        Create account
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Login;