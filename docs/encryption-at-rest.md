# Encryption at Rest — AES-256-GCM (Phase 6)

## 1. Scope

Real authenticated encryption for **sensitive application-generated artifacts**
before they are persisted to disk. This is an **engineering control for a
specific storage boundary**, not a claim that every byte on every disk is
encrypted — see §5.

## 2–3. Algorithm

**AES-256-GCM**, via the maintained, vetted primitive
`cryptography.hazmat.primitives.ciphers.aead.AESGCM` (Python `cryptography`
package). No hand-rolled AES/GCM, no manual tag splitting — `AESGCM.encrypt()`
returns ciphertext with the authentication tag appended, and `AESGCM.decrypt()`
verifies it as one atomic operation. AES-GCM is authenticated (confidentiality
+ integrity in one primitive), avoiding the classic "encrypt-then-forget-MAC"
mistake of unauthenticated modes like raw CBC.

## 4. What IS encrypted

Explicit, opt-in encrypted export of **application-generated normalized KYC
artifacts** (`NormalizedKYCEntity` batches) via
`export_encrypted_kyc_artifact()` → `EncryptedArtifactStore` →
`data/encrypted/`. Nothing is encrypted automatically on import or as a side
effect of ingestion.

## 5. What is NOT claimed to be encrypted

- The **raw challenge dataset** under `data/raw/` — an input fixture, never
  modified, never encrypted by this phase.
- Any **database** — none exists yet (no SQLAlchemy/Postgres in this project).
  "Database encryption" is not implemented because there is no database.
- **Disk/cloud-provider encryption** — not configured or claimed here;
  production infrastructure may additionally provide this.
- **Data in transit** — TLS 1.3 is Phase 7, not this phase.

## 6–7. Key length & encoding

Exactly **32 bytes (256 bits)** after Base64 decoding. 16-byte (AES-128) and
24-byte (AES-192) keys, malformed Base64, and empty keys are all rejected
(`InvalidEncryptionKeyError`) — never silently truncated, padded, or derived
from a password without an explicit KDF (none is implemented; a human password
is never used directly as a key).

## 8–10. Key-provider architecture

```
EncryptionService → SecretProvider.get_secret(key_id) → EnvironmentSecretProvider (SECRETS_PROVIDER=environment, default)
                                                        → VaultSecretProvider (SECRETS_PROVIDER=vault — implemented, Phase 8)
```

Reuses the **exact** Phase 5 `SecretProvider` boundary
(`app/secrets/provider.py`) — no duplicate secret system. `key_id` (e.g.
`kyc-data-key-v1`) doubles as the non-secret envelope reference **and** the
logical secret name resolved through the provider — the same pattern Phase 5
used for `auth_secret_name`.

**Update (Phase 8 — implemented, not just planned):** `key_id` can now be
resolved through a real `VaultSecretProvider`
(`app/secrets/vault_provider.py`, HashiCorp Vault KV v2) by setting
`SECRETS_PROVIDER=vault`. As predicted, swapping providers required **zero**
changes to `EncryptionService`, `EncryptedArtifactStore`, `resolve_key()`, the
AES-256-GCM algorithm, nonce generation, or the envelope format — proven by
`backend/tests/test_secrets_encryption_integration.py` (a synthetic 32-byte
key served by a fake Vault client encrypts and decrypts identically to the
environment-provider path). See docs/secrets-vault.md for the full Vault
architecture, authentication, and local demonstration.

## 11. Environment provider for local development

`EnvironmentSecretProvider` resolves `key_id` from `os.environ` (or an
injected in-memory mapping in tests). Set an environment variable / `.env`
line **named exactly like `ENCRYPTION_KEY_ID`'s value** (default
`kyc-data-key-v1`) to a base64-encoded 32-byte key. See §27 for generation.

## 12. Key identifiers

`key_id` is metadata, not a secret. It is stored in the envelope so a future
key-rotation process can identify which key encrypted an artifact (§26).

## 13–14. Nonce

Fresh **96-bit (12-byte)** `os.urandom(12)` nonce generated **internally** for
every single encryption call — callers cannot supply one, so there is no static
or client-controlled nonce path. The nonce is not secret; it's stored
Base64-encoded alongside the ciphertext in the envelope.

## 15. Authenticated encryption

AES-GCM authenticates both the ciphertext and the AAD (below). Any bit-flip in
the ciphertext, nonce, or AAD causes `AESGCM.decrypt()` to raise
`InvalidTag`, mapped to `DecryptionFailedError` — **no partial plaintext is
ever returned**.

## 16. AAD usage

Centralized in `build_aad(version, algorithm, artifact_type)`
(`app/encryption/models.py`), used identically on encrypt and decrypt. Binds
the envelope's version/algorithm/content-type so tampering with those fields
is detected, without embedding anything secret or unstable.

## 17. Encrypted-envelope format

```json
{
  "version": 1,
  "algorithm": "AES-256-GCM",
  "key_id": "kyc-data-key-v1",
  "artifact_type": "normalized_kyc_entities",
  "nonce": "<base64, 12 bytes>",
  "ciphertext": "<base64, includes GCM tag>",
  "created_at": "2026-...Z"
}
```

No plaintext, no key material — ever.

