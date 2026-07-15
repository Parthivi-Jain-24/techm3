// Part 3 + Part 5 -- Risk assessment, case review, and SAR sign-off.

import { useEffect, useState } from "react";
import {
  caseDetail,
  governanceSummary,
  listCases,
  sarSignoff,
  submitReview,
} from "../../api";

function severityClass(level) {
  return `severity severity-${String(level || "low").toLowerCase()}`;
}

function SummaryStrip({ summary }) {
  if (!summary) return null;
  const cells = [
    ["Accounts monitored", summary.accounts_monitored],
    ["Transactions", summary.transactions_loaded],
    ["Critical", summary.critical_risk],
    ["High", summary.high_risk],
    ["Pending reviews", summary.pending_reviews],
    ["FPs prevented", summary.false_positives_prevented],
    ["Audit events", summary.audit_events],
  ];
  return (
    <div className="metric-strip">
      {cells.map(([label, value]) => (
        <div className="metric" key={label}>
          <div className="metric-value">{value ?? "—"}</div>
          <div className="metric-label">{label}</div>
        </div>
      ))}
    </div>
  );
}

function ReviewForm({ customerId, onDone }) {
  const [action, setAction] = useState("Approve Escalation");
  const [reason, setReason] = useState("");
  const [actor, setActor] = useState("Compliance Officer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);

  async function submit(kind) {
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const res =
        kind === "review"
          ? await submitReview(customerId, { action, reason, actor })
          : await sarSignoff(customerId, { reason, actor });
      setOk(res.review_id || res.signoff_id || "recorded");
      setReason("");
      onDone?.();
    } catch (err) {
      // The backend rejects a blank reason with 400 -- that is the four-eyes
      // control, not a UI bug, so show it verbatim.
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Human Review</h3>
        <span className="timing">reason is mandatory</span>
      </div>
      <div className="card-body">
        <div className="controls inline-form">
          <label className="field">
            <span className="field-label">actor</span>
            <input value={actor} onChange={(e) => setActor(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">action</span>
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option>Approve Escalation</option>
              <option>Reject Escalation</option>
              <option>Request More Information</option>
            </select>
          </label>
        </div>
        <label className="field field-wide">
          <span className="field-label">reason (required — recorded in the audit trail)</span>
          <textarea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why this decision? Cite the evidence you relied on."
          />
        </label>
        <div className="controls">
          <button onClick={() => submit("review")} disabled={busy}>
            {busy ? "Submitting…" : "Submit review"}
          </button>
          <button className="secondary" onClick={() => submit("sar")} disabled={busy}>
            Sign off SAR
          </button>
        </div>
        {error && <div className="error-box">{error}</div>}
        {ok && <div className="callout callout-success">Recorded: {ok}</div>}
      </div>
    </div>
  );
}

function CaseDetail({ detail, role, onReviewed }) {
  if (!detail) return null;
  const a = detail.assessment || {};

  return (
    <div className="stack">
      <div className="card">
        <div className="card-header">
          <h3>
            {detail.case_id} — {detail.name}
          </h3>
          <span className={severityClass(a.risk_level)}>
            {a.risk_level} {a.risk_score != null && `· ${a.risk_score}`}
          </span>
        </div>
        <div className="card-body">
          <div className="kv-grid">
            {[
              ["Status", detail.status],
              ["Assigned team", detail.assigned_team],
              ["Country", detail.profile?.country],
              ["Sector", detail.profile?.sector],
              ["PEP", String(detail.profile?.pep_flag)],
              ["Sanctions flag", String(detail.profile?.sanctions_flag)],
              ["Beneficial owner", detail.profile?.beneficial_owner],
            ].map(([k, v]) => (
              <div className="kv" key={k}>
                <span className="kv-key">{k}</span>
                <span className="kv-val">{v ?? "—"}</span>
              </div>
            ))}
          </div>

          {!detail.sensitive_visible && (
            <div className="callout callout-info">
              Role <strong>{role}</strong> — sensitive fields are masked by RBAC.
            </div>
          )}

          {a.top_reasons?.length > 0 && (
            <>
              <div className="section-label">Top risk drivers</div>
              <ul className="risk-list">
                {a.top_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </>
          )}

          {a.evidence_ids?.length > 0 && (
            <>
              <div className="section-label">Evidence IDs (traceable to source)</div>
              <div className="chip-row">
                {a.evidence_ids.map((id) => (
                  <span className="chip" key={id}>
                    {id}
                  </span>
                ))}
              </div>
            </>
          )}

          {detail.timeline?.length > 0 && (
            <>
              <div className="section-label">Timeline</div>
              <ul className="timeline">
                {detail.timeline.map((t, i) => (
                  <li key={i}>
                    <span className="timeline-when">{t.timestamp || t.when || ""}</span>
                    <span>{t.event || t.description || JSON.stringify(t)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      {detail.reviews?.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3>Prior decisions</h3>
          </div>
          <div className="card-body">
            <table className="evidence-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {detail.reviews.map((r) => (
                  <tr key={r.review_id}>
                    <td className="mono-sm">{r.review_id}</td>
                    <td>{r.actor}</td>
                    <td>{r.action}</td>
                    <td>{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ReviewForm customerId={detail.customer_id} onDone={onReviewed} />
    </div>
  );
}

export default function CasesView() {
  const [summary, setSummary] = useState(null);
  const [cases, setCases] = useState([]);
  const [role, setRole] = useState("compliance");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    governanceSummary().then(setSummary).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    listCases(role)
      .then((list) => {
        setCases(list);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [role]);

  function open(id) {
    setSelected(id);
    setDetail(null);
    caseDetail(id, role).then(setDetail).catch((err) => setError(err.message));
  }

  const refresh = () => selected && open(selected);

  return (
    <div className="stack">
      <SummaryStrip summary={summary} />

      <div className="card">
        <div className="card-header">
          <h3>Cases</h3>
          <label className="field inline">
            <span className="field-label">role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="compliance">compliance</option>
              <option value="investigator">investigator</option>
              <option value="auditor">auditor</option>
            </select>
          </label>
        </div>
        <div className="card-body">
          {error && <div className="error-box">{error}</div>}
          {loading ? (
            <p className="muted">Loading cases…</p>
          ) : (
            <table className="evidence-table clickable">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Name</th>
                  <th>Score</th>
                  <th>Level</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr
                    key={c.case_id}
                    onClick={() => open(c.customer_id)}
                    className={selected === c.customer_id ? "row-selected" : ""}
                  >
                    <td className="mono-sm">{c.case_id}</td>
                    <td>{c.name}</td>
                    <td>
                      <strong>{c.risk_score}</strong>
                    </td>
                    <td>
                      <span className={severityClass(c.risk_level)}>{c.risk_level}</span>
                    </td>
                    <td>{c.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {selected && !detail && <p className="muted">Loading case {selected}…</p>}
      <CaseDetail detail={detail} role={role} onReviewed={refresh} />
    </div>
  );
}
