/*
 * AuthProvider
 * --------------------
 * Creates a global authentication system.
 */

/* External Libraries */
import React, { useEffect, useState } from "react";
import { AuthContext } from "./useAuth";

// All API calls use relative paths — CloudFront proxies /auth/* to the ALB
const API_BASE_URL = "";

export function AuthProvider({ children }) {
    // Legacy localStorage token kept as fallback; httpOnly cookie is primary.
    const [token, setToken] = useState(() => localStorage.getItem("jwt") || null);
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;

        const load = async () => {
            setLoading(true);
            try {
                const res = await fetch(`${API_BASE_URL}/auth/me`, {
                    credentials: "include",
                    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
                });

                if (!res.ok) {
                    localStorage.removeItem("jwt");
                    if (mounted) {
                        setToken(null);
                        setUser(null);
                    }
                } else {
                    const data = await res.json();
                    if (mounted) setUser(data);
                }
            } catch {
                if (mounted) setUser(null);
            } finally {
                if (mounted) setLoading(false);
            }
        };

        load();
        return () => {
            mounted = false;
        };
    }, [token]);

    const login = (newToken) => {
        if (newToken) localStorage.setItem("jwt", newToken);
        setLoading(true); // Prevent ProtectedRoute from redirecting before /auth/me resolves
        setToken(newToken || null);
    };

    const logout = async () => {
        try {
            await fetch(`${API_BASE_URL}/auth/logout`, {
                method: "POST",
                credentials: "include",
                ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
            });
        } catch {
            // Clear local state even if the server call fails
        }
        localStorage.removeItem("jwt");
        setToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ token, user, loading, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}
