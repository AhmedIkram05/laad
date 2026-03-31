import { useNavigate } from "react-router-dom";
import { useState } from "react";

import "./Login.css";

const API_BASE_URL = "http://localhost:8000";

function Signup() {
    const navigate = useNavigate();
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSignup = async () => {
        setError("");
        if (!username || !password) {
            setError("Please enter a username and password.");
            return;
        }
        if (password.length < 6) {
            setError("Password must be at least 6 characters.");
            return;
        }
        if (password !== confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });

            const data = await res.json();
            if (res.status === 201) {
                // Redirect to login with a flag so the login page can show a success message
                navigate("/login?registered=1");
                return;
            }

            setError(data.detail ?? data.message ?? "Registration failed.");
        } catch (e) {
            setError("Could not reach the server. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="loginPage">
            <div className="loginBox">
                <h1 className="loginTitle">Create Account</h1>

                {error && <p className="loginError">{error}</p>}

                <label htmlFor="username">Username:</label>
                <input type="text" id="username" name="username" className="loginInput" value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignup()} />

                <label htmlFor="password">Password:</label>
                <input type="password" id="password" name="password" className="loginInput" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignup()} />

                <label htmlFor="confirmPassword">Confirm Password:</label>
                <input type="password" id="confirmPassword" name="confirmPassword" className="loginInput" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSignup()} />

                <div className="loginButtonContainer">
                    <button className="loginButton" onClick={handleSignup} disabled={loading}>
                        Create account
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Signup;
