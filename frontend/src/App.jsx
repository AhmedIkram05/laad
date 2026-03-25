/* Import Libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

/* Import Pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import Starred from "./pages/Starred";
import Completed from "./pages/Completed";
import AnomalyData from "./pages/AnomalyData";
import Settings from "./pages/Settings";


function App() {
  return (

    <BrowserRouter>
      <Routes>

        {/* Redirect Root to Dashboard */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* Set Main Layout to Pages */}
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/starred" element={<Starred />} />
          <Route path="/completed" element={<Completed />} />
          <Route path="/data" element={<AnomalyData />} />
          <Route path="/settings" element={<Settings />} />
        </Route>

      </Routes>
    </BrowserRouter>

  );
}


export default App;