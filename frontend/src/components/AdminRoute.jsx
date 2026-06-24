/*
 * AdminRoute Component
 * --------------------
 * Handles routing and access during authentication process and restricts access to admin-only pages.
 */

// External Libraries
import { Navigate, Outlet } from "react-router-dom";

// Internal Imports
import { useAuth } from "../auth/useAuth";

function AdminRoute() {
    const { user, loading } = useAuth();

    if (loading) return null;
    if (!user) return <Navigate to="/login" />;
    if (user.role !== "admin") return <Navigate to="/dashboard" />;

    return <Outlet />;
}

export default AdminRoute;
