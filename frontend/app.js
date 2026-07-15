const { createElement: h, useEffect, useMemo, useState } = React;
const root = ReactDOM.createRoot(document.getElementById("root"));

const roles = [
  { value: "compliance", label: "Compliance Officer" },
  { value: "investigator", label: "Investigator" },
  { value: "risk", label: "Risk Analyst" },
  { value: "auditor", label: "Auditor" },
  { value: "admin", label: "Admin" },
];
const views = ["Overview", "Case", "Report", "Audit"];

function request(path, options = {}) {
  return fetch(path, { headers: { "Content-Type": "application/json" }, ...options }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  });
}

function App() {
  const [role, setRole] = useState("compliance");
  const [view, setView] = useState("Overview");
  const [tab, setTab] = useState("profile");
  const [summary, setSummary] = useState(null);
  const [cases, setCases] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [caseDetail, setCaseDetail] = useState(null);
  const [audit, setAudit] = useState([]);
  const [query, setQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [news, setNews] = useState(null);

  function showToast(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }

  function refresh() {
    Promise.all([request("/governance/summary"), request(`/governance/cases?role=${role}`), request("/governance/audit")])
      .then(([summaryData, caseRows, auditRows]) => {
        setSummary(summaryData);
        setCases(caseRows);
        setAudit(auditRows);
        if (!selectedId && caseRows[0]) setSelectedId(caseRows[0].customer_id);
      })
      .catch((error) => showToast(error.message));
  }

  useEffect(() => { refresh(); }, [role]);
  useEffect(() => {
    if (!selectedId) return;
    request(`/governance/cases/${selectedId}?role=${role}`).then(setCaseDetail).catch((error) => showToast(error.message));
  }, [selectedId, role]);

  const filteredCases = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return cases.filter((item) => {
      const matchesRisk = riskFilter === "ALL" || item.risk_level === riskFilter;
      const matchesQuery = !needle || `${item.name} ${item.customer_id} ${item.case_id}`.toLowerCase().includes(needle);
      return matchesRisk && matchesQuery;
    });
  }, [cases, query, riskFilter]);

  const actor = roles.find((item) => item.value === role)?.label || "Reviewer";

  async function submitReview(action, reason) {
    await request(`/governance/cases/${selectedId}/review`, { method: "POST", body: JSON.stringify({ action, reason, actor }) });
    setReviewOpen(false);
    showToast("Review decision recorded with audit hash");
    refresh();
    request(`/governance/cases/${selectedId}?role=${role}`).then(setCaseDetail);
  }

  async function signSar(reason) {
    await request(`/governance/cases/${selectedId}/sar-signoff`, { method: "POST", body: JSON.stringify({ reason, actor }) });
    showToast("Report sign-off recorded");
    refresh();
    request(`/governance/cases/${selectedId}?role=${role}`).then(setCaseDetail);
  }

  async function fetchNews() {
    if (!selectedId) return;
    setNews({ loading: true });
    try {
      const result = await request(`/governance/cases/${selectedId}/live-news`);
      setNews(result);
      showToast(result.message || "Live news check complete");
      request("/governance/audit").then(setAudit);
    } catch (error) {
      setNews({ articles: [], message: error.message });
      showToast(error.message);
    }
  }

  return h("div", { className: "app-shell" },
    h(Sidebar, { role, setRole, view, setView }),
    h("main", { className: "main" },
      h(Header, { role: actor, onRefresh: refresh, onReview: () => setReviewOpen(true) }),
      h(Metrics, { summary }),
      h("section", { className: "workspace" },
        h(CaseQueue, { cases: filteredCases, selectedId, setSelectedId, query, setQuery, riskFilter, setRiskFilter }),
        h("div", { className: "detail-surface" },
          view === "Overview" && h(OverviewView, { caseDetail, news, fetchNews }),
          view === "Case" && h(CaseView, { caseDetail, tab, setTab }),
          view === "Report" && h(ReportView, { caseDetail, onSign: signSar }),
          view === "Audit" && h(AuditView, { audit }),
        ),
      ),
    ),
    reviewOpen && h(ReviewDialog, { onClose: () => setReviewOpen(false), onSubmit: submitReview }),
    h("div", { className: `toast ${toast ? "show" : ""}`, role: "status" }, toast),
  );
}

