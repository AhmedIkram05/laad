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
export const fetchAnomalies = (is_active = 1, hours = 24) => {
    const now = new Date();
    const from = new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString();
    if (is_active === null || is_active === undefined) {
        return request(`/anomalies?from_date=${encodeURIComponent(from)}`);
    }
    return request(`/anomalies?is_active=${is_active}&from_date=${encodeURIComponent(from)}`);
};

// Fetches analysis data for a specific anomaly
export const fetchDetailedAnalysis = (anomaly_type) =>
    request(`/analysis/detailed?Anomaly=${anomaly_type}`);

// Toggles the "Starred" state of an anomaly
export const toggleStar = (id) =>
    request(`/anomalies/${id}/star`, {method: "PATCH",});

// Toggles the "Completed" state of an anomaly
export const toggleComplete = (id) =>
    request(`/anomalies/${id}/resolve`, {method: "PATCH",});

// Fetches anomaly metrics for dashboard analytics
export const fetchMetrics = (hours = 24, bucket_minutes = 60) =>
    request(`/analysis/metrics?hours=${hours}&bucket_minutes=${bucket_minutes}`);

// RAG Diagnostic Assistant API
export const queryRAG = (query, atm_id = null, top_k = 5, include_uncertainty = true) =>
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