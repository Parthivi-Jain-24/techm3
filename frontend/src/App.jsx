import { useState, useEffect } from "react";
import "./App.css";

// ── Helpers ──────────────────────────────────────────────────────────

function verdictBadge(outcome) {
  const map = {
    escalate_to_sar: ["Escalate to SAR", "badge badge-danger"],
    further_investigation: ["Further Investigation", "badge badge-warning"],
    false_positive_clear: ["False Positive — Clear", "badge badge-success"],
    error: ["Error", "badge badge-danger"],
  };
  const [label, cls] = map[outcome] || [outcome, "badge badge-info"];
  return <span className={cls}>{label}</span>;
}

function severityClass(level) {
  return `severity severity-${(level || "low").toLowerCase()}`;
}

function confidenceBadge(level) {
  const cls =
    level === "high"
      ? "badge badge-success"
      : level === "medium"
        ? "badge badge-warning"
        : "badge badge-info";
  return <span className={cls}>{level}</span>;
}

function formatMs(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── GuardrailStats ───────────────────────────────────────────────────

function GuardrailStats({ gr, label }) {
  if (!gr) return null;
  return (
    <div style={{ marginTop: "0.5rem" }}>
      {label && <div className="section-label">{label}</div>}
      <div className="guardrail-stats">
        <span className="stat">
          <span className="stat-dot verified" /> {gr.verified_count} verified
        </span>
        <span className="stat">
          <span className="stat-dot stripped" /> {gr.stripped_count} stripped
        </span>
        <span className="stat">
          <span className="stat-dot skipped" /> {gr.skipped_count} skipped
        </span>
      </div>
      {gr.unverified && gr.unverified.length > 0 && (
        <details style={{ marginTop: "0.4rem", fontSize: "0.8rem" }}>
          <summary style={{ cursor: "pointer", color: "#dc3545" }}>
            {gr.unverified.length} unverified citation(s)
          </summary>
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Source ID</th>
                <th>Type</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {gr.unverified.map((u, i) => (
                <tr key={i}>
                  <td><code>{u.source_id}</code></td>
                  <td>{u.source_type}</td>
                  <td>{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

// ── EvidenceTable ────────────────────────────────────────────────────

function EvidenceTable({ evidence }) {
  if (!evidence || evidence.length === 0) return null;
  return (
    <table className="evidence-table">
      <thead>
        <tr>
          <th>Claim</th>
          <th>Source Type</th>
          <th>Source ID</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {evidence.map((ev, i) => (
          <tr key={i}>
            <td>{ev.claim}</td>
            <td>{ev.source_type}</td>
            <td><code>{ev.source_id}</code></td>
            <td>{confidenceBadge(ev.confidence)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── InvestigationPanel ───────────────────────────────────────────────

function InvestigationPanel({ stage }) {
  const { finding, guardrail, duration_ms } = stage;
  return (
    <div className="card">
      <div className="card-header">
        <span>Stage 2 — Investigation Finding</span>
        <span className="timing">{formatMs(duration_ms)}</span>
      </div>
      <div className="card-body">
        <p style={{ margin: "0 0 0.5rem" }}>
          <strong>Confidence:</strong> {confidenceBadge(finding.confidence)}
        </p>
        <p style={{ margin: "0 0 0.75rem", fontSize: "0.9rem" }}>
          {finding.summary}
        </p>

        {finding.risk_indicators && finding.risk_indicators.length > 0 && (
          <>
            <div className="section-label">Risk Indicators</div>
            <ul className="risk-list">
              {finding.risk_indicators.map((ri, i) => (
                <li key={i}>
                  <span className={severityClass(ri.severity)}>
                    {ri.severity}
                  </span>
                  <strong>{ri.indicator}</strong>
                  {ri.detail && <span> — {ri.detail}</span>}
                </li>
              ))}
            </ul>
          </>
        )}

        <div className="section-label">Evidence</div>
        <EvidenceTable evidence={finding.evidence} />

        <GuardrailStats gr={guardrail} label="Grounding Guardrail" />
      </div>
    </div>
  );
}

// ── DebatePanel ──────────────────────────────────────────────────────

function DebateSide({ title, argument, guardrail, color }) {
  return (
    <div className="debate-side" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
      <h4>{title}</h4>
      <p style={{ margin: "0 0 0.3rem", fontSize: "0.8rem" }}>
        Position: {verdictBadge(argument.position === "risk_confirmed" ? "escalate_to_sar" : "false_positive_clear")}
        {" "}Strength: {confidenceBadge(argument.strength)}
      </p>
      <div className="argument-text">{argument.argument}</div>
      {argument.cited_evidence && argument.cited_evidence.length > 0 && (
        <div className="cited">
          <strong>Cited evidence:</strong>{" "}
          {argument.cited_evidence.map((ref, i) => (
            <span key={i}>
              <code>{ref}</code>
              {i < argument.cited_evidence.length - 1 && ", "}
            </span>
          ))}
        </div>
      )}
      <GuardrailStats gr={guardrail} />
    </div>
  );
}

function DebatePanel({ stage }) {
  const {
    prosecution,
    prosecution_guardrail,
    defense,
    defense_guardrail,
    verdict,
    duration_ms,
  } = stage;

  return (
    <div className="card">
      <div className="card-header">
        <span>Stage 3 — Adversarial Debate</span>
        <span className="timing">{formatMs(duration_ms)}</span>
      </div>
      <div className="card-body">
        <div className="debate-columns">
          <DebateSide
            title="Prosecutor"
            argument={prosecution}
            guardrail={prosecution_guardrail}
            color="#dc3545"
          />
          <DebateSide
            title="Defender"
            argument={defense}
            guardrail={defense_guardrail}
            color="#198754"
          />
        </div>

        <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#f8f9fa", borderRadius: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <strong>Judge Verdict:</strong>
            {verdictBadge(verdict.verdict)}
            <span style={{ marginLeft: "auto" }}>
              Confidence: {confidenceBadge(verdict.confidence)}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
            {verdict.reasoning}
          </p>
          {verdict.key_deciding_evidence && verdict.key_deciding_evidence.length > 0 && (
            <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#6c757d" }}>
              <strong>Key evidence:</strong>{" "}
              {verdict.key_deciding_evidence.map((ref, i) => (
                <span key={i}>
                  <code>{ref}</code>
                  {i < verdict.key_deciding_evidence.length - 1 && ", "}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── RedactionLogPanel ────────────────────────────────────────────────

function RedactionLogPanel({ privacy }) {
  if (!privacy || privacy.redaction_count === 0) return null;

  return (
    <div className="card">
      <div className="card-header">
        <span>Privacy Guardrail — Redaction Log</span>
        <span className="timing">{privacy.redaction_count} redaction(s)</span>
      </div>
      <div className="card-body">
        {privacy.gdpr_articles_cited && privacy.gdpr_articles_cited.length > 0 && (
          <p style={{ fontSize: "0.8rem", margin: "0 0 0.5rem" }}>
            <strong>GDPR articles cited:</strong>{" "}
            {privacy.gdpr_articles_cited.join(", ")}
          </p>
        )}
        <table className="evidence-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Original</th>
              <th>Replacement</th>
              <th>GDPR Article</th>
              <th>OPP-115</th>
            </tr>
          </thead>
          <tbody>
            {privacy.redactions.map((r, i) => (
              <tr key={i}>
                <td>{r.field}</td>
                <td><code>{r.original_snippet}</code></td>
                <td><code>{r.replacement}</code></td>
                <td style={{ fontSize: "0.75rem" }}>{r.gdpr_article}</td>
                <td style={{ fontSize: "0.75rem" }}>{r.opp115_category}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── SARPanel ─────────────────────────────────────────────────────────

function SARPanel({ stage }) {
  if (!stage) return null;

  const { sar, grounding_guardrail, privacy_guardrail, duration_ms } = stage;

  return (
    <>
      <div className="card">
        <div className="card-header">
          <span>Stage 4 — SAR Draft</span>
          <span className="timing">{formatMs(duration_ms)}</span>
        </div>
        <div className="card-body">
          <div className="section-label">Subject Information</div>
          <div className="sar-narrative">{sar.subject_information}</div>

          <div className="section-label">Narrative</div>
          <div className="sar-narrative">{sar.narrative}</div>

          {sar.red_flags && sar.red_flags.length > 0 && (
            <>
              <div className="section-label">Red Flags</div>
              <ul className="red-flags">
                {sar.red_flags.map((rf, i) => (
                  <li key={i}>{rf}</li>
                ))}
              </ul>
            </>
          )}

          {sar.regulatory_basis && sar.regulatory_basis.length > 0 && (
            <>
              <div className="section-label">Regulatory Basis</div>
              <ul className="red-flags">
                {sar.regulatory_basis.map((rb, i) => (
                  <li key={i}>{rb}</li>
                ))}
              </ul>
            </>
          )}

          <div className="section-label">Recommended Action</div>
          <p style={{ fontSize: "0.85rem", margin: "0.25rem 0" }}>
            {sar.recommended_action}
          </p>

          {sar.evidence_appendix && sar.evidence_appendix.length > 0 && (
            <>
              <div className="section-label">Evidence Appendix</div>
              <EvidenceTable evidence={sar.evidence_appendix} />
            </>
          )}

          {sar.disclaimer && (
            <div className="disclaimer">{sar.disclaimer}</div>
          )}

          <GuardrailStats gr={grounding_guardrail} label="Grounding Guardrail" />
        </div>
      </div>

      <RedactionLogPanel privacy={privacy_guardrail} />
    </>
  );
}

// ── TimingPanel ──────────────────────────────────────────────────────

function TimingPanel({ result }) {
  const inv = result.investigation.duration_ms;
  const deb = result.debate.duration_ms;
  const sar = result.sar ? result.sar.duration_ms : 0;
  const total = result.total_duration_ms || inv + deb + sar;

  const pctInv = Math.max(((inv / total) * 100), 5);
  const pctDeb = Math.max(((deb / total) * 100), 5);
  const pctSar = sar > 0 ? Math.max(((sar / total) * 100), 5) : 0;

  return (
    <div className="card">
      <div className="card-header">
        <span>Pipeline Timing</span>
        <span className="timing">Total: {formatMs(total)}</span>
      </div>
      <div className="card-body">
        <div className="timing-bar">
          <div
            className="segment seg-investigation"
            style={{ width: `${pctInv}%` }}
          >
            {formatMs(inv)}
          </div>
          <div
            className="segment seg-debate"
            style={{ width: `${pctDeb}%` }}
          >
            {formatMs(deb)}
          </div>
          {sar > 0 && (
            <div
              className="segment seg-sar"
              style={{ width: `${pctSar}%` }}
            >
              {formatMs(sar)}
            </div>
          )}
        </div>
        <div className="timing-legend">
          <span className="leg-investigation">Investigation ({formatMs(inv)})</span>
          <span className="leg-debate">Debate ({formatMs(deb)})</span>
          {sar > 0 && <span className="leg-sar">SAR ({formatMs(sar)})</span>}
        </div>
      </div>
    </div>
  );
}

// ── ResultsView ──────────────────────────────────────────────────────

function ResultsView({ result }) {
  return (
    <div>
      {/* Outcome banner */}
      <div
        className="card"
        style={{ textAlign: "center", padding: "1rem" }}
      >
        <div style={{ fontSize: "0.8rem", color: "#6c757d", marginBottom: "0.25rem" }}>
          Client #{result.client_id} — Pipeline Outcome
        </div>
        <div>{verdictBadge(result.outcome)}</div>
        {result.error && (
          <div className="error-alert" style={{ marginTop: "0.5rem" }}>
            {result.error}
          </div>
        )}
      </div>

      <TimingPanel result={result} />
      <InvestigationPanel stage={result.investigation} />
      <DebatePanel stage={result.debate} />
      {result.sar && <SARPanel stage={result.sar} />}
    </div>
  );
}

// ── App ──────────────────────────────────────────────────────────────

function App() {
  const [clients, setClients] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [loadingClients, setLoadingClients] = useState(true);

  // Fetch clients on mount
  useEffect(() => {
    fetch("/api/v1/clients")
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load clients (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setClients(data.clients || []);
        setLoadingClients(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoadingClients(false);
      });
  }, []);

  async function runInvestigation() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`/api/v1/investigate/${selectedId}`, {
        method: "POST",
      });

      if (res.status === 409) {
        setError("Pipeline is already running for this client. Please wait.");
        return;
      }
      if (res.status === 404) {
        setError("Client not found in KYC dataset.");
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(
          body?.detail ||
            `Pipeline failed (HTTP ${res.status}). Check server logs.`
        );
        return;
      }

      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Network error — is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  // Build risk badge text for dropdown option
  function clientLabel(c) {
    const flags = [];
    if (c.pep_flag) flags.push("PEP");
    if (c.sanctions_flag) flags.push("SANC");
    if (c.fatf_country_flag) flags.push("FATF");
    const risk = flags.length > 0 ? ` [${flags.join(",")}]` : "";
    return `#${c.client_id} — ${c.client_name} (${c.country}, ${c.sector_risk} risk)${risk}`;
  }

  return (
    <div className="dashboard">
      <h1>Continuous KYC — Investigation Dashboard</h1>

      {/* Controls */}
      <div className="controls">
        <select
          value={selectedId}
          onChange={(e) => {
            setSelectedId(e.target.value);
            setResult(null);
            setError(null);
          }}
          disabled={loadingClients || loading}
        >
          <option value="">
            {loadingClients
              ? "Loading clients..."
              : `Select a client (${clients.length} available)`}
          </option>
          {clients.map((c) => (
            <option key={c.client_id} value={c.client_id}>
              {clientLabel(c)}
            </option>
          ))}
        </select>
        <button
          onClick={runInvestigation}
          disabled={!selectedId || loading}
        >
          {loading ? "Investigating..." : "Investigate"}
        </button>
      </div>

      {/* Error */}
      {error && <div className="error-alert">{error}</div>}

      {/* Loading */}
      {loading && (
        <div className="spinner-overlay">
          <div className="spinner" />
          <p>Running pipeline — this may take 15-60 seconds...</p>
        </div>
      )}

      {/* Results */}
      {result && !loading && <ResultsView result={result} />}
    </div>
  );
}

export default App;
