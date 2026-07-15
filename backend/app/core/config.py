# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# Application settings. Values are sourced from environment variables (and an
# optional local .env file) only — never hardcode secrets here.
#
# Every field has a safe, non-secret default so the application starts in
# Phase 1 WITHOUT requiring any real credentials.

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: backend/app/core/config.py -> parents[3] == project root.
# Used to anchor dataset paths so they do not depend on the process CWD.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # extra="ignore" so unrelated keys in a shared .env (e.g. teammates'
    # NEWS_API_KEY, VITE_API_BASE_URL) never break startup.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application (Phase 1) ---
    app_name: str = "Continuous KYC Autonomous Auditor"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    # --- KYC ingestion (Phase 2) ---
    # Approved directory for raw KYC input files. Files are only ingested when
    # they resolve INSIDE this directory (path-traversal guard). Relative paths
    # are anchored at PROJECT_ROOT.
    kyc_raw_dir: str = "data/raw/kyc"
    # Optional local development artifact directory (git-ignored).
    kyc_processed_dir: str = "data/processed"
    # Maximum accepted KYC input file size. Dataset is ~5-10 MB; 50 MB headroom.
    max_kyc_file_size_mb: int = 50

    # --- Privacy / governance (Phase 3) ---
    # HMAC key for pseudonymizing identifiers in log-safe / external outputs.
    # NEVER hardcode a real value here or in .env.example. Empty default keeps
    # startup working; the pseudonymizer then falls back to a clearly-insecure
    # development key (see app.privacy.masking.pseudonymize). Set a real,
    # secret value via the environment in any non-local deployment.
    pseudonymization_key: str = ""

    @property
    def kyc_raw_path(self) -> Path:
        p = Path(self.kyc_raw_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    @property
    def kyc_processed_path(self) -> Path:
        p = Path(self.kyc_processed_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    # --- Authentication / RBAC (Phase 4) ---
    # HS256 signing secret. NO real value in source or .env.example; supply via
    # environment. Empty default keeps the app (and public health) running, but
    # the token/auth endpoints then return "not configured" instead of issuing
    # tokens. Tests inject a test secret. Future: sourced from a secrets vault.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    # Short-lived access tokens (minutes). Validated > 0 below.
    access_token_expire_minutes: int = 15
    # DEVELOPMENT-ONLY demo identities as a JSON array (never real credentials):
    # [{"username","principal_id","password_hash","principal_type","roles":[...],
    #   "is_active"}]. Empty => no demo users (default-deny). Tests build their
    # own isolated identities and do not use this.
    dev_auth_users: str = ""

    # --- API ingestion (Phase 5) ---
    # Explicit outbound-request timeouts (seconds). No infinite/default timeouts.
    api_connect_timeout_seconds: float = 5.0
    api_read_timeout_seconds: float = 10.0
    api_write_timeout_seconds: float = 5.0
    api_pool_timeout_seconds: float = 5.0
    # Hard cap on bytes read from an upstream response (defends memory + DoS).
    max_api_response_size_mb: float = 10.0
    # Bounded, conservative retry policy for transient upstream failures only.
    api_max_retries: int = 2
    api_retry_backoff_seconds: float = 0.2
    # Server-controlled trusted API sources as a JSON array (never client input;
    # never contains secret values — only logical secret NAMES). Empty => no
    # sources registered (a trigger then returns UNKNOWN_SOURCE). Tests inject
    # their own registry. See app.ingestion.api.models.TrustedApiSourceConfig.
    api_sources_json: str = ""

    @field_validator("access_token_expire_minutes")
    @classmethod
    def _expiry_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("access_token_expire_minutes must be positive")
        return v

    @field_validator(
        "api_connect_timeout_seconds", "api_read_timeout_seconds",
        "api_write_timeout_seconds", "api_pool_timeout_seconds",
        "max_api_response_size_mb", "api_retry_backoff_seconds",
    )
    @classmethod
    def _must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("value must be positive")
        return v

    @field_validator("api_max_retries")
    @classmethod
    def _retries_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("api_max_retries must be >= 0")
        return v

    # --- Encryption at rest (Phase 6) ---
    # Non-secret identifier stored in encrypted envelopes for future key
    # rotation. IMPORTANT: this value is ALSO used as the SecretProvider
    # logical name to resolve the actual key material (same pattern as Phase
    # 5's auth_secret_name) — set an environment variable / .env line with
    # THIS EXACT NAME to a base64-encoded 32 random bytes. Never a real value
    # here or in .env.example.
    encryption_key_id: str = "kyc-data-key-v1"
    # Approved directory for encrypted application-managed artifacts. Writes
    # and reads are only permitted INSIDE this directory (path-traversal
    # guard, same principle as kyc_raw_dir). Git-ignored; separate from
    # data/raw/ (never overwrites source datasets).
    encrypted_artifact_dir: str = "data/encrypted"

    @property
    def encrypted_artifact_path(self) -> Path:
        p = Path(self.encrypted_artifact_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    # --- TLS in transit (Phase 7) ---
    # Strict LOCAL TLS 1.3 secure-demonstration listener. Entirely separate
    # from the ordinary plain-HTTP dev server (uvicorn app.main:app on 8000) —
    # these settings do not affect it. Non-secret paths/port only; the actual
    # private key file itself must never be committed (see .gitignore).
    tls_cert_file: str = "certs/local/dev-cert.pem"
    tls_key_file: str = "certs/local/dev-key.pem"
    tls_port: int = 8443
    # Comma-separated trusted reverse-proxy IP(s)/CIDR allowed to set
    # X-Forwarded-Proto/X-Forwarded-For (passed to uvicorn's forwarded_allow_ips).
    # Empty (default) = trust NO proxy headers — fail-safe. Our direct-Uvicorn
    # TLS demo needs none (scheme is detected natively by terminating TLS
    # in-process). Set ONLY to the exact proxy IP if deployed behind one;
    # NEVER "*".
    trusted_proxy_ips: str = ""

    @property
    def tls_cert_path(self) -> Path:
        p = Path(self.tls_cert_file)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    @property
    def tls_key_path(self) -> Path:
        p = Path(self.tls_key_file)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    # --- Secrets provider selection (Phase 8) ---
    # Explicit allow-list enforced by app.secrets.factory (not here) so the
    # invalid-value error stays a normal, testable SecretProviderError rather
    # than a startup-time pydantic failure. Default "environment" preserves
    # all existing Phase 5/6 local-development behavior unchanged.
    secrets_provider: str = "environment"

    # --- HashiCorp Vault connection (Phase 8) — NON-SECRET config only ---
    # The bootstrap credential (VAULT_TOKEN) is intentionally NOT a Settings
    # field: it is read directly from the process environment inside
    # VaultSecretProvider (see docs/secrets-vault.md — "bootstrap credential
    # problem"). Putting it here would make it just another "ordinary
    # setting", which is exactly what Phase 8 avoids for actual secrets.
    vault_addr: str = ""
    vault_mount_point: str = "secret"
    vault_secret_path: str = "continuous-kyc"
    vault_auth_method: str = "token"

    # --- Audit logging (Phase 9) --- NON-SECRET configuration only. ---
    # Master on/off switch. When false, the audit service uses a no-op sink
    # (events are still constructed/sanitized in-process for callers that
    # inspect the return value in tests, but nothing is persisted).
    audit_enabled: bool = True
    # Sink selection: "jsonl" (default, local hash-chained file) | "memory"
    # (process-local, test/demo use) | "null" (explicit no-op). Validated in
    # app.audit.service (not here) -- same precedent as secrets_provider
    # above: an invalid value becomes a normal, testable error at the point
    # of use rather than a startup-time pydantic failure.
    audit_sink: str = "jsonl"
    # Server-controlled only -- never influenced by request input. Relative
    # paths are anchored at PROJECT_ROOT and MUST resolve inside
    # backend/var/audit/ (see app.audit.storage.paths); anything else falls
    # back to the approved default rather than writing elsewhere.
    audit_log_path: str = "backend/var/audit/audit.jsonl"

    # --- Placeholders for later phases (documented in .env.example) ---
    # Present so teammates share one Settings object; NOT used or required yet.
    database_url: str = ""
    llm_provider: str = ""
    llm_api_key: str = ""


settings = Settings()