function Sidebar({ role, setRole, view, setView }) {
  return h("aside", { className: "sidebar" },
    h("div", { className: "brand" }, h("div", { className: "brand-mark" }, "K"), h("div", null, h("strong", null, "KYC Command"), h("span", null, "Continuous risk operations"))),
    h("nav", { className: "nav-list" }, views.map((item) => h("button", { key: item, className: `nav-item ${view === item ? "active" : ""}`, onClick: () => setView(item), type: "button" }, h("span", { className: "nav-icon" }, iconFor(item)), h("span", null, item)))),
    h("div", { className: "role-panel" }, h("label", { htmlFor: "role" }, "Access role"), h("select", { id: "role", value: role, onChange: (event) => setRole(event.target.value) }, roles.map((item) => h("option", { key: item.value, value: item.value }, item.label))))
  );
}

function Header({ role, onRefresh, onReview }) {
  return h("header", { className: "topbar" },
    h("div", null, h("p", { className: "eyebrow" }, "Continuous KYC operations"), h("h1", null, "Customer Risk Review Workspace"), h("span", { className: "subtle" }, `Signed in as ${role}`)),
    h("div", { className: "topbar-actions" }, h("button", { className: "icon-button", title: "Refresh", onClick: onRefresh }, "↻"), h("button", { className: "primary-button", onClick: onReview }, "Record Decision"))
  );
}

function Metrics({ summary }) {
  const cards = [
    ["Customers monitored", summary?.accounts_monitored, summary?.data_source || "Local data", ""],
    ["Transactions analyzed", summary?.transactions_loaded, `${formatNumber(summary?.saml_dataset_rows || 0)} SAML-D rows available`, ""],
    ["Critical / High", `${summary?.critical_risk ?? "--"} / ${summary?.high_risk ?? "--"}`, `${summary?.pending_reviews ?? "--"} cases need review`, "danger"],
    ["False positives reduced", summary?.false_positives_prevented, "Low-risk profiles filtered from queue", "success"],
  ];
  return h("section", { className: "metrics-grid" }, cards.map(([label, value, detail, tone]) => h("article", { className: `metric ${tone}`, key: label }, h("span", null, label), h("strong", null, formatNumber(value ?? "--")), h("small", null, detail))));
}

function CaseQueue({ cases, selectedId, setSelectedId, query, setQuery, riskFilter, setRiskFilter }) {
  return h("aside", { className: "case-list" },
    h("div", { className: "section-head" }, h("h2", null, "Customer Queue"), h("span", { className: "status-pill" }, `${cases.length} shown`)),
    h("input", { className: "search-input", value: query, onChange: (event) => setQuery(event.target.value), placeholder: "Search customer or case" }),
    h("div", { className: "segmented" }, ["ALL", "CRITICAL", "HIGH", "MEDIUM"].map((item) => h("button", { key: item, className: riskFilter === item ? "active" : "", onClick: () => setRiskFilter(item), type: "button" }, item))),
    h("div", { className: "queue-scroll" }, cases.map((item) => h("button", { className: `case-row ${selectedId === item.customer_id ? "active" : ""}`, key: item.case_id, onClick: () => setSelectedId(item.customer_id) },
      h("span", { className: `risk-dot ${item.risk_level.toLowerCase()}` }),
      h("strong", null, item.name),
      h("span", null, `${item.case_id} · Score ${item.risk_score} · ${(item.confidence_score * 100).toFixed(0)}% confidence`),
      h("small", null, item.summary),
    )))
  );
}

function OverviewView({ caseDetail, news, fetchNews }) {
  if (!caseDetail) return h(Loading);
  const a = caseDetail.assessment;
  return h("section", null,
    h("div", { className: "case-header" }, h("div", null, h("p", { className: "eyebrow" }, caseDetail.case_id), h("h2", null, caseDetail.name), h("p", null, `${caseDetail.assigned_team} · ${caseDetail.status}`)), h(RiskGauge, { assessment: a })),
    h("div", { className: "split" },
      h("div", null, h("div", { className: "section-head" }, h("h3", null, "Risk composition"), h("span", { className: "status-pill" }, `Base ${a.base_score}`)), h(Breakdown, { assessment: a })),
      h("div", null, h("div", { className: "section-head" }, h("h3", null, "Priority drivers"), h("button", { className: "small-button", onClick: fetchNews }, "Check live news")), h("ul", { className: "reason-list" }, a.top_reasons.map((reason) => h("li", { key: reason }, reason))), h(NewsPanel, { news }))
    )
  );
}

