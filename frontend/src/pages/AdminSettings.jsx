import { useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import "./Login.css";
import "./AdminSettings.css";

const API_BASE_URL = "http://localhost:8000";

function AdminSettings() {
    const [tokenInfo, setTokenInfo] = useState(null);
    const [genError, setGenError] = useState("");
    const [creating, setCreating] = useState(false);

    const [cUsername, setCUsername] = useState("");
    const [cPassword, setCPassword] = useState("");
    const [cRole, setCRole] = useState("user");
    const [createMsg, setCreateMsg] = useState("");
    const [createErr, setCreateErr] = useState("");
    const { token: jwt } = useAuth();

    const handleGenerate = async () => {
        setGenError("");
        setTokenInfo(null);

        try {
            const res = await fetch(`${API_BASE_URL}/auth/otp/generate`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${jwt}`,
                },
                body: JSON.stringify({ role: "user" }),
            });
            const data = await res.json();
            if (!res.ok) {
                setGenError(data.detail ?? "Failed to generate token");
                return;
            }
            setTokenInfo(data);
        } catch (err) {
            setGenError("Could not reach server");
        }
    };

    const handleCreate = async () => {
        setCreateErr("");
        setCreateMsg("");

        if (!cUsername || !cPassword) {
            setCreateErr("username and password required");
            return;
        }
        setCreating(true);

        try {
            const res = await fetch(`${API_BASE_URL}/admin/users`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${jwt}`,
                },
                body: JSON.stringify({ username: cUsername, password: cPassword, role: cRole }),
            });
            const data = await res.json();
            if (!res.ok) {
                setCreateErr(data.detail ?? data.message ?? "Create failed");
                return;
            }
            setCreateMsg(`Created user ${data.username} (${data.role})`);
            setCUsername("");
            setCPassword("");
        } catch (err) {
            setCreateErr("Could not reach server");
        } finally {
            setCreating(false);
        }
    };

    return (
        <div className="mainContainer">
            <div className="titleContainer">
                <h1>Admin Settings</h1>
            </div>

            <div className="panelBox">
                <div className="panelGrid">

                    <section className="panelSection">
                        <h3>Generate Guest Invite</h3>
                        <label>Invite type:</label>
                        <div className="adminNote">Guest access (user only)</div>

                        <div className="mt12">
                            <button className="loginButton" onClick={handleGenerate}>Generate Invite</button>
                        </div>

                        {genError && <p className="loginError">{genError}</p>}

                        {tokenInfo && (
                            <div className="mt12 tokenBlock">
                                <p>Token: <strong>{tokenInfo.token}</strong></p>

                                <div className="tokenRow">
                                    <div className="tokenInner">
                                        <label className="tokenLabel">Guest access link (no account required):</label>

                                        <div className="tokenRowInner">
                                            {tokenInfo.token ? (<>
                                                    <input readOnly value={`${window.location.origin}/dashboard?token=${tokenInfo.token}`} className="tokenInput"/>

                                                    <button className="loginButton" onClick={() => navigator.clipboard.writeText(`${window.location.origin}/dashboard?token=${tokenInfo.token}`)}> Copy </button></>):
                                                    (<input readOnly value={tokenInfo.link} className="tokenInput" />)}
                                        </div>
                                        <div className="muted">
                                            Recipients clicking this link will be logged in as a temporary guest user, with user permissions not admin, for 24 hours. No account creation required.
                                        </div>
                                    </div>
                                </div>

                                <p className="mt8">Expires: {tokenInfo.expires_at}</p>
                            </div>
                        )}
                    </section>

                    <section className="panelSection">
                        <h3>Create Persistent User</h3>
                        {createErr && <p className="loginError">{createErr}</p>}
                        {createMsg && <p className="loginSuccess">{createMsg}</p>}

                        <label>Username:</label>
                        <input className="loginInput" value={cUsername} onChange={(e) => setCUsername(e.target.value)} />

                        <label>Password:</label>
                        <input type="password" className="loginInput" value={cPassword} onChange={(e) => setCPassword(e.target.value)} />

                        <label>Role:</label>
                        <select value={cRole} onChange={(e) => setCRole(e.target.value)} className="loginInput">
                            <option value="user">user</option>
                            <option value="admin">admin</option>
                        </select>

                        <div className="mt12">
                            <button className="loginButton" onClick={handleCreate} disabled={creating}>Create</button>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
export default AdminSettings;
