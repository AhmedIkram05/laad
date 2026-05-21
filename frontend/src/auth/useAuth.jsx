/*
 * useAuth Hook & AuthContext
 * ---------------------------
 * Provides the AuthContext and hook for the auth system.
 */

import { createContext, useContext } from "react";

export const AuthContext = createContext(null);

export const useAuth = () => {
    const ctx = useContext(AuthContext);
    if (ctx === null) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return ctx;
};