function CaseView({ caseDetail, tab, setTab }) {
  if (!caseDetail) return h(Loading);
  return h("section", null,
    h("div", { className: "tabs" }, ["profile", "timeline", "transactions", "evidence", "reasoning"].map((item) => h("button", { className: `tab ${tab === item ? "active" : ""}`, onClick: () => setTab(item), key: item }, titleCase(item)))),
    tab === "profile" && h(Profile, { caseDetail }),
    tab === "timeline" && h(Timeline, { rows: caseDetail.timeline }),
    tab === "transactions" && h(Transactions, { transactions: caseDetail.transactions }),
    tab === "evidence" && h(Evidence, { evidence: caseDetail.evidence }),
    tab === "reasoning" && h(Reasoning, { assessment: caseDetail.assessment })
  );
}

function Profile({ caseDetail }) {
  const p = caseDetail.profile;
  const rows = [["Client type", p.client_type], ["Country", p.country], ["Sector", p.sector], ["Sector risk", p.sector_risk], ["PEP flag", p.pep_flag ? "Yes" : "No"], ["Sanctions flag", p.sanctions_flag ? "Yes" : "No"], ["Ownership opacity", Number(p.ownership_opacity_score).toFixed(2)], ["Linked party", p.beneficial_owner]];
  return h("dl", { className: "info-grid" }, rows.map(([k, v]) => h("div", { key: k }, h("dt", null, k), h("dd", { className: String(v).startsWith("Restricted") ? "masked" : "" }, String(v)))));
}

function Timeline({ rows }) { return h("ol", { className: "timeline" }, rows.map((item) => h("li", { key: `${item.date}-${item.score}` }, h("strong", null, `${item.date} · Risk ${item.score}`), h("span", null, item.event)))); }
function Transactions({ transactions }) { return h("div", null, h("div", { className: "mini-metrics" }, [["Count", transactions.count], ["Total", currency(transactions.total_amount)], ["Average", currency(transactions.avg_amount)], ["Typology hits", transactions.typology_hits]].map(([k, v]) => h("div", { key: k }, h("span", null, k), h("strong", null, v)))), h("div", { className: "table" }, transactions.sample_transactions.map((row) => h("div", { className: "table-row", key: row.transaction_id }, h("span", null, row.transaction_id), h("span", null, currency(row.amount)), h("span", null, row.transaction_type), h("span", null, row.counterparty_country))))); }
function Evidence({ evidence }) { return h("div", { className: "evidence-grid" }, evidence.map((item) => h("article", { className: "evidence-item", key: item.id }, h("strong", null, item.id), h("span", null, `${item.source} · ${(item.confidence * 100).toFixed(0)}% confidence`), h("p", null, item.claim)))); }
function Reasoning({ assessment }) { const factors = assessment.component_details.flatMap((c) => c.sub_factors.map((f) => ({ ...f, component: c.name }))); return h("div", { className: "subfactor-table" }, factors.map((f) => h("article", { className: "subfactor-row", key: `${f.component}-${f.name}` }, h("strong", null, `${f.contribution.toFixed(1)} pts · ${f.reason}`), h("span", null, `${labelFor(f.component)} · max ${f.max_points} · ${(f.confidence * 100).toFixed(0)}% confidence · ${f.evidence_ids.join(", ") || "No evidence ID"}`)))); }