## 18. Envelope versioning

`version=1` today; unsupported versions raise
`UnsupportedEnvelopeVersionError` before any crypto runs. No migration
framework — a future version bump is a small, explicit addition.

## 19. Serialization

Structured content is serialized as **UTF-8 JSON** (`json.dumps`) before
encryption — never `pickle`, never `eval`. Decryption reverses this and (for
the KYC integration) the resulting dicts can be re-validated through
`NormalizedKYCEntity`.

## 20. Approved encrypted-artifact directory

`data/encrypted/` (configurable via `ENCRYPTED_ARTIFACT_DIR`), separate from
`data/raw/` (source datasets, never modified) and `data/processed/` (Phase 2's
plaintext dev export). Git-ignored.

## 21. Path safety

`resolve_artifact_path()` mirrors the Phase 2 `resolve_kyc_path` pattern:
rejects absolute paths, `..` traversal, and symlink escapes; every write/read
must resolve inside the approved directory.

## 22. Atomic writes

Encrypted JSON is written to a temp file **in the same directory** (so the
final `os.replace` is an atomic same-filesystem rename), `fsync`'d, then
atomically replacing the target. On any failure the temp file is cleaned up —
no partially-written final artifact is ever left, and the original source
dataset is never overwritten.

## 23. Plaintext temp-file avoidance

Plaintext exists only in memory. It is JSON-serialized, encrypted, and only
the encrypted envelope bytes touch disk — never a plaintext temp file that is
then encrypted and deleted.

## 24. Wrong-key behavior

Decrypting with the wrong key raises `DecryptionFailedError` (from GCM's
`InvalidTag`) — the exact same exception as tampering, so callers cannot
distinguish "wrong key" from "corrupted/tampered data" from the error alone.
No key material, ciphertext, or cryptographic internals are exposed.

## 25. Tamper detection

Proven by tests: flipping a ciphertext byte, a nonce byte, or the
`artifact_type` (AAD) all cause decryption to fail with no plaintext returned.

## 26. Logging safety

The encryption module performs **no logging of its own** (no key, plaintext,
or decrypted-content logging exists to accidentally trigger). Tests assert the
literal key material and a synthetic PII marker never appear in captured log
output across encrypt/decrypt operations. **Update (Phase 9 — implemented):**
`EncryptionService.encrypt_bytes`/`decrypt_bytes` now emit structured audit
events (`app.audit`, not the encryption module's own logging) — operation
type, `key_id`, algorithm, artifact identifier, success/failure, a safe error
category on failure — never key material, plaintext, or ciphertext. See
docs/audit-logging.md §14.

## Key-rotation readiness

Not implemented in Phase 6, but the envelope's `key_id` makes it possible:
future rotation = resolve the *old* `key_id` → decrypt → re-encrypt under a
*new* `key_id` → write. Phase 6 does **not** auto-re-encrypt existing
artifacts.

## 27. Generate a local development key

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```
Never commit the output. Set it as an environment variable named exactly like
`ENCRYPTION_KEY_ID`'s value (default `kyc-data-key-v1`).

## 28–29. Tests & verification

```bash
cd backend
python -m pytest                              # full suite, no real keys needed
python -m app.encryption.jobs.verify_encryption  # synthetic demo: round-trip,
                                                  # fresh-nonce, tamper, wrong-key
```
The verify job uses an in-memory random key generated for that run only —
never printed, never persisted, never a real KYC record.

## Privacy integration

Encryption and Phase 3 privacy solve different problems: encryption protects
*persisted* content from *direct storage exposure*; masking/minimization
control *what a consumer is shown*. Decrypting an artifact does **not** imply
it is safe to return as-is — the flow remains
`Authorization → Decryption (where required) → Privacy/minimization → Consumer-safe representation`.
No public decryption endpoint exists (see §30).

## 30. Decryption exposure

**No public `/decrypt` endpoint was added.** The service is an internal
application component, demonstrated via automated tests and the local
`verify_encryption` job — not a network-reachable decryption oracle.

## Future database field encryption (not implemented)

No database exists yet. If/when one is added, `EncryptionService.encrypt_bytes`
/`decrypt_bytes` could protect selected sensitive columns before persistence
(encrypt-then-store, decrypt-after-read) — this is a documented future option,
not implemented now.

## 31. Current limitations

- Single active key per `key_id`; no automatic rotation/re-encryption.
- Environment-backed key resolution only (vault is Phase 8).
- No database field encryption (no database exists).
- No TLS (Phase 7); envelope-level audit events now emitted (Phase 9 —
  operation/key_id/algorithm/outcome only, see docs/audit-logging.md §14).
- File permission hardening (owner-only) is not enforced cross-platform;
  encryption is the primary control, OS permissions are defense-in-depth.

## Production-hardening requirements

Secrets vault with access policies + audit (Phase 8); key rotation with
re-encryption tooling; TLS 1.3 in transit (Phase 7); forwarding the local
envelope-level audit trail (Phase 9, implemented — see
docs/audit-logging.md) to centralized SIEM/WORM storage; OS/filesystem
permission hardening; disk/cloud-provider encryption as an additional
infrastructure layer (not a substitute for
application-level encryption of sensitive fields).
