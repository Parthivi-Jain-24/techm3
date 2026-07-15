// Part 2 -- Entity Intelligence: sanctions screening, adverse media, UBO tracing.

import { useEffect, useState } from "react";
import {
  analyzeArticle,
  listArticles,
  listUboStructures,
  screen,
  traceUbo,
} from "../../api";

function decisionBadge(decision) {
  const d = String(decision || "").toLowerCase();
  if (d.includes("confirmed")) return "badge badge-danger";
  if (d.includes("possible") || d.includes("review")) return "badge badge-warning";
  if (d.includes("no_match") || d.includes("cleared")) return "badge badge-success";
  return "badge badge-info";
}

// Field names below are the API's actual contract (matched_against / match_score /
// classification / component_scores), confirmed against a live response -- not the
// generic name/score/decision shape.
function MatchTable({ matches }) {
  if (!matches?.length) {
    return <p className="muted">No match above threshold — the name screened clean.</p>;
  }
  return (
    <table className="evidence-table">
      <thead>
        <tr>
          <th>Matched against</th>
          <th>Score</th>
          <th>Classification</th>
          <th>Why it matched</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        {matches.map((m, i) => (
          <tr key={m.evidence_id || i}>
            <td className="mono-sm">{m.matched_against ?? "—"}</td>
            <td>
              <strong>
                {typeof m.match_score === "number" ? m.match_score.toFixed(2) : m.match_score ?? "—"}
              </strong>
            </td>
            <td>
              <span className={decisionBadge(m.classification)}>{m.classification ?? "—"}</span>
            </td>
            <td>
              {/* The component scores are the explainability story: they show which
                  signals (name, dob, nationality...) actually drove the score. */}
              <div className="chip-row">
                {Object.entries(m.component_scores || {}).map(([k, v]) => (
                  <span className="chip" key={k}>
                    {k} {typeof v === "number" ? v.toFixed(2) : v}
                  </span>
                ))}
              </div>
            </td>
            <td className="mono-sm">{m.evidence_id ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ScreenPanel() {
  const [form, setForm] = useState({
    name: "Mohammed Al Rashid",
    dob: "1975",
    nationality: "UAE",
  });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== "")
      );
      setResult(await screen(payload));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const matches = result?.matches ?? (Array.isArray(result) ? result : []);

  return (
    <div className="card">
      <div className="card-header">
        <h3>Sanctions Screening</h3>
        <span className="timing">OFAC + OpenSanctions</span>
      </div>
      <div className="card-body">
        <form className="controls inline-form" onSubmit={run}>
          {["name", "dob", "nationality"].map((field) => (
            <label key={field} className="field">
              <span className="field-label">{field}</span>
              <input
                value={form[field]}
                onChange={(e) => setForm({ ...form, [field]: e.target.value })}
                placeholder={field === "dob" ? "1975 or 1975-03-15" : ""}
              />
            </label>
          ))}
          <button type="submit" disabled={busy || !form.name}>
            {busy ? "Screening…" : "Screen"}
          </button>
        </form>

        {error && <div className="error-box">{error}</div>}
        {result && (
          <>
            <div className="section-label">Matches</div>
            <MatchTable matches={matches} />
          </>
        )}
      </div>
    </div>
  );
}

function AdverseMediaPanel() {
  const [articles, setArticles] = useState([]);
  const [selected, setSelected] = useState("");
  const [entityId, setEntityId] = useState("CUST-2041");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listArticles()
      .then((data) => {
        const list = data.articles || data || [];
        setArticles(list);
        const first = list[0];
        setSelected(typeof first === "string" ? first : first?.name || "");
      })
      .catch((err) => setError(err.message));
  }, []);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await analyzeArticle(entityId, selected));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const injected = result?.injection_attempt_detected;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Adverse Media</h3>
        <span className="timing">prompt-injection defended</span>
      </div>
      <div className="card-body">
        <div className="controls inline-form">
          <label className="field">
            <span className="field-label">entity id</span>
            <input value={entityId} onChange={(e) => setEntityId(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">article</span>
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              {articles.map((a) => {
                const name = typeof a === "string" ? a : a.name;
                return (
                  <option key={name} value={name}>
                    {name}
                  </option>
                );
              })}
            </select>
          </label>
          <button onClick={run} disabled={busy || !selected}>
            {busy ? "Analyzing…" : "Analyze"}
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}
        {result && (
          <>
            <div className={injected ? "callout callout-danger" : "callout callout-success"}>
              {injected ? (
                <>
                  <strong>Prompt injection detected.</strong> {result.injection_details}
                </>
              ) : (
                "No prompt injection detected in this article."
              )}
            </div>
            <div className="section-label">
              Extracted claims ({result.extracted_claims?.length ?? 0})
            </div>
            {result.extracted_claims?.length ? (
              <table className="evidence-table">
                <thead>
                  <tr>
                    <th>Claim</th>
                    <th>Supported</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {result.extracted_claims.map((c, i) => (
                    <tr key={i}>
                      <td>{c.claim}</td>
                      <td>
                        <span className={c.supported ? "badge badge-success" : "badge badge-warning"}>
                          {String(c.supported)}
                        </span>
                      </td>
                      <td>{typeof c.confidence === "number" ? c.confidence.toFixed(2) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No claims extracted.</p>
            )}
            <p className="muted">Evidence: {result.evidence_id}</p>
          </>
        )}
      </div>
    </div>
  );
}

// /ubo/structures returns {name, nodes, edges, roots[]}; /ubo/trace takes
// {structure, root_entity_id} and answers {nodes_traversed, findings[]} where each
// finding carries the ownership_path that reached a sanctioned owner.
function UboPanel() {
  const [structures, setStructures] = useState([]);
  const [structure, setStructure] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listUboStructures()
      .then((data) => {
        const list = data.structures || [];
        setStructures(list);
        setStructure(list[0]?.name || "");
      })
      .catch((err) => setError(err.message));
  }, []);

  const current = structures.find((s) => s.name === structure);
  const rootId = current?.roots?.[0] || "";

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await traceUbo({ structure, root_entity_id: rootId }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>UBO Ownership Trace</h3>
        <span className="timing">finds owners hidden behind layers</span>
      </div>
      <div className="card-body">
        <div className="controls inline-form">
          <label className="field">
            <span className="field-label">structure</span>
            <select value={structure} onChange={(e) => setStructure(e.target.value)}>
              {structures.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name} ({s.nodes} nodes)
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">root entity</span>
            <input value={rootId} readOnly />
          </label>
          <button onClick={run} disabled={busy || !structure}>
            {busy ? "Tracing…" : "Trace ownership"}
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}
        {result && (
          <>
            <p className="muted">
              Traversed {result.nodes_traversed} node(s) from {result.root_entity_id} —{" "}
              {result.findings?.length || 0} sanctioned owner(s) found.
            </p>
            {result.findings?.length ? (
              result.findings.map((f, i) => (
                <div key={i} className="finding-block">
                  <div className="section-label">Ownership path to {f.node}</div>
                  <div className="chain">
                    {(f.ownership_path || []).map((hop, j, arr) => (
                      <span key={j} className="chain-hop">
                        {hop}
                        {j < arr.length - 1 && <span className="chain-arrow">→</span>}
                      </span>
                    ))}
                  </div>
                  <div className="section-label">Match</div>
                  <MatchTable matches={[f.match]} />
                </div>
              ))
            ) : (
              <p className="muted">No sanctioned owner found in this structure.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ScreeningView() {
  return (
    <div className="stack">
      <ScreenPanel />
      <AdverseMediaPanel />
      <UboPanel />
    </div>
  );
}
