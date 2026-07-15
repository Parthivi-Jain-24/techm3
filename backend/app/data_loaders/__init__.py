"""Data-loader package — re-exports the public API from each sub-module."""

from app.data_loaders.kyc_loader import get_client_profile, list_all_client_ids
from app.data_loaders.transaction_loader import get_client_transactions, get_accounts_for_client
from app.data_loaders.sanctions_loader import get_sanctions_matches
from app.data_loaders.gdpr_loader import get_gdpr_article, get_gdpr_article_by_id
from app.data_loaders.adverse_media_loader import get_adverse_media

__all__ = [
    "get_client_profile",
    "list_all_client_ids",
    "get_client_transactions",
    "get_accounts_for_client",
    "get_sanctions_matches",
    "get_gdpr_article",
    "get_gdpr_article_by_id",
    "get_adverse_media",
]
