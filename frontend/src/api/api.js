const getAuthHeaders = () => ({
    Authorization: `Bearer ${localStorage.getItem("jwt")}`,
});

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

export const fetchAnomalies = (is_active = 1) =>
    request(`/api/anomalies?is_active=${is_active}`);

export const fetchDetailedAnalysis = (anomaly_type) =>
    request(`/api/analysis/detailed?Anomaly=${anomaly_type}`);

export const toggleStar = (id) =>
    request(`/api/anomalies/${id}/star`, {
        method: "PATCH",
    });

export const fetchAnomalyDetail = (id) =>
    request(`/api/anomalies/${id}`);

export const fetchATM = (atmId) =>
    request(`/api/atms/${atmId}`);

export const fetchTimeline = (atmId, from, to, offset = 0) =>
    request(`/api/timeline?atm_id=${atmId}&from_date=${from}&to_date=${to}&limit=10&offset=${offset}`);

export const resolveAnomaly = (id) =>
    request(`/api/anomalies/${id}/resolve`, {
        method: "PATCH",
    });
