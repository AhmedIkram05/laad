/* Import Libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

/* Import Pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import Starred from "./pages/Starred";
import Completed from "./pages/Completed";
import AnomalyData from "./pages/AnomalyData";
import Login from "./pages/Login";
import ProtectedRoute from "./components/ProtectedRoute";

function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Login Pathway */}
                <Route path="/login" element={<Login />} />

                {/* Redirect Root to Dashboard */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />

                {/* Set Main Layout to Pages */}
                <Route element={<ProtectedRoute />}>
                    <Route element={<MainLayout />}>
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/starred" element={<Starred />} />
                        <Route path="/completed" element={<Completed />} />
                        <Route path="/data/:anomaly_type" element={<AnomalyData />} />
                    </Route>
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

export default App;
