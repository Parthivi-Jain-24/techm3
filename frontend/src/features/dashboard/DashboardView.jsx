// Landing view: the architecture flow, live service health, and headline numbers.

import { useEffect, useState } from "react";
import { governanceSummary, probeHealth } from "../../api";

// Each entry probes the service it names. Part 1 uses /p1/* deliberately: /api/v1
// is proxied to :8002, so probing it here would report :8002's health under Part
// 1's label and show green while :8001 was down.
const SERVICES = [
  { key: "p1", label: "Part 1 — Secure Data & Identity", probe: "/p1/api/v1/health/live", docs: "http://127.0.0.1:8001/docs" },
  { key: "p2", label: "Part 2 — Entity Intelligence", probe: "/customers", docs: "http://127.0.0.1:8004/docs" },
  { key: "p35", label: "Part 3+5 — Risk & Governance", probe: "/governance/summary", docs: "http://127.0.0.1:8003/docs" },
  { key: "p4", label: "Part 4 — Investigation & SAR", probe: "/api/v1/clients", docs: "http://127.0.0.1:8002/docs" },
];

const FLOW = [
  { n: 1, title: "Secure Data & Identity", body: "Ingest KYC, normalize, authenticate, enforce RBAC." },
  { n: 2, title: "Entity Intelligence", body: "Screen against OFAC/OpenSanctions, adverse media, UBO tracing." },
  { n: 3, title: "Risk Intelligence", body: "Turn evidence into a scored, explainable assessment." },
  { n: 4, title: "Autonomous Investigation", body: "Investigate, debate, draft the SAR — grounded and privacy-guarded." },
  { n: 5, title: "Human Review & Governance", body: "A person decides. Reason mandatory. Everything audited." },
];

function StatusDot({ state }) {
  const cls = state === "up" ? "up" : state === "down" ? "down" : "warn";
  return <span className={`status-dot ${cls}`} title={state} />;
}

export default function DashboardView({ onNavigate }) {
  const [health, setHealth] = useState({});
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    SERVICES.forEach((s) =>
      probeHealth(s.probe).then((state) =>
        setHealth((h) => ({ ...h, [s.key]: state }))
      )
    );
    governanceSummary().then(setSummary).catch(() => {});
  }, []);

  return (
    <div className="stack">
      <div className="card">
        <div className="card-header">
          <h3>Service health</h3>
          <span className="timing">live probes</span>
        </div>
        <div className="card-body">
          <div className="health-grid">
            {SERVICES.map((s) => (
              <div className="health-item" key={s.key}>
                <StatusDot state={health[s.key]} />
                <span className="health-label">{s.label}</span>
                <a className="health-docs" href={s.docs} target="_blank" rel="noreferrer">
                  API docs ↗
                </a>
              </div>
            ))}
          </div>
          {Object.values(health).includes("down") && (
            <div className="callout callout-info">
              A service showing <strong>down</strong> just means it is not running — start
              everything with <code>powershell -File scripts\dev_up.ps1</code>. Part 2 takes
              ~40s to index 1.29M sanctioned entities before it answers.
            </div>
          )}
        </div>
      </div>

      {summary && (
        <div className="metric-strip">
          {[
            ["Accounts monitored", summary.accounts_monitored],
            ["Transactions", summary.transactions_loaded],
            ["Critical risk", summary.critical_risk],
            ["High risk", summary.high_risk],
            ["False positives prevented", summary.false_positives_prevented],
            ["Audit events", summary.audit_events],
          ].map(([label, value]) => (
            <div className="metric" key={label}>
              <div className="metric-value">{value ?? "—"}</div>
              <div className="metric-label">{label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>How a customer flows through the system</h3>
        </div>
        <div className="card-body">
          <div className="flow">
            {FLOW.map((f) => (
              <div className="flow-step" key={f.n}>
                <div className="flow-n">{f.n}</div>
                <div>
                  <div className="flow-title">{f.title}</div>
                  <div className="flow-body">{f.body}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="callout callout-info">
            Underneath all five: a <strong>hash-chained audit trail</strong>. Every decision is
            linked to the one before it, so altering history is detectable —{" "}
            <button className="linklike" onClick={() => onNavigate?.("audit")}>
              verify the chains
            </button>
            .
          </div>
        </div>
      </div>
    </div>
  );
}
