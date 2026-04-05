/*
 * AdminSettings Page
 * --------------------
 * Configures settings only accessible by admin users.
 */

/* External Libraries */
import { useState, useEffect } from "react";

/* Internal Imports */
import { useAuth } from "../auth/AuthProvider";
import BackButton from "../components/BackButton";
import "./Login.css";
import "./AdminSettings.css";

const API_BASE_URL = "http://localhost:8000";

function AdminSettings() {
    const [creating, setCreating] = useState(false);

    const [cUsername, setCUsername] = useState("");
    const [cPassword, setCPassword] = useState("");
    const [cPasswordConfirm, setCPasswordConfirm] = useState("");
    const [cRole, setCRole] = useState("user");
    const [createMsg, setCreateMsg] = useState("");
    const [createErr, setCreateErr] = useState("");
    const { token: jwt } = useAuth();

    // Global retention (days) — backend supports 1,7,30,60,90,365
    const RETENTION_OPTIONS = [1, 7, 30, 60, 90, 365];
    const [retentionDays, setRetentionDays] = useState(7);
    const [retentionUpdatedAt, setRetentionUpdatedAt] = useState(null);
    const [retentionLoading, setRetentionLoading] = useState(true);
    const [retentionErr, setRetentionErr] = useState("");
    const [savingRetention, setSavingRetention] = useState(false);

    const [cleanupRunning, setCleanupRunning] = useState(false);
    const [cleanupResult, setCleanupResult] = useState(null);
    const [cleanupErr, setCleanupErr] = useState("");

    useEffect(() => {
        loadRetention();
    }, []);

    const loadRetention = async () => {
        setRetentionLoading(true);
        setRetentionErr("");
        try {
            const res = await fetch(`${API_BASE_URL}/admin/retention`, {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${jwt}`,
                },
            });
            const data = await res.json();
            if (!res.ok) {
                setRetentionErr(data.detail ?? "Failed to load retention");
                return;
            }
            setRetentionDays(data.retention_days);
            setRetentionUpdatedAt(data.updated_at);
        } catch (err) {
            setRetentionErr("Could not reach server");
        } finally {
            setRetentionLoading(false);
        }
    };

    const saveRetention = async () => {
        setRetentionErr("");
        setSavingRetention(true);
        try {
            if (!RETENTION_OPTIONS.includes(retentionDays)) {
                setRetentionErr(`Allowed values: ${RETENTION_OPTIONS.join(", ")}`);
                return;
            }
            const res = await fetch(`${API_BASE_URL}/admin/retention`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${jwt}`,
                },
                body: JSON.stringify({ days: retentionDays }),
            });
            const data = await res.json();
            if (!res.ok) {
                setRetentionErr(data.detail ?? "Failed to update retention");
                return;
            }
            await loadRetention();
        } catch (err) {
            setRetentionErr("Could not reach server");
        } finally {
            setSavingRetention(false);
        }
    };

    const runCleanup = async () => {
        setCleanupErr("");
        setCleanupResult(null);
        setCleanupRunning(true);
        try {
            const res = await fetch(`${API_BASE_URL}/admin/cleanup/wipe`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${jwt}`,
                },
            });
            const data = await res.json();
            if (!res.ok) {
                setCleanupErr(data.detail ?? "Full Delete failed");
                return;
            }
            setCleanupResult(data);
        } catch (err) {
            setCleanupErr("Could not reach server");
        } finally {
            setCleanupRunning(false);
        }
    };

    // Format ISO timestamp into `YYYY-MM-DD HH:MM:SS` (local time)
    const formatTimestamp = (iso) => {
        if (!iso) return "";
        try {
            const d = new Date(iso);
            const pad = (n) => String(n).padStart(2, "0");
            const year = d.getFullYear();
            const month = pad(d.getMonth() + 1);
            const day = pad(d.getDate());
            const hours = pad(d.getHours());
            const minutes = pad(d.getMinutes());
            const seconds = pad(d.getSeconds());
            return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
        } catch (e) {
            return iso;
        }
    };

    const handleCreate = async () => {
        setCreateErr("");
        setCreateMsg("");

        if (!cUsername || !cPassword) {
            setCreateErr("username and password required");
            return;
        }
        if (!cPasswordConfirm) {
            setCreateErr("confirm password required");
            return;
        }
        if (cPassword !== cPasswordConfirm) {
            setCreateErr("passwords do not match");
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
                body: JSON.stringify({ username: cUsername, password: cPassword, confirm_password: cPasswordConfirm, role: cRole }),});
            const data = await res.json();
            if (!res.ok) {
                setCreateErr(data.detail ?? data.message ?? "Create failed");
                return;}
            setCreateMsg(`Created user ${data.username} (${data.role})`);
            setCUsername("");
            setCPassword("");
            setCPasswordConfirm("");
        } catch (err) {
            setCreateErr("Could not reach server");
        } finally {
            setCreating(false);
        }
    };

    const deleted = cleanupResult && cleanupResult.deleted ? cleanupResult.deleted : null;

    return (
        <div className="mainContainer">
            <div className="settingsTitleContainer">
                <BackButton />
                <h1>Admin Settings</h1>
            </div>
            <div className="panelBox">
                <div className="panelGrid">
                    <section className="panelSection">
                        <h3>Data Retention</h3>
                        {retentionErr && <p className="loginError">{retentionErr}</p>}

                        <label>Retention period:</label>
                        <select value={retentionDays} onChange={(e) => setRetentionDays(parseInt(e.target.value, 10))} className="loginInput">
                            {RETENTION_OPTIONS.map(opt => (
                                <option key={opt} value={opt}>{opt === 1 ? '1 day' : `${opt} days`}</option>))}
                        </select>

                        <div className="buttonRow mt12">
                            <button className="loginButton--secondary" onClick={saveRetention} disabled={savingRetention}>Save</button>
                            <button className="loginButton--primary dangerButton" onClick={runCleanup} disabled={cleanupRunning}>Delete All Now</button>
                        </div>

                        {retentionUpdatedAt && <p className="muted">Last updated: {formatTimestamp(retentionUpdatedAt)}</p>}
                        {cleanupErr && <p className="loginError">{cleanupErr}</p>}
                        {cleanupResult && (
                            <div className="mt8 tokenBlock">
                                {cleanupResult.action === 'wipe' ? (
                                    <div className="muted">Full Delete complete.</div>):(
                                    <div className="muted">Cleanup complete. Cutoff: {formatTimestamp(cleanupResult.cutoff)} — Retention: {cleanupResult.retention_days}d</div>)}
                                <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{JSON.stringify(deleted, null, 2)}</pre>
                            </div>)}
                    </section>

                    <section className="panelSection">
                        <h3>Create New User</h3>
                        {createErr && <p className="loginError">{createErr}</p>}
                        {createMsg && <p className="loginSuccess">{createMsg}</p>}

                        <label>Username:</label>
                        <input className="loginInput" value={cUsername} onChange={(e) => setCUsername(e.target.value)} />

                        <label>Password:</label>
                        <input type="password" className="loginInput" value={cPassword} onChange={(e) => setCPassword(e.target.value)} />

                        <label>Confirm Password:</label>
                        <input type="password" className="loginInput" value={cPasswordConfirm} onChange={(e) => setCPasswordConfirm(e.target.value)} />

                        <label>Role:</label>
                        <select value={cRole} onChange={(e) => setCRole(e.target.value)} className="loginInput">
                            <option value="user">user</option>
                            <option value="admin">admin</option>
                        </select>
                        <div className="mt12">
                            <button className="loginButton--secondary" onClick={handleCreate} disabled={creating}>Create</button>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
export default AdminSettings;