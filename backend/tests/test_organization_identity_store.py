from datetime import timedelta

import pytest

from app.models import VerifiedOrganizationIdentity, utcnow
from app.providers.ror import ROROrganization
from app.research.organization_identity_store import (
    load_recent_identity,
    persist_openalex_mapping,
    persist_verified_identity,
)


def _ror_profile(*, ror_id="https://ror.org/03yrm5c26", modified="2026-10-20"):
    return ROROrganization(
        ror_id=ror_id,
        canonical_name="Unseeded Climate Research Institute",
        aliases=("UCRI",),
        organization_types=("nonprofit",),
        domains=("ucri.example",),
        official_urls=("https://ucri.example",),
        country_code="IN",
        record_status="active",
        last_modified=modified,
        retrieved_at=utcnow().isoformat(),
        api_url="https://api.ror.org/v2/organizations/03yrm5c26",
    )


def test_recent_verified_identity_and_exact_openalex_mapping_are_reusable(client):
    with client.db_sessions() as db:
        persist_verified_identity(db, _ror_profile())
        assert persist_openalex_mapping(db, "https://ror.org/03yrm5c26", "I987")
        db.commit()

    with client.db_sessions() as db:
        cached = load_recent_identity(db, "https://ror.org/03yrm5c26")
        assert cached is not None
        assert cached.profile.canonical_name == "Unseeded Climate Research Institute"
        assert cached.profile.domains == ("ucri.example",)
        assert cached.openalex_institution_id == "I987"


def test_expired_or_malformed_identity_is_never_reused(client):
    with client.db_sessions() as db:
        persist_verified_identity(db, _ror_profile())
        identity = db.get(VerifiedOrganizationIdentity, "https://ror.org/03yrm5c26")
        identity.verified_at = utcnow() - timedelta(days=91)
        db.commit()

    with client.db_sessions() as db:
        assert load_recent_identity(db, "https://ror.org/03yrm5c26") is None
        assert load_recent_identity(db, "https://ror.org/not-a-ror-id") is None


def test_unverified_ids_cannot_enter_the_persistent_identity_store(client):
    with client.db_sessions() as db:
        with pytest.raises(ValueError, match="ROR identity is invalid"):
            persist_verified_identity(
                db,
                _ror_profile(
                    ror_id="https://attacker.example/id",
                ),
            )
        assert not persist_openalex_mapping(db, "https://ror.org/03yrm5c26", "not-an-openalex-id")
