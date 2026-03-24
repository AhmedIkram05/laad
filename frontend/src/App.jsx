/* Import Libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

/* Import Pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";


function App() {
  return (

    <BrowserRouter>
      <Routes>

        {/* Redirect Root to Dashboard */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* Set Main Layout to Pages */}
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
        </Route>

      </Routes>
    </BrowserRouter>

  );
}


export default App;