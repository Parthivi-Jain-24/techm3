// Part 1 -- Secure Data & Identity: token issuance and RBAC identity.

import { useState } from "react";
import { login, whoAmI } from "../../api";

export default function IdentityView() {
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("CorrectHorse9!");
  const [token, setToken] = useState(null);
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function doLogin(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMe(null);
    setToken(null);
    try {
      const data = await login(username, password);
      setToken(data.access_token);
      setMe(await whoAmI(data.access_token));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-header">
          <h3>Authentication</h3>
          <span className="timing">OAuth2 password flow · JWT HS256</span>
        </div>
        <div className="card-body">
          <form className="controls inline-form" onSubmit={doLogin}>
            <label className="field">
              <span className="field-label">username</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Get token"}
            </button>
          </form>

          {error && (
            <>
              <div className="error-box">{error}</div>
              <div className="callout callout-info">
                This service is <strong>fail-closed by design</strong>: with no
                <code> JWT_SECRET_KEY </code> it returns 503, and with no seeded user it
                returns 401 — and it audits the failed attempt. Both are the control
                working, not an outage. <code>scripts\dev_up.ps1</code> seeds the dev user.
              </div>
            </>
          )}

          {token && (
            <>
              <div className="callout callout-success">Token issued.</div>
              <div className="section-label">Access token (truncated)</div>
              <pre className="json-dump">{token.slice(0, 72)}…</pre>
            </>
          )}

          {me && (
            <>
              <div className="section-label">Identity (/security/me)</div>
              <pre className="json-dump">{JSON.stringify(me, null, 2)}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
