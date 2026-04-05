/*
 * API Helper
 * --------------------
 * Connects to backend API and attaches authentication headers.
 */

// Generates Authorisation Headers Using JWT
const getAuthHeaders = () => ({
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
export const fetchAnomalies = (is_active = 1) =>
    request(`/api/anomalies?is_active=${is_active}`);

// Fetches analysis data for a specific anomaly
export const fetchDetailedAnalysis = (anomaly_type) =>
    request(`/api/analysis/detailed?Anomaly=${anomaly_type}`);

// Toggles the "Starred" state of an anomaly
export const toggleStar = (id) =>
    request(`/api/anomalies/${id}/star`, {method: "PATCH",});

// Toggles the "Completed" state of an anomaly
export const toggleComplete = (id) =>
    request(`/api/anomalies/${id}/resolve`, {method: "PATCH",});