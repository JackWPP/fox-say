from unittest.mock import patch

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
