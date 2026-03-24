/* import libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

/* import pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";

function App() {
  return (

    <BrowserRouter>
      <Routes>

        {/* default redirect from root to dashboard page */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* set main layout (side navbar) to pages */}
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
        </Route>

      </Routes>
    </BrowserRouter>

  );
}


export default App;