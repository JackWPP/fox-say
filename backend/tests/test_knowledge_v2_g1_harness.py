"""No-network coverage for the disposable G1 automatic-chain rehearsal."""

from __future__ import annotations

import pytest

from scripts.knowledge_v2_g1_auto_linear import run_offline_g1_rehearsal


@pytest.mark.asyncio
async def test_offline_g1_rehearsal_uses_one_audited_request_and_finishes_automatic_chain() -> None:
    result = await run_offline_g1_rehearsal()

    assert result.outline_job_status == "succeeded"
    assert result.semantic_job_status == "succeeded"
    assert result.term_job_status == "succeeded"
    assert result.provider_request_count == 1
    assert result.semantic_job_token_budget == 4_000
    assert result.audit_status == "succeeded"
    assert result.audit_reserved_tokens <= 4_000
    assert result.audit_accounted_tokens == 300
    assert result.semantic_atom_count == 1
    assert result.term_count == 1
    assert result.temporary_db_cleaned is True
