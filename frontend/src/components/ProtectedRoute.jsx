/*
 * ProtectedRoute Component
 * --------------------
 * Handles routing and access during authentication process.
 */

/* External Libraries */
import { Navigate, Outlet } from "react-router-dom";

// Internal Imports
import { useAuth } from "../auth/AuthProvider";

function ProtectedRoute() {
    const { user, loading } = useAuth();

    if (loading) return null;
    if (!user) return <Navigate to="/login" />;

    return <Outlet />;
}

export default ProtectedRoute;