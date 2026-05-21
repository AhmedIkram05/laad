import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../auth/useAuth";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { Trash2, Save, UserPlus, RefreshCw, AlertCircle, Eye, ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";
import { formatUKDateTime } from "../lib/utils";

const RETENTION_OPTIONS = [1, 7, 30, 60, 90, 365];

function AdminSettings() {
  const { token: jwt } = useAuth();
  const [retentionDays, setRetentionDays] = useState(7);
  const [retentionUpdatedAt, setRetentionUpdatedAt] = useState(null);
  const [savingRetention, setSavingRetention] = useState(false);

  const [cleanupRunning, setCleanupRunning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState(null);
  const [retentionCleanupRunning, setRetentionCleanupRunning] = useState(false);
  const [retentionCleanupResult, setRetentionCleanupResult] = useState(null);

  const [cUsername, setCUsername] = useState("");
  const [cPassword, setCPassword] = useState("");
  const [cPasswordConfirm, setCPasswordConfirm] = useState("");
  const [cRole, setCRole] = useState("user");
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState("");

  const [ingestionErrors, setIngestionErrors] = useState([]);
  const [ingestionTotal, setIngestionTotal] = useState(0);
  const [ingestionPage, setIngestionPage] = useState(1);
  const [ingestionLoading, setIngestionLoading] = useState(true);
  const [expandedError, setExpandedError] = useState(null);

  const INGESTION_PER_PAGE = 10;

  useEffect(() => {
    let cancelled = false;
    async function loadRetention() {
      try {
        const res = await fetch("/api/admin/retention", { headers: { Authorization: `Bearer ${jwt}` }});
        const data = await res.json();
        if (!cancelled && res.ok) {
          setRetentionDays(data.retention_days);
          setRetentionUpdatedAt(data.updated_at);
        }
      } catch {
        if (!cancelled) console.error("Failed to load retention");
      }
    }
    async function loadErrors() {
      try {
        const res = await fetch(`/api/admin/ingestion-errors?limit=${INGESTION_PER_PAGE}&offset=0`, {
          headers: { Authorization: `Bearer ${jwt}` },
        });
        const data = await res.json();
        if (!cancelled && res.ok) {
          setIngestionErrors(data.data || []);
          setIngestionTotal(data.total || 0);
          setIngestionPage(1);
        }
      } catch {
        if (!cancelled) console.error("Failed to load ingestion errors");
      } finally {
        if (!cancelled) setIngestionLoading(false);
      }
    }
    loadRetention();
    loadErrors();
    return () => { cancelled = true; };
  }, [jwt]);

  const loadRetention = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/retention", { headers: { Authorization: `Bearer ${jwt}` }});
      const data = await res.json();
      if (res.ok) {
        setRetentionDays(data.retention_days);
        setRetentionUpdatedAt(data.updated_at);
      }
    } catch {
      console.error("Failed to load retention");
    }
  }, [jwt]);

  const loadIngestionErrors = async (page) => {
    setIngestionLoading(true);
    const offset = (page - 1) * INGESTION_PER_PAGE;
    try {
      const res = await fetch(`/api/admin/ingestion-errors?limit=${INGESTION_PER_PAGE}&offset=${offset}`, {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      const data = await res.json();
      if (res.ok) {
        setIngestionErrors(data.data || []);
        setIngestionTotal(data.total || 0);
        setIngestionPage(page);
      }
    } catch {
      console.error("Failed to load ingestion errors");
    } finally {
      setIngestionLoading(false);
    }
  };

  const clearIngestionErrors = async () => {
    if (!confirm("Delete all ingestion error records?")) return;
    try {
      const res = await fetch("/api/admin/ingestion-errors", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(`Cleared ${data.deleted} ingestion errors`);
        loadIngestionErrors(1);
      } else {
        toast.error(data.detail || "Failed to clear errors");
      }
    } catch {
      toast.error("Could not reach server");
    }
  };

  const saveRetention = async () => {
    setSavingRetention(true);
    try {
      const res = await fetch("/api/admin/retention", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
        body: JSON.stringify({ days: retentionDays }),
      });
      if (res.ok) {
        toast.success("Retention settings saved");
        await loadRetention();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to save retention");
      }
    } catch {
      toast.error("Could not reach server");
    } finally {
      setSavingRetention(false);
    }
  };

  const runRetentionCleanup = async () => {
    if (!confirm(`Delete all data older than ${retentionDays} days?`)) return;
    setRetentionCleanupRunning(true);
    setRetentionCleanupResult(null);
    try {
      const res = await fetch("/api/admin/cleanup/run", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      const data = await res.json();
      if (res.ok) {
        setRetentionCleanupResult(data);
        toast.success(`Retention cleanup complete: ${Object.values(data.deleted || {}).reduce((a, b) => a + b, 0)} rows deleted`);
      } else {
        toast.error(data.detail || "Cleanup failed");
      }
    } catch {
      toast.error("Could not reach server");
    } finally {
      setRetentionCleanupRunning(false);
    }
  };

  const runWipe = async () => {
    if (!confirm("Are you sure you want to delete ALL data? This cannot be undone.")) return;
    setCleanupRunning(true);
    setCleanupResult(null);
    try {
      const res = await fetch("/api/admin/cleanup/wipe", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      const data = await res.json();
      if (res.ok) {
        setCleanupResult(data);
        toast.success("Data wipe complete");
        loadIngestionErrors(1);
      } else {
        toast.error(data.detail || "Wipe failed");
      }
    } catch {
      toast.error("Could not reach server");
    } finally {
      setCleanupRunning(false);
    }
  };

  const handleCreate = async () => {
    if (!cUsername || !cPassword) {
      toast.error("Username and password required");
      return;
    }
    if (cPassword !== cPasswordConfirm) {
      toast.error("Passwords do not match");
      return;
    }
    setCreating(true);
    try {
      const res = await fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
        body: JSON.stringify({ username: cUsername, password: cPassword, confirm_password: cPasswordConfirm, role: cRole }),
      });
      const data = await res.json();
      if (res.ok) {
        setCreateMsg(`Created user ${data.username} (${data.role})`);
        setCUsername("");
        setCPassword("");
        setCPasswordConfirm("");
        toast.success("User created successfully");
      } else {
        toast.error(data.detail || "Create failed");
      }
    } catch {
      toast.error("Could not reach server");
    } finally {
      setCreating(false);
    }
  };

  const ingestionTotalPages = Math.ceil(ingestionTotal / INGESTION_PER_PAGE);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">Admin Settings</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Data Retention</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Retention period</Label>
              <Select value={retentionDays} onValueChange={(v) => setRetentionDays(parseInt(v))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RETENTION_OPTIONS.map(opt => (
                    <SelectItem key={opt} value={opt}>{opt === 1 ? '1 day' : `${opt} days`}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2">
              <Button onClick={saveRetention} disabled={savingRetention} className="gap-2">
                <Save className="w-4 h-4" /> Save
              </Button>
              <Button onClick={runRetentionCleanup} disabled={retentionCleanupRunning} variant="outline" className="gap-2">
                <RefreshCw className={`w-4 h-4 ${retentionCleanupRunning ? "animate-spin" : ""}`} /> Run Cleanup
              </Button>
              <Button variant="destructive" onClick={runWipe} disabled={cleanupRunning} className="gap-2">
                <Trash2 className="w-4 h-4" /> Wipe All
              </Button>
            </div>

            {retentionUpdatedAt && (
              <p className="text-sm text-muted-foreground">Last updated: {formatUKDateTime(retentionUpdatedAt)}</p>
            )}

            {retentionCleanupResult && (
              <div className="p-3 bg-secondary rounded-md">
                <p className="text-sm font-medium">Retention cleanup complete</p>
                <p className="text-xs text-muted-foreground">Cutoff: {formatUKDateTime(retentionCleanupResult.cutoff)}</p>
                {retentionCleanupResult.deleted && (
                  <pre className="text-xs mt-2">{JSON.stringify(retentionCleanupResult.deleted, null, 2)}</pre>
                )}
              </div>
            )}

            {cleanupResult && (
              <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-md">
                <p className="text-sm font-medium text-destructive">Full wipe complete</p>
                {cleanupResult.deleted && (
                  <pre className="text-xs mt-2">{JSON.stringify(cleanupResult.deleted, null, 2)}</pre>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Create New User</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {createMsg && <p className="text-sm text-emerald-600">{createMsg}</p>}

            <div className="space-y-2">
              <Label>Username</Label>
              <Input value={cUsername} onChange={(e) => setCUsername(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Password</Label>
              <Input type="password" value={cPassword} onChange={(e) => setCPassword(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Confirm Password</Label>
              <Input type="password" value={cPasswordConfirm} onChange={(e) => setCPasswordConfirm(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={cRole} onValueChange={setCRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleCreate} disabled={creating} className="gap-2">
              <UserPlus className="w-4 h-4" /> Create User
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Ingestion Errors</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">{ingestionTotal} total errors</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => loadIngestionErrors(ingestionPage)} className="gap-2">
              <RefreshCw className="w-4 h-4" /> Refresh
            </Button>
            {ingestionTotal > 0 && (
              <Button variant="destructive" size="sm" onClick={clearIngestionErrors} className="gap-2">
                <Trash2 className="w-4 h-4" /> Clear All
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {ingestionLoading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Loading...</p>
          ) : ingestionErrors.length === 0 ? (
            <div className="text-center py-8">
              <AlertCircle className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
              <p className="text-muted-foreground">No ingestion errors found.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {ingestionErrors.map((err) => (
                <div key={err.id} className="border border-border rounded-md overflow-hidden">
                  <button
                    onClick={() => setExpandedError(expandedError === err.id ? null : err.id)}
                    className="w-full flex items-center justify-between p-3 text-left hover:bg-secondary/50 transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <Badge variant="secondary" className="shrink-0">{err.source || "unknown"}</Badge>
                      <span className="text-sm font-mono truncate flex-1">{err.error_detail}</span>
                    </div>
                    <div className="flex items-center gap-3 ml-3 shrink-0">
                      <span className="text-xs text-muted-foreground">{formatUKDateTime(err.timestamp)}</span>
                      {expandedError === err.id ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                    </div>
                  </button>
                  {expandedError === err.id && (
                    <div className="px-3 pb-3 border-t border-border">
                      <div className="mt-3 space-y-2">
                        <div>
                          <span className="text-xs text-muted-foreground">Error Detail:</span>
                          <pre className="text-xs mt-1 p-2 bg-secondary rounded-md overflow-x-auto whitespace-pre-wrap">{err.error_detail}</pre>
                        </div>
                        {err.raw_input && (
                          <div>
                            <span className="text-xs text-muted-foreground">Raw Input:</span>
                            <pre className="text-xs mt-1 p-2 bg-secondary rounded-md overflow-x-auto whitespace-pre-wrap">{typeof err.raw_input === "string" ? err.raw_input : JSON.stringify(err.raw_input, null, 2)}</pre>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {ingestionTotalPages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              <button onClick={() => loadIngestionErrors(1)} disabled={ingestionPage === 1} className="px-3 py-1.5 border rounded text-sm disabled:opacity-50">First</button>
              <button onClick={() => loadIngestionErrors(ingestionPage - 1)} disabled={ingestionPage === 1} className="px-3 py-1.5 border rounded text-sm disabled:opacity-50">Prev</button>
              <span className="px-3 py-1.5 text-sm">Page {ingestionPage} of {ingestionTotalPages}</span>
              <button onClick={() => loadIngestionErrors(ingestionPage + 1)} disabled={ingestionPage === ingestionTotalPages} className="px-3 py-1.5 border rounded text-sm disabled:opacity-50">Next</button>
              <button onClick={() => loadIngestionErrors(ingestionTotalPages)} disabled={ingestionPage === ingestionTotalPages} className="px-3 py-1.5 border rounded text-sm disabled:opacity-50">Last</button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default AdminSettings;
