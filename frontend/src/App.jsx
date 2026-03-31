/* Import Libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";

/* Import Pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import Starred from "./pages/Starred";
import Completed from "./pages/Completed";
import AnomalyData from "./pages/AnomalyData";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import AdminSettings from "./pages/AdminSettings";
import AdminRoute from "./components/AdminRoute";
import ProtectedRoute from "./components/ProtectedRoute";

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                {/* Login Pathway */}
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Signup />} />
                {/* Redirect Root to Dashboard */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />

                {/* Set Main Layout to Pages */}
                <Route element={<ProtectedRoute />}>
                    <Route element={<MainLayout />}>
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/starred" element={<Starred />} />
                        <Route path="/completed" element={<Completed />} />
                        <Route path="/data/:anomaly_type" element={<AnomalyData />} />
                        <Route element={<AdminRoute />}>
                            <Route path="/admin/settings" element={<AdminSettings />} />
                        </Route>
                    </Route>
                </Route>
                </Routes>
            </BrowserRouter>
        </AuthProvider>
    );
}

export default App;
