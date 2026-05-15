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
export const fetchAnomalies = (is_active = 1) => {
    if (is_active === null || is_active === undefined) {
        return request("/api/anomalies");
    }
    return request(`/api/anomalies?is_active=${is_active}`);
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
export const queryRAG = (query, atm_id = null, top_k = 5, include_uncertainty = true) => {
    const params = new URLSearchParams({
        query,
        top_k,
        include_uncertainty,
    });
    if (atm_id) params.append("atm_id", atm_id);
    return request(`/api/rag/query?${params}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query, atm_id, top_k, include_uncertainty}),
    });
};

export const submitRAGFeedback = (query_id, feedback) =>
    request("/api/rag/feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query_id, feedback}),
    });

export const getRAGHistory = (limit = 20, offset = 0) =>
    request(`/api/rag/history?limit=${limit}&offset=${offset}`);

export const getRAGStats = () => request("/api/rag/stats");

export const recalibrateRAG = () => request("/api/rag/recalibrate", {method: "POST"});