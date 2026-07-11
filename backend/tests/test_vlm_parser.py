"""VLM 图片解析器的配置与错误可见性契约测试（全部 mock，不调用真实 API）。"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest
from pydantic import ValidationError

import app.services.vlm_parser as vlm_parser
from app.core.config import Settings
from app.services.parser_interface import DocumentParsingException


def _image_file(tmp_path: Path, suffix: str = ".jpg") -> Path:
    image_path = tmp_path / f"image{suffix}"
    image_path.write_bytes(b"synthetic-image-bytes")
    return image_path


def _configure_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vlm_parser.settings, "vlm_api_key", "test-vlm-key")
    monkeypatch.setattr(vlm_parser.settings, "vlm_api_base", "https://vlm.test/v1")
    monkeypatch.setattr(vlm_parser.settings, "vlm_model", "test-vlm-model")
    monkeypatch.setattr(vlm_parser.settings, "vlm_max_tokens", 321)


def _response(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_vlm_settings_defaults_are_independent() -> None:
    settings = Settings(_env_file=None)

    assert settings.vlm_api_key == ""
    assert settings.vlm_api_base == "https://api.siliconflow.cn/v1"
    assert settings.vlm_model == "Qwen/Qwen3.6-27B"
    assert settings.vlm_max_tokens == 2048


def test_vlm_settings_read_uppercase_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLM_API_KEY", "configured-key")
    monkeypatch.setenv("VLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("VLM_MODEL", "custom-vlm")
    monkeypatch.setenv("VLM_MAX_TOKENS", "123")

    settings = Settings(_env_file=None)

    assert settings.vlm_api_key == "configured-key"
    assert settings.vlm_api_base == "https://example.test/v1"
    assert settings.vlm_model == "custom-vlm"
    assert settings.vlm_max_tokens == 123


def test_vlm_settings_reject_non_positive_output_budget() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(_env_file=None, vlm_max_tokens=0)


def test_vlm_uses_independent_config_data_uri_and_thinking_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_vlm(monkeypatch)
    client = MagicMock()
    client.chat.completions.create.return_value = _response("# Extracted")
    openai_factory = MagicMock(return_value=client)
    monkeypatch.setattr(openai, "OpenAI", openai_factory)
    image_path = _image_file(tmp_path)

    content = vlm_parser.VLMImageParser()._call_vlm(image_path)

    assert content == "# Extracted"
    openai_factory.assert_called_once_with(
        api_key="test-vlm-key",
        base_url="https://vlm.test/v1",
        timeout=60,
    )
    create_kwargs = client.chat.completions.create.call_args.kwargs
    assert create_kwargs["model"] == "test-vlm-model"
    assert create_kwargs["max_tokens"] == 321
    assert create_kwargs["extra_body"] == {"enable_thinking": False}
    image_url = create_kwargs["messages"][0]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(image_url.rsplit(",", maxsplit=1)[1]) == image_path.read_bytes()


def test_vlm_missing_key_is_visible_and_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(vlm_parser.settings, "vlm_api_key", "")
    openai_factory = MagicMock()
    monkeypatch.setattr(openai, "OpenAI", openai_factory)

    with pytest.raises(DocumentParsingException, match="VLM_API_KEY is not configured"):
        vlm_parser.VLMImageParser()._call_vlm(_image_file(tmp_path))

    openai_factory.assert_not_called()


def test_vlm_empty_content_raises_visible_parsing_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_vlm(monkeypatch)
    client = MagicMock()
    client.chat.completions.create.return_value = _response("  \n")
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))

    with pytest.raises(DocumentParsingException, match="VLM returned empty content"):
        vlm_parser.VLMImageParser()._call_vlm(_image_file(tmp_path))


def test_vlm_api_error_is_wrapped_as_visible_parsing_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_vlm(monkeypatch)
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("simulated API outage")
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))

    with pytest.raises(DocumentParsingException, match="VLM API call failed") as exc_info:
        vlm_parser.VLMImageParser()._call_vlm(_image_file(tmp_path))

    assert isinstance(exc_info.value.original_error, RuntimeError)
