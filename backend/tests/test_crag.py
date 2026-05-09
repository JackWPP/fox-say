from unittest.mock import AsyncMock, patch

import pytest

from app.services.crag import ask
from app.services.retrieval import retrieve


def _make_search_result(score: float, text: str = "sample text", file_name: str = "notes.pdf", index: int = 0):
    return {
        "score": score,
        "payload": {
            "text": text,
            "file_name": file_name,
            "index": index,
        },
    }


class TestRetrievalThresholds:
    @patch("app.services.retrieval._qdrant")
    @patch("app.services.retrieval.embed_texts")
    def test_grounded_score(self, mock_embed, mock_qdrant):
        mock_embed.return_value = [[0.1] * 1536]
        mock_qdrant.search.return_value = [_make_search_result(0.85)]
        result = retrieve("course-1", "什么是微积分")
        assert result["confidence"] == "grounded"
        assert result["top_score"] == 0.85

    @patch("app.services.retrieval._qdrant")
    @patch("app.services.retrieval.embed_texts")
    def test_ambiguous_score(self, mock_embed, mock_qdrant):
        mock_embed.return_value = [[0.1] * 1536]
        mock_qdrant.search.return_value = [_make_search_result(0.60)]
        result = retrieve("course-1", "什么是微积分")
        assert result["confidence"] == "ambiguous"
        assert result["top_score"] == 0.60
        assert mock_qdrant.search.call_count == 2

    @patch("app.services.retrieval._qdrant")
    @patch("app.services.retrieval.embed_texts")
    def test_out_of_scope_score(self, mock_embed, mock_qdrant):
        mock_embed.return_value = [[0.1] * 1536]
        mock_qdrant.search.return_value = [_make_search_result(0.30)]
        result = retrieve("course-1", "什么是微积分")
        assert result["confidence"] == "out_of_scope"
        assert result["top_score"] == 0.30
        assert result["results"] == []

    @patch("app.services.retrieval._qdrant")
    @patch("app.services.retrieval.embed_texts")
    def test_empty_embedding(self, mock_embed, mock_qdrant):
        mock_embed.return_value = []
        result = retrieve("course-1", "什么是微积分")
        assert result["confidence"] == "out_of_scope"
        assert result["top_score"] == 0.0

    @patch("app.services.retrieval._qdrant")
    @patch("app.services.retrieval.embed_texts")
    def test_no_search_results(self, mock_embed, mock_qdrant):
        mock_embed.return_value = [[0.1] * 1536]
        mock_qdrant.search.return_value = []
        result = retrieve("course-1", "什么是微积分")
        assert result["confidence"] == "out_of_scope"


class TestCragRefusal:
    @patch("app.services.crag.retrieve")
    async def test_out_of_scope_refusal(self, mock_retrieve):
        mock_retrieve.return_value = {
            "confidence": "out_of_scope",
            "top_score": 0.30,
            "results": [],
        }
        answer = await ask("course-1", "高等数学", "量子力学是什么")
        assert answer.confidence_status == "out_of_scope"
        assert "这个问题超出了高等数学的范围，我不知道。" in answer.answer
        assert answer.citations == []
        assert answer.refusal_reason == "out_of_scope"

    @patch("app.services.crag.retrieve")
    async def test_ambiguous_answer(self, mock_retrieve):
        mock_retrieve.return_value = {
            "confidence": "ambiguous",
            "top_score": 0.60,
            "results": [
                {
                    "text": "微积分是研究变化率的数学分支",
                    "score": 0.60,
                    "metadata": {"file_name": "calculus.pdf", "locator": "第1部分"},
                },
            ],
        }
        with patch("app.services.crag._llm_answer", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "根据材料，微积分是研究变化率的数学分支。来自 calculus.pdf · 第1部分"
            answer = await ask("course-1", "高等数学", "微积分是什么")
            assert answer.confidence_status == "ambiguous"
            assert answer.refusal_reason == "low_confidence"
            assert len(answer.citations) == 1
            assert answer.citations[0].file_name == "calculus.pdf"

    @patch("app.services.crag.retrieve")
    async def test_grounded_answer_with_citation(self, mock_retrieve):
        mock_retrieve.return_value = {
            "confidence": "grounded",
            "top_score": 0.85,
            "results": [
                {
                    "text": "导数表示函数在某一点的瞬时变化率",
                    "score": 0.85,
                    "metadata": {"file_name": "calculus.pdf", "locator": "第2部分"},
                },
            ],
        }
        with patch("app.services.crag._llm_answer", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "导数表示函数在某一点的瞬时变化率。来自 calculus.pdf · 第2部分"
            answer = await ask("course-1", "高等数学", "什么是导数")
            assert answer.confidence_status == "grounded"
            assert answer.refusal_reason is None
            assert len(answer.citations) == 1
            assert answer.citations[0].file_name == "calculus.pdf"
            assert answer.citations[0].locator == "第2部分"

    @patch("app.services.crag.retrieve")
    async def test_no_fallback_to_model_only(self, mock_retrieve):
        mock_retrieve.return_value = {
            "confidence": "out_of_scope",
            "top_score": 0.20,
            "results": [],
        }
        with patch("app.services.crag._llm_answer", new_callable=AsyncMock) as mock_llm:
            answer = await ask("course-1", "高等数学", "宇宙大爆炸是什么")
            mock_llm.assert_not_called()
            assert answer.confidence_status == "out_of_scope"
            assert "我不知道" in answer.answer

    @patch("app.services.crag.retrieve")
    async def test_grounded_answer_includes_course_id(self, mock_retrieve):
        mock_retrieve.return_value = {
            "confidence": "grounded",
            "top_score": 0.80,
            "results": [
                {
                    "text": "积分是微积分的逆运算",
                    "score": 0.80,
                    "metadata": {"file_name": "calc.pdf", "locator": "第3部分"},
                },
            ],
        }
        with patch("app.services.crag._llm_answer", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "积分是微积分的逆运算。来自 calc.pdf · 第3部分"
            answer = await ask("course-xyz", "高等数学", "什么是积分")
            assert answer.course_id == "course-xyz"


@pytest.mark.asyncio
async def test_chat_endpoint_course_not_found():
    from httpx import ASGITransport, AsyncClient
    import tempfile
    import os
    from app.db.sqlite_store import SqliteStore
    from app.main import app

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = SqliteStore(db_path=db_path)
    app.state.store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/courses/nonexistent/chat", json={"question": "test"})
        assert resp.status_code == 404

    store.close()
    os.unlink(db_path)
