"""Offline regression for the disposable V2-E1 visual acceptance harness."""

from __future__ import annotations

import pytest

from scripts.knowledge_v2_e1_visual import run_offline_e1_rehearsal


@pytest.mark.asyncio
async def test_offline_e1_visual_rehearsal_is_one_request_and_cleans_up() -> None:
    result = await run_offline_e1_rehearsal()

    assert result.visual_job_status == "succeeded"
    assert result.provider_request_count == 1
    assert result.provider == "siliconflow"
    assert result.model == "Qwen/Qwen3.6-27B"
    assert result.visual_job_token_budget == 3600
    assert result.audit_status == "succeeded"
    assert result.audit_total_tokens == 220
    assert result.audit_accounted_tokens == 220
    assert result.result_count == 1
    assert result.temporary_artifacts_cleaned is True
