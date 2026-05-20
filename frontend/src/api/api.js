/*
 * API Helper
 * --------------------
 * Connects to backend API and attaches authentication headers.
 */

// Generates Authorisation Headers Using JWT
export const getAuthHeaders = () => {
    const token = localStorage.getItem("jwt");
    return token ? { Authorization: `Bearer ${token}` } : {};
};

// Helper Function for Making API Requests
const request = async (endpoint, options = {}) => {
    const { headers: optionHeaders, ...restOptions } = options;
    const res = await fetch(endpoint, {
        headers: {
            ...getAuthHeaders(),
            ...(optionHeaders || {}),
        },
        ...restOptions,
    });

    if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`);
    }

    return res.json();
};

// Fetches a list of anomalies filtered by Completed state
// is_active: 1 = active only, 0 = resolved only, undefined/null = all
// hours: time range filter (default 24 hours)
// sort_by: 'score' (default, criticality), 'detected_at' (most recent), 'severity'
// detection_source: 'CLASSIFIER', 'ZSCORE', 'SIGNAL_CORRELATOR'
// atm_id: filter by specific ATM ID
// anomaly_type: filter by anomaly type (A1-A7, UNKNOWN)
// severity: filter by severity (CRITICAL, HIGH, MAJOR, LOW)
export const fetchAnomalies = (is_active = 1, hours = 24, sort_by = 'score', detection_source = null, is_starred = null, atm_id = null, anomaly_type = null, severity = null) => {
    const now = new Date();
    const from = new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString();
    let params = `from_date=${encodeURIComponent(from)}&sort_by=${sort_by}`;
    if (is_active !== null && is_active !== undefined) {
        params += `&is_active=${is_active}`;
    }
    if (detection_source) {
        params += `&detection_source=${encodeURIComponent(detection_source)}`;
    }
    if (is_starred !== null && is_starred !== undefined) {
        params += `&is_starred=${is_starred}`;
    }
    if (atm_id) {
        params += `&atm_id=${encodeURIComponent(atm_id)}`;
    }
    if (anomaly_type) {
        params += `&anomaly_type=${encodeURIComponent(anomaly_type)}`;
    }
    if (severity) {
        params += `&severity=${encodeURIComponent(severity)}`;
    }
    return request(`/api/anomalies?${params}`);
};

// Fetches analysis data for a specific anomaly
export const fetchDetailedAnalysis = (anomaly_type) =>
    request(`/api/analysis/detailed?Anomaly=${anomaly_type}`);

// Toggles the "Starred" state of an anomaly
export const toggleStar = (id) =>
    request(`/api/anomalies/${id}/star`, {method: "PATCH",});

// Toggles the "Completed" state of an anomaly
export const toggleComplete = (id) =>
    request(`/api/anomalies/${id}/resolve`, {method: "PATCH",});

// Fetches anomaly metrics for dashboard analytics
export const fetchMetrics = (hours = 24, bucket_minutes = 60) =>
    request(`/api/analysis/metrics?hours=${hours}&bucket_minutes=${bucket_minutes}`);

// RAG Diagnostic Assistant API
export const queryRAG = (query, atm_id = null, top_k = 3, include_uncertainty = true) =>
    request("/api/rag/query", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query, atm_id, top_k, include_uncertainty}),
    });

export const submitRAGFeedback = (query_id, feedback) =>
    request("/api/rag/feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query_id, feedback}),
    });

export const getRAGHistory = (limit = 20, offset = 0) =>
    request(`/api/rag/history?limit=${limit}&offset=${offset}`);

export const getRAGStats = () => request("/api/rag/stats");