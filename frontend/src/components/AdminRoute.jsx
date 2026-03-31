import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

function AdminRoute() {
    const { user, loading } = useAuth();

    if (loading) return null;
    if (!user) return <Navigate to="/login" />;
    if (user.role !== "admin") return <Navigate to="/dashboard" />;

    return <Outlet />;
}

export default AdminRoute;
