/*
 * AuthProvider
 * --------------------
 * Creates a global authentication system.
 */

/* External Libraries */
import React, { useEffect, useState } from "react";
import { AuthContext } from "./useAuth";

const API_BASE_URL = "http://localhost:8000";

export function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem("jwt") || null);
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(Boolean(token));

    useEffect(() => {
        let mounted = true;

        const load = async () => {
            if (!token) {
                setUser(null);
                setLoading(false);
                return;
            }

            setLoading(true);
            try {
                const res = await fetch(`${API_BASE_URL}/auth/me`, {
                    headers: { Authorization: `Bearer ${token}` },
                });

                if (!res.ok) {
                    localStorage.removeItem("jwt");
                    setToken(null);
                    setUser(null);
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
        if (!newToken) return;
        localStorage.setItem("jwt", newToken);
        setToken(newToken);
    };

    const logout = () => {
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

