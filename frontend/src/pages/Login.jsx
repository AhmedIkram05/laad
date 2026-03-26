/* Import Styles */
import './Login.css'


function Login() {
  return (

    <div className="page">

      <div className="loginBox">
        <h1>Log In</h1>
        
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
        <div className="buttonContainer">
            <button className="loginButton" onClick={() => navigate("/dashboard")}>Login</button>
        </div>

      </div>
    </div>

  );
}


export default Login;