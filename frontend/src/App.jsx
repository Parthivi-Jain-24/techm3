import { useEffect, useMemo, useState } from "react";
import "./App.css";

import {
  analyzeArticle,
  auditVerify,
  caseDetail,
  governanceAuditVerify,
  governanceSummary,
  investigate,
  listArticles,
  listClients,
  listUboStructures,
  login as requestLogin,
  probeHealth,
  sarSignoff,
  screen,
  submitReview,
  traceUbo,
  whoAmI,
} from "./api";

const SERVICES = [
  { key: "identity", label: "Identity", probe: "/p1/api/v1/health/live" },
  { key: "investigation", label: "Investigation", probe: "/api/v1/health/live" },
  { key: "risk", label: "Risk", probe: "/governance/summary" },
  { key: "entity", label: "Entity Intelligence", probe: "/customers" },
];

function displayPrincipal(principal) {
  return principal?.username || principal?.principal_id || principal?.sub || "Authorized user";
}

function LoginLanding({ onLogin }) {
  const [credentials, setCredentials] = useState({ username: "analyst", password: "CorrectHorse9!" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const auth = await requestLogin(credentials.username, credentials.password);
      const token = auth.access_token;
      const principal = token ? await whoAmI(token) : null;
      onLogin({ token, principal, tokenType: auth.token_type || "bearer" });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <span className="brand-mark">KYC</span>
          <div>
            <h1 id="login-title">Continuous KYC Autonomous Auditor</h1>
            <p>Secure compliance access</p>
          </div>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label className="field field-wide">
            <span className="field-label">login id</span>
            <input value={credentials.username} autoComplete="username" onChange={(e) => setCredentials({ ...credentials, username: e.target.value })} required />
          </label>
          <label className="field field-wide">
            <span className="field-label">password</span>
            <input type="password" value={credentials.password} autoComplete="current-password" onChange={(e) => setCredentials({ ...credentials, password: e.target.value })} required />
          </label>
          <button className="login-button" type="submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
        </form>
        {error && <div className="error-box">{error}</div>}
      </section>
    </main>
  );
}

function StatusDot({ state }) {
  return <span className={`status-dot ${state === "up" ? "up" : state === "down" ? "down" : "warn"}`} title={state || "checking"} />;
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-value">{value ?? "-"}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

function severityClass(level) {
  return `severity severity-${String(level || "low").toLowerCase()}`;
}

function confidenceBadge(value) {
  const raw = String(value ?? "medium").toLowerCase();
  const cls = raw.includes("high") || Number(value) >= 80 ? "badge-success" : raw.includes("low") || Number(value) < 55 ? "badge-info" : "badge-warning";
  return <span className={`badge ${cls}`}>{value ?? "medium"}</span>;
}

function outcomeBadge(outcome) {
  const map = {
    escalate_to_sar: ["Escalate to SAR", "badge-danger"],
    further_investigation: ["Further investigation", "badge-warning"],
    false_positive_clear: ["False positive cleared", "badge-success"],
  };
  const [label, cls] = map[outcome] || [outcome || "Not run", "badge-info"];
  return <span className={`badge ${cls}`}>{label}</span>;
}

function guardrailStats(gr) {
  if (!gr) return null;
  return (
    <div className="guardrail-stats compact">
      <span className="stat"><span className="stat-dot verified" />{gr.verified_count ?? 0} verified</span>
      <span className="stat"><span className="stat-dot stripped" />{gr.stripped_count ?? 0} stripped</span>
      <span className="stat"><span className="stat-dot skipped" />{gr.skipped_count ?? 0} skipped</span>
    </div>
  );
}

function pickClientScore(client) {
  let score = 24;
  if (isTrueFlag(client?.sanctions_flag)) score += 30;
  if (isTrueFlag(client?.pep_flag)) score += 18;
  if (isTrueFlag(client?.fatf_country_flag)) score += 14;
  if (isHighSector(client)) score += 18;
  return Math.min(score, 96);
}

function Timeline({ client }) {
  const score = pickClientScore(client);
  const items = [
    ["Initial KYC", Math.max(18, score - 42), "Profile ingested and normalized"],
    ["Screening", Math.max(24, score - 24), isTrueFlag(client?.sanctions_flag) ? "Sanctions indicator found" : isHighSector(client) ? "High sector risk requires screening" : "No confirmed sanctions match"],
    ["Risk update", score, isTrueFlag(client?.fatf_country_flag) ? "Jurisdiction risk added" : isHighSector(client) ? "Sector-risk score refreshed" : "Continuous score refreshed"],
  ];
  return (
    <ul className="timeline clickable-timeline">
      {items.map(([name, s, body]) => (
        <li key={name}>
          <span className="timeline-when">{s}/100</span>
          <span><strong>{name}</strong> {body}</span>
        </li>
      ))}
    </ul>
  );
}

function isTrueFlag(value) {
  return value === true || value === 1 || value === "1" || String(value).toLowerCase() === "true";
}

function isHighSector(client) {
  return ["high", "critical"].includes(String(client?.sector_risk || "").toLowerCase());
}

function profileSignalMatches(client) {
  if (!client) return [];
  const rows = [];
  if (isTrueFlag(client.sanctions_flag)) rows.push({ matched_against: client.client_name, match_score: 88, classification: "profile sanctions flag", component_scores: { profile: 1, evidence: 0.88 }, evidence_id: `KYC-${client.client_id}-sanctions_flag` });
  if (isTrueFlag(client.pep_flag)) rows.push({ matched_against: client.client_name, match_score: 82, classification: "PEP profile flag", component_scores: { profile: 1, evidence: 0.82 }, evidence_id: `KYC-${client.client_id}-pep_flag` });
  if (isHighSector(client)) rows.push({ matched_against: `${client.sector || "Customer sector"}`, match_score: 72, classification: "high sector risk", component_scores: { sector: 1, evidence: 0.72 }, evidence_id: `KYC-${client.client_id}-sector_risk` });
  return rows;
}

function MatchTable({ matches, selected, result }) {
  const rows = matches?.length ? matches : profileSignalMatches(selected);
  if (!rows.length) {
    return <div className="callout callout-info">No sanctions-list match crossed the configured threshold. The customer remains under baseline monitoring unless profile, transaction, media, or UBO evidence adds risk.</div>;
  }
  return (
    <>
      {!matches?.length && <div className="callout callout-warning">No direct list match crossed the sanctions threshold, so the table below shows profile-based risk signals from the loaded KYC data.</div>}
      {result?.decision && <div className="callout callout-info">Screening decision: {result.decision}. Confidence: {result.match_confidence ?? result.confidence ?? "not supplied"}.</div>}
      <table className="evidence-table">
        <thead><tr><th>Matched / flagged item</th><th>Score</th><th>Classification</th><th>Breakdown</th><th>Evidence</th></tr></thead>
        <tbody>
          {rows.map((m, i) => (
            <tr key={m.evidence_id || i}>
              <td>{m.matched_against || m.matched_entity_name || m.name || "-"}</td>
              <td><strong>{typeof m.match_score === "number" ? m.match_score.toFixed(2) : m.match_score ?? m.match_confidence ?? "-"}</strong></td>
              <td>{m.classification || m.decision || "review"}</td>
              <td><div className="chip-row">{Object.entries(m.component_scores || {}).map(([k, v]) => <span className="chip" key={k}>{k} {typeof v === "number" ? v.toFixed(2) : v}</span>)}</div></td>
              <td className="mono-sm">{m.evidence_id || m.result_id || "profile-signal"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function AuditSummary({ audit }) {
  if (!audit) return null;
  if (audit.status === "error") return <div className="error-box">Audit verification failed: {audit.detail}</div>;
  return (
    <div className={audit.valid ? "callout callout-success" : "callout callout-danger"}>
      <strong>{audit.valid ? "Hash chain verified" : "Hash chain broken"}</strong>
      <div>{audit.events_checked ?? 0} event(s) checked at {audit.checked_at || "this session"}.</div>
      {audit.broken_at && <div>Broken at: {audit.broken_at}. Reason: {audit.reason}</div>}
      {!audit.broken_at && <div>Latest check confirms the persisted governance audit log is still linked and tamper-evident.</div>}
    </div>
  );
}

function Workbench({ session, onLogout }) {
  const [health, setHealth] = useState({});
  const [summary, setSummary] = useState(null);
  const [clients, setClients] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [caseInfo, setCaseInfo] = useState(null);
  const [entityResult, setEntityResult] = useState(null);
  const [articles, setArticles] = useState([]);
  const [articleResult, setArticleResult] = useState(null);
  const [uboStructures, setUboStructures] = useState([]);
  const [uboResult, setUboResult] = useState(null);
  const [pipeline, setPipeline] = useState(null);
  const [auditCheck, setAuditCheck] = useState(null);
  const [reason, setReason] = useState("");
  const [reviewMessage, setReviewMessage] = useState(null);
  const [busy, setBusy] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    SERVICES.forEach((s) => probeHealth(s.probe).then((state) => setHealth((h) => ({ ...h, [s.key]: state }))));
    governanceSummary().then(setSummary).catch(() => {});
    listClients().then((data) => {
      const list = data.clients || [];
      setClients(list);
      setSelectedId(String(list[0]?.client_id || ""));
    }).catch((err) => setError(err.message));
    listArticles().then((data) => setArticles(data.articles || data || [])).catch(() => {});
    listUboStructures().then((data) => setUboStructures(data.structures || [])).catch(() => {});
  }, []);

  const selected = useMemo(() => clients.find((c) => String(c.client_id) === String(selectedId)), [clients, selectedId]);
  const riskScore = pickClientScore(selected);
  const confidence = selected?.sanctions_flag || selected?.pep_flag ? 91 : 76;

  useEffect(() => {
    if (!selectedId) return;
    setCaseInfo(null);
    setPipeline(null);
    setEntityResult(null);
    setArticleResult(null);
    setUboResult(null);
    caseDetail(selectedId, "compliance").then(setCaseInfo).catch(() => {});
  }, [selectedId]);

  async function runEntityIntelligence() {
    if (!selected) return;
    setBusy((b) => ({ ...b, entity: true }));
    setError(null);
    try {
      const result = await screen({ entity_id: `CUST-${selected.client_id}`, name: selected.client_name, nationality: selected.country, company: selected.client_name, context: `${selected.sector || "KYC"} customer from ${selected.country || "unknown jurisdiction"}` });
      setEntityResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, entity: false }));
    }
  }

  async function runArticleCheck() {
    if (!selected) return;
    setBusy((b) => ({ ...b, article: true }));
    setError(null);
    try {
      let available = articles;
      if (!available.length) {
        const refreshed = await listArticles();
        available = refreshed.articles || refreshed || [];
        setArticles(available);
      }
      const preferred = available.find((item) => String(typeof item === "string" ? item : item?.name).includes("adverse_hit")) || available[0];
      const articleName = typeof preferred === "string" ? preferred : preferred?.name;
      if (!articleName) {
        setArticleResult({ status: "not_configured", message: "No local adverse-media article is loaded yet. Add article files under data/articles to enable evidence analysis." });
        return;
      }
      setArticleResult(await analyzeArticle(`CUST-${selected.client_id}`, articleName));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, article: false }));
    }
  }

  async function runUboTrace() {
    if (!selected) return;
    setBusy((b) => ({ ...b, ubo: true }));
    setError(null);
    try {
      let available = uboStructures;
      if (!available.length) {
        const refreshed = await listUboStructures();
        available = refreshed.structures || refreshed || [];
        setUboStructures(available);
      }
      const preferred = available.find((item) => (item.roots || []).includes(`CUST-${selected.client_id}`)) || available[0];
      if (!preferred) {
        setUboResult({ status: "not_configured", root_entity_id: `CUST-${selected.client_id}`, findings: [], nodes_traversed: 0, message: "No UBO structure file is currently loaded. Add or select a JSON structure in data/ubo to trace ownership." });
        return;
      }
      setUboResult(await traceUbo({ structure: preferred.name || preferred, root_entity_id: preferred.roots?.[0] || `CUST-${selected.client_id}` }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, ubo: false }));
    }
  }

  async function runInvestigation() {
    if (!selectedId) return;
    setBusy((b) => ({ ...b, investigation: true }));
    setError(null);
    try {
      setPipeline(await investigate(selectedId));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((b) => ({ ...b, investigation: false }));
    }
  }

  async function review(action) {
    if (!selectedId || !reason.trim()) {
      setReviewMessage({ kind: "error", text: "A typed reason is required before any review action." });
      return;
    }
    setBusy((b) => ({ ...b, review: true }));
    setReviewMessage(null);
    try {
      const actor = displayPrincipal(session.principal);
      const result = action === "Sign off SAR"
        ? await sarSignoff(selectedId, { actor, reason })
        : await submitReview(selectedId, { actor, action, reason });
      const id = result.review_id || result.signoff_id || "decision";
      const label = result.action || result.status || action;
      setReviewMessage({ kind: "ok", text: `${label} recorded for customer ${selectedId}. Reference ${id}. The audit chain now has a new human-review event.` });
      caseDetail(selectedId, "compliance").then(setCaseInfo).catch(() => {});
      governanceAuditVerify().then((audit) => setAuditCheck({ ...audit, checked_at: new Date().toLocaleString() })).catch(() => {});
      setReason("");
    } catch (err) {
      setReviewMessage({ kind: "error", text: err.message });
    } finally {
      setBusy((b) => ({ ...b, review: false }));
    }
  }

  async function verifyAudit() {
    setBusy((b) => ({ ...b, audit: true }));
    try {
      const result = await governanceAuditVerify().catch(() => auditVerify());
      setAuditCheck({ ...result, checked_at: new Date().toLocaleString() });
    } catch (err) {
      setAuditCheck({ status: "error", detail: err.message });
    } finally {
      setBusy((b) => ({ ...b, audit: false }));
    }
  }

  return (
    <div className="shell workbench-shell">
      <header className="shell-header workbench-header">
        <div className="brand">
          <span className="brand-mark">KYC</span>
          <div>
            <h1>Continuous KYC Command Center</h1>
            <p className="brand-sub">One case journey: detect, explain, investigate, review, audit.</p>
          </div>
        </div>
        <div className="account-bar">
          <span className="account-name">{displayPrincipal(session.principal)}</span>
          <button className="secondary account-button" onClick={onLogout}>Sign out</button>
        </div>
      </header>

      {error && <div className="error-alert">{error}</div>}

      <section className="command-grid">
        <div className="command-main">
          <div className="card control-room-card">
            <div className="card-header"><h3>Overview Dashboard</h3><span className="timing">control room</span></div>
            <div className="card-body">
              <div className="metric-strip">
                <Metric label="Accounts monitored" value={summary?.accounts_monitored || clients.length} />
                <Metric label="Critical risk" value={summary?.critical_risk} />
                <Metric label="High risk" value={summary?.high_risk} />
                <Metric label="Pending reviews" value={summary?.pending_reviews} />
                <Metric label="SAR drafts" value={pipeline?.sar ? 1 : 0} />
                <Metric label="False positives prevented" value={summary?.false_positives_prevented} />
              </div>
              <div className="service-strip">
                {SERVICES.map((s) => <span className="service-pill" key={s.key}><StatusDot state={health[s.key]} />{s.label}</span>)}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header"><h3>Customer Risk Profile</h3><span className={severityClass(riskScore > 75 ? "critical" : riskScore > 55 ? "high" : "medium")}>{riskScore}/100</span></div>
            <div className="card-body">
              <div className="controls inline-form sticky-controls">
                <label className="field field-grow">
                  <span className="field-label">customer</span>
                  <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
                    {clients.map((c) => <option key={c.client_id} value={c.client_id}>#{c.client_id} - {c.client_name} ({c.country})</option>)}
                  </select>
                </label>
                <button onClick={runInvestigation} disabled={!selectedId || busy.investigation}>{busy.investigation ? "Investigating..." : "Run investigation"}</button>
              </div>

              {selected && (
                <div className="profile-grid">
                  <div className="score-panel">
                    <div className="score-number">{riskScore}</div>
                    <div className="metric-label">Risk score</div>
                  </div>
                  <div className="score-panel confidence-panel">
                    <div className="score-number">{confidence}%</div>
                    <div className="metric-label">Evidence confidence</div>
                  </div>
                  <div className="profile-facts">
                    <div className="kv"><span className="kv-key">Name</span><span className="kv-val">{selected.client_name}</span></div>
                    <div className="kv"><span className="kv-key">Country</span><span className="kv-val">{selected.country}</span></div>
                    <div className="kv"><span className="kv-key">Sector</span><span className="kv-val">{selected.sector}</span></div>
                    <div className="kv"><span className="kv-key">Risk drivers</span><span className="kv-val">{[isTrueFlag(selected.sanctions_flag) && "Sanctions", isTrueFlag(selected.pep_flag) && "PEP", isTrueFlag(selected.fatf_country_flag) && "FATF", selected.sector_risk && `${selected.sector_risk} sector`].filter(Boolean).join(", ") || "Baseline monitoring"}</span></div>
                  </div>
                </div>
              )}

              <div className="section-label">Clickable risk timeline</div>
              <Timeline client={selected} />
              {caseInfo?.assessment?.top_reasons?.length > 0 && <div className="callout callout-info">{caseInfo.assessment.top_reasons.join(" | ")}</div>}
            </div>
          </div>

          <div className="card">
            <div className="card-header"><h3>Entity Intelligence View</h3><span className="timing">sanctions, media, UBO</span></div>
            <div className="card-body">
              <div className="controls">
                <button onClick={runEntityIntelligence} disabled={!selected || busy.entity}>{busy.entity ? "Screening..." : "Screen sanctions"}</button>
                <button className="secondary" onClick={runArticleCheck} disabled={!selected || busy.article}>{busy.article ? "Checking..." : "Check adverse media"}</button>
                <button className="secondary" onClick={runUboTrace} disabled={!selected || busy.ubo}>{busy.ubo ? "Tracing..." : "Trace UBO graph"}</button>
              </div>
              <MatchTable selected={selected} result={entityResult} matches={entityResult?.matches || (Array.isArray(entityResult) ? entityResult : [])} />
              {articleResult && <div className={articleResult.injection_attempt_detected ? "callout callout-danger" : articleResult.status === "not_configured" ? "callout callout-warning" : "callout callout-success"}>{articleResult.injection_attempt_detected ? `Prompt injection detected: ${articleResult.injection_details}` : articleResult.message || articleResult.summary || "Adverse media checked. No prompt injection detected in the selected article."}</div>}
              {uboResult && <div className="ubo-map"><div className="section-label">Ownership graph</div>{uboResult.message && <div className="callout callout-warning">{uboResult.message}</div>}<div className="chain">{(uboResult.findings?.[0]?.ownership_path || [uboResult.root_entity_id, "screened owners"]).map((hop, i, arr) => <span className="chain-hop" key={`${hop}-${i}`}>{hop}{i < arr.length - 1 && <span className="chain-arrow">→</span>}</span>)}</div><p className="muted">{uboResult.findings?.length || 0} sanctioned owner finding(s), {uboResult.nodes_traversed || 0} node(s) traversed.</p></div>}
            </div>
          </div>
        </div>

        <aside className="case-rail">
          <div className="card">
            <div className="card-header"><h3>Why flagged?</h3></div>
            <div className="card-body">
              <ul className="risk-list">
                <li><span className={severityClass(isTrueFlag(selected?.sanctions_flag) ? "critical" : "low")}>sanctions</span>{isTrueFlag(selected?.sanctions_flag) ? "+30 confirmed indicator" : "No direct flag"}</li>
                <li><span className={severityClass(isTrueFlag(selected?.pep_flag) ? "high" : "low")}>PEP</span>{isTrueFlag(selected?.pep_flag) ? "+18 politically exposed person" : "No PEP flag"}</li>
                <li><span className={severityClass(isTrueFlag(selected?.fatf_country_flag) ? "high" : "low")}>jurisdiction</span>{isTrueFlag(selected?.fatf_country_flag) ? "+14 FATF country flag" : "No FATF flag"}</li>
                <li><span className={severityClass(isHighSector(selected) ? "high" : "medium")}>sector</span>{isHighSector(selected) ? `+18 ${selected?.sector_risk} sector risk` : `${selected?.sector_risk || "Baseline"} sector risk`}</li>
              </ul>
            </div>
          </div>

          <div className="card">
            <div className="card-header"><h3>Audit integrity</h3></div>
            <div className="card-body">
              <button onClick={verifyAudit} disabled={busy.audit}>{busy.audit ? "Verifying..." : "Verify hash chain"}</button>
              <AuditSummary audit={auditCheck} />
            </div>
          </div>
        </aside>
      </section>

      <section className="card">
        <div className="card-header"><h3>Investigation Workspace</h3><span>{outcomeBadge(pipeline?.outcome)}</span></div>
        <div className="card-body">
          {!pipeline && <p className="muted">Run an investigation to see data gathering, agent reasoning, debate, verdict, and SAR drafting in one case file.</p>}
          {busy.investigation && <div className="spinner-overlay"><div className="spinner" /><p>Running autonomous investigation. This can take 15-60 seconds.</p></div>}
          {pipeline && (
            <div className="stage-grid">
              <div className="stage-card"><div className="section-label">Stage 1</div><h4>Data gathered</h4><p>Customer profile, transaction signals, sanctions matches, and available evidence were collected.</p></div>
              <div className="stage-card"><div className="section-label">Stage 2</div><h4>Investigation finding</h4><p>{pipeline.investigation?.finding?.summary}</p>{confidenceBadge(pipeline.investigation?.finding?.confidence)}{guardrailStats(pipeline.investigation?.guardrail)}</div>
              <div className="stage-card"><div className="section-label">Stage 3</div><h4>Prosecutor vs Defender</h4><p>{pipeline.debate?.verdict?.reasoning}</p>{guardrailStats(pipeline.debate?.prosecution_guardrail)}{guardrailStats(pipeline.debate?.defense_guardrail)}</div>
              <div className="stage-card"><div className="section-label">Stage 4</div><h4>Judge verdict</h4>{outcomeBadge(pipeline.debate?.verdict?.verdict)}<p>Confidence: {confidenceBadge(pipeline.debate?.verdict?.confidence)}</p></div>
              <div className="stage-card wide"><div className="section-label">Stage 5</div><h4>SAR draft</h4>{pipeline.sar ? <><div className="sar-narrative">{pipeline.sar.sar?.narrative}</div>{guardrailStats(pipeline.sar.grounding_guardrail)}<p className="muted">Privacy redactions: {pipeline.sar.privacy_guardrail?.redaction_count ?? 0}</p></> : <p>No SAR draft needed unless the verdict escalates.</p>}</div>
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="card-header"><h3>Human Review & SAR Sign-off</h3><span className="timing">typed reason required</span></div>
        <div className="card-body">
          <label className="field field-wide">
            <span className="field-label">decision reason</span>
            <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Explain the evidence used for this decision." />
          </label>
          <div className="controls">
            {["Approve escalation", "Request more investigation", "Mark false positive"].map((action) => <button key={action} onClick={() => review(action)} disabled={busy.review}>{action}</button>)}<button className="secondary" onClick={() => review("Sign off SAR")} disabled={busy.review || !pipeline?.sar}>Sign off SAR draft</button>
          </div>
          {reviewMessage && <div className={reviewMessage.kind === "ok" ? "callout callout-success" : "error-box"}>{reviewMessage.text}</div>}
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(() => {
    const raw = sessionStorage.getItem("ckyc-session");
    return raw ? JSON.parse(raw) : null;
  });

  useEffect(() => {
    if (session) sessionStorage.setItem("ckyc-session", JSON.stringify(session));
    else sessionStorage.removeItem("ckyc-session");
  }, [session]);

  if (!session) return <LoginLanding onLogin={setSession} />;
  return <Workbench session={session} onLogout={() => setSession(null)} />;
}
