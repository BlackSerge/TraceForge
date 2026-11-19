const BASE_URL = "http://127.0.0.1:8000";

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, options);
  } catch {
    throw new Error(`Could not connect to the backend (${BASE_URL})`);
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
