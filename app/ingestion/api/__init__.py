"""Secure OUTBOUND API ingestion (Phase 5).

Our backend calls explicitly-configured trusted external KYC sources. There is
no generic URL fetcher: callers select a ``source_id`` only; the destination,
auth, TLS, redirect, and mapping are all server-controlled. See
docs/api-ingestion.md.
"""
