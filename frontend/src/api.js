const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
const TIMEOUT_MS = 15000;

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...options, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (err) {
    if (err.name === "TimeoutError") throw new Error(`The backend did not respond within ${TIMEOUT_MS / 1000}s`, { cause: err });
    throw new Error(`Could not connect to the backend (${BASE_URL})`, { cause: err });
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // body was not JSON: keep statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export function listRuns(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/agent/runs${query}`);
}

export function getRun(id) {
  return request(`/agent/runs/${id}`);
}

export function approveRun(id) {
  return request(`/agent/runs/${id}/approve`, { method: "POST" });
}

export function rejectRun(id, reason) {
  return request(`/agent/runs/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
}
