/* Import Libraries */
import { Outlet } from "react-router-dom";

/* Import Components */
import SideNavbar from "../components/SideNavbar";

/* Import Styles */
import './MainLayout.css'


function MainLayout() {
  return (

    <div className="container">
      {/* Side Navbar */}
      <SideNavbar/>

      {/* Page content */}
      <div className="page">
        <Outlet/>
      </div>
    </div>

  );
}


export default MainLayout;