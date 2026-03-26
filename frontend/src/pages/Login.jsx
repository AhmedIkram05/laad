/* Import Libraries */
import { useNavigate } from "react-router-dom";

/* Import Styles */
import './Login.css'


function Login() {
    const navigate = useNavigate();
    
  return (

    <div className="loginPage">

      <div className="loginBox">
        <div className="loginTitle">
          <h1>Log In</h1>
        </div>
        
        {/* Username */}
        <label htmlFor="username">Username:</label>
        <input
          type="text"
          id="username"
          name="username"
          className="loginInput"
        />

        {/* Password */}
        <label htmlFor="password">Password:</label>
        <input
          type="password"
          id="password"
          name="password"
          className="loginInput"
        />

        {/* Login Button */}
        <div className="loginButtonContainer">
            <button className="loginButton" onClick={() => navigate("/dashboard")}>Login</button>
        </div>

      </div>
    </div>

  );
}


export default Login;