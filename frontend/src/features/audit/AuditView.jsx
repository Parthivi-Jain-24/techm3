// Hash-chained audit trails. Two independent chains exist -- Part 2's screening
// sink and Part 5's governance log -- so both are shown with their own verify
// state rather than implying a single system-wide chain.

import { useEffect, useState } from "react";
import {
  auditEvents,
  auditVerify,
  governanceAudit,
  governanceAuditVerify,
} from "../../api";

function VerifyBadge({ verdict }) {
  if (!verdict) return <span className="badge badge-info">checking…</span>;
  if (verdict.error) return <span className="badge badge-info">unavailable</span>;
  if (verdict.valid) {
    return (
      <span className="badge badge-success">
        VALID · {verdict.events_checked ?? "?"} events
      </span>
    );
  }
  return (
    <span className="badge badge-danger">
      BROKEN at {verdict.broken_at || "?"} — {verdict.reason}
    </span>
  );
}

function ChainCard({ title, note, events, verdict, error, columns }) {
  return (
    <div className="card">
      <div className="card-header">
        <h3>{title}</h3>
        <VerifyBadge verdict={verdict} />
      </div>
      <div className="card-body">
        <p className="muted">{note}</p>
        {error && <div className="error-box">{error}</div>}
        {events?.length ? (
          <table className="evidence-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={e.event_id || i}>
                  <td className="mono-sm">{e.event_id}</td>
                  <td>{e.action}</td>
                  <td className="mono-sm">{(e.previous_hash || "").slice(0, 10)}…</td>
                  <td className="mono-sm">{(e.event_hash || e.hash || "").slice(0, 10)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          !error && <p className="muted">No events recorded yet.</p>
        )}
      </div>
    </div>
  );
}

export default function AuditView() {
  const [p2, setP2] = useState({ events: [], verdict: null, error: null });
  const [p5, setP5] = useState({ events: [], verdict: null, error: null });

  async function load() {
    // Each chain loads independently: one service being down must still leave
    // the other chain's verdict visible.
    try {
      const [ev, vr] = await Promise.all([auditEvents(25), auditVerify()]);
      setP2({ events: ev.events || [], verdict: vr, error: null });
    } catch (err) {
      setP2({ events: [], verdict: { error: true }, error: err.message });
    }
    try {
      const [ev, vr] = await Promise.all([governanceAudit(), governanceAuditVerify()]);
      setP5({ events: ev || [], verdict: vr, error: null });
    } catch (err) {
      setP5({ events: [], verdict: { error: true }, error: err.message });
    }
  }

  useEffect(() => {
    load();
  }, []);

  const cols = ["Event", "Action", "prev hash", "hash"];

  return (
    <div className="stack">
      <div className="controls">
        <button onClick={load}>Re-verify both chains</button>
      </div>
      <ChainCard
        title="Part 2 — Screening audit chain"
        note="SHA-256 chained, in-memory. Every screening decision and injection detection is linked to its predecessor; altering one event breaks verification at that entry."
        {...p2}
        columns={cols}
      />
      <ChainCard
        title="Part 5 — Governance audit chain"
        note="SHA-256 chained and persisted to SQLite, so the chain continues across restarts rather than re-anchoring at genesis."
        {...p5}
        columns={cols}
      />
    </div>
  );
}
