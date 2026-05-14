/*
 * API Helper
 * --------------------
 * Connects to backend API and attaches authentication headers.
 */

// Generates Authorisation Headers Using JWT
export const getAuthHeaders = () => ({
    Authorization: `Bearer ${localStorage.getItem("jwt")}`,
});

// Helper Function for Making API Requests
const request = async (endpoint, options = {}) => {
    const res = await fetch(endpoint, {
        headers: {
            ...getAuthHeaders(),
            ...(options.headers || {}),
        },
        ...options,
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