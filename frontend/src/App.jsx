// Console shell: navigation across all five workstreams.
//
// Each tab is a feature view that talks to the service owning it (see api.js and
// the proxy map in vite.config.js). Tabs mount lazily -- switching to Screening
// must not make the browser wait on Part 4's minutes-long LLM pipeline.

import { useState } from "react";
import "./App.css";

import AuditView from "./features/audit/AuditView";
import CasesView from "./features/cases/CasesView";
import DashboardView from "./features/dashboard/DashboardView";
import IdentityView from "./features/security/IdentityView";
import InvestigationView from "./features/investigations/InvestigationView";
import ScreeningView from "./features/customers/ScreeningView";

const TABS = [
  { id: "dashboard", label: "Overview", part: "", view: DashboardView },
  { id: "identity", label: "Identity", part: "Part 1", view: IdentityView },
  { id: "screening", label: "Screening", part: "Part 2", view: ScreeningView },
  { id: "cases", label: "Risk & Cases", part: "Part 3+5", view: CasesView },
  { id: "investigation", label: "Investigation", part: "Part 4", view: InvestigationView },
  { id: "audit", label: "Audit Trail", part: "All", view: AuditView },
];

export default function App() {
  const [active, setActive] = useState("dashboard");
  const tab = TABS.find((t) => t.id === active) ?? TABS[0];
  const View = tab.view;

  return (
    <div className="shell">
      <header className="shell-header">
        <div className="brand">
          <span className="brand-mark">KYC</span>
          <div>
            <h1>Continuous KYC Autonomous Auditor</h1>
            <p className="brand-sub">Governance console — screening, risk, investigation, review</p>
          </div>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={t.id === active}
            className={`tab ${t.id === active ? "tab-active" : ""}`}
            onClick={() => setActive(t.id)}
          >
            {t.label}
            {t.part && <span className="tab-part">{t.part}</span>}
          </button>
        ))}
      </nav>

      <main className="shell-body">
        <View onNavigate={setActive} />
      </main>
    </div>
  );
}
