// Shared API client for the four backends behind the Vite proxy.
//
// Every call goes through a relative path so the proxy in vite.config.js routes
// it to the owning service. Nothing here hardcodes a port -- that mapping lives
// in one place, the proxy config.

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    // fetch() rejects only on network-level failure: the service is down, or the
    // proxy could not reach it. Surface that as itself rather than as a bare
    // "Failed to fetch", which reads like a bug in the page.
    throw new Error(`Cannot reach the service for ${path}. Is it running?`);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${res.status} from ${path}`);
  }
  return res.json();
}

const postJson = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// --- Part 1 + Part 4 (:8002) ---------------------------------------------
export const listClients = () => request("/api/v1/clients");
export const investigate = (clientId) =>
  request(`/api/v1/investigate/${clientId}`, { method: "POST" });

export async function login(username, password) {
  // The token endpoint is OAuth2 password flow: form-encoded, not JSON.
  const form = new URLSearchParams({ username, password });
  const res = await fetch("/api/v1/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  }).catch(() => {
    throw new Error("Cannot reach the identity service. Is it running?");
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Login failed (HTTP ${res.status})`);
  }
  return res.json();
}

export const whoAmI = (token) =>
  request("/api/v1/security/me", { headers: { Authorization: `Bearer ${token}` } });

// --- Part 2 (:8004) -------------------------------------------------------
export const screen = (query) => postJson("/screen", query);
export const listArticles = () => request("/adverse-media/articles");
export const analyzeArticle = (entityId, articleName) =>
  postJson("/adverse-media/analyze", { entity_id: entityId, article_name: articleName });
export const listUboStructures = () => request("/ubo/structures");
export const traceUbo = (body) => postJson("/ubo/trace", body);
export const auditEvents = (limit = 25) => request(`/audit/events?limit=${limit}`);
export const auditVerify = () => request("/audit/verify");

// --- Part 3 + Part 5 (:8003) ---------------------------------------------
export const governanceSummary = () => request("/governance/summary");
export const listCases = (role = "compliance") => request(`/governance/cases?role=${role}`);
export const caseDetail = (id, role = "compliance") =>
  request(`/governance/cases/${id}?role=${role}`);
export const submitReview = (id, body) => postJson(`/governance/cases/${id}/review`, body);
export const sarSignoff = (id, body) => postJson(`/governance/cases/${id}/sar-signoff`, body);
export const governanceAudit = () => request("/governance/audit");
export const governanceAuditVerify = () => request("/governance/audit/verify");

// --- Health ---------------------------------------------------------------
// Each service is probed independently: one being down must not blank the strip.
export async function probeHealth(path) {
  try {
    const res = await fetch(path);
    return res.ok ? "up" : "error";
  } catch {
    return "down";
  }
}
