/* import libraries */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

/* import pages */
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import Starred from "./pages/Starred";
import Completed from "./pages/Completed";
import AnomalyDetails from "./pages/AnomalyDetails";


function App() {
  return (

    <BrowserRouter>
      <Routes>

        <Route element={<MainLayout/>}>
          {/* default opening to dashboard page */}
          <Route path="/" element={<Navigate to="/dashboard"/>}/> 

          {/* set main layout to all pages */}
          <Route path="/dashboard" element={<Dashboard/>}/>
          <Route path="/starred" element={<Starred/>}/>
          <Route path="/completed" element={<Completed/>}/>
          <Route path="/anomaly/:id" element={<AnomalyDetails/>}/>
        </Route>

      </Routes>
    </BrowserRouter>
    
  );
}


export default App;