function ReportView({ caseDetail, onSign }) { const [reason, setReason] = useState(""); if (!caseDetail) return h(Loading); const a = caseDetail.assessment; return h("section", null, h("div", { className: "section-head" }, h("h2", null, "Review Report Draft"), h("span", { className: "status-pill warning" }, "Human approval required")), h("div", { className: "sar-draft" }, h("p", null, h("strong", null, "Subject: "), caseDetail.sar_draft.subject), h("p", null, h("strong", null, "Activity summary: "), caseDetail.sar_draft.activity), h("p", null, h("strong", null, "Score movement: "), `${a.timeline_event.previous_score} to ${a.risk_score}; confidence ${(a.confidence_score * 100).toFixed(0)}%.`), h("p", null, h("strong", null, "Evidence: "), a.evidence_ids.join(", ")), h("p", null, h("strong", null, "Recommendation: "), caseDetail.sar_draft.recommendation)), h("div", { className: "review-panel" }, h("label", null, "Approval note"), h("textarea", { rows: 4, value: reason, onChange: (e) => setReason(e.target.value), placeholder: "Required before sign-off" }), h("button", { className: "primary-button", onClick: () => reason.trim() && onSign(reason) }, "Sign Off Report"))); }
function AuditView({ audit }) { return h("section", null, h("div", { className: "section-head" }, h("h2", null, "Audit Trail"), h("span", { className: "status-pill" }, "Tamper-evident")), h("div", { className: "audit-log" }, audit.map((item) => h("article", { className: "audit-item", key: item.event_id }, h("strong", null, `${item.event_id} · ${item.action}`), h("span", null, `${item.actor} · ${new Date(item.timestamp).toLocaleString()}`), h("p", null, item.reason), h("code", null, `${item.hash.slice(0, 18)}... <- ${item.previous_hash.slice(0, 12)}`))))); }
function NewsPanel({ news }) { if (!news) return h("div", { className: "note" }, "Live adverse-media checks are optional and are logged in audit history."); if (news.loading) return h("div", { className: "note" }, "Checking live news sources..."); return h("div", { className: "news-panel" }, h("strong", null, news.message), (news.articles || []).slice(0, 3).map((item) => h("a", { key: item.url || item.title, href: item.url, target: "_blank", rel: "noreferrer" }, item.title || "News article"))); }
function Breakdown({ assessment }) { return h("div", { className: "breakdown" }, Object.entries(assessment.breakdown).map(([key, value]) => { const max = assessment.component_details.find((item) => item.name === key)?.max_score || 100; return h("div", { className: "bar-row", key }, h("div", { className: "bar-label" }, h("span", null, labelFor(key)), h("strong", null, `${Number(value).toFixed(1)} / ${max}`)), h("div", { className: "bar-track" }, h("div", { className: "bar-fill", style: { width: `${Math.min(100, (value / max) * 100)}%` } }))); })); }
function RiskGauge({ assessment }) { const score = assessment.risk_score || 0; return h("div", { className: "risk-gauge", style: { background: `conic-gradient(var(--danger) 0 ${score}%, var(--surface-2) ${score}% 100%)` } }, h("strong", null, score), h("span", null, assessment.risk_level)); }
function ReviewDialog({ onClose, onSubmit }) { const [action, setAction] = useState("Approve Escalation"); const [reason, setReason] = useState(""); return h("div", { className: "modal-backdrop" }, h("div", { className: "dialog-body", role: "dialog", "aria-modal": "true" }, h("div", { className: "section-head" }, h("h2", null, "Record Decision"), h("button", { className: "close-button", onClick: onClose }, "×")), h("label", null, "Decision"), h("select", { value: action, onChange: (e) => setAction(e.target.value) }, ["Approve Escalation", "Request More Investigation", "Mark False Positive", "Reject Recommendation"].map((x) => h("option", { key: x }, x))), h("label", null, "Reason"), h("textarea", { rows: 5, value: reason, onChange: (e) => setReason(e.target.value), placeholder: "Required for audit trail" }), h("div", { className: "dialog-actions" }, h("button", { onClick: onClose }, "Cancel"), h("button", { className: "primary-button", onClick: () => reason.trim() && onSubmit(action, reason) }, "Submit")))); }
function Loading() { return h("div", { className: "loading" }, "Loading customer risk workspace..."); }
function iconFor(item) { return { Overview: "⌂", Case: "◫", Report: "◇", Audit: "#" }[item]; }
function formatNumber(value) { return typeof value === "number" ? value.toLocaleString() : value; }
function currency(value) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function titleCase(value) { return value.replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function labelFor(key) { return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }

root.render(h(App));