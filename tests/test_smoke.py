"""Tests for olla.smoke."""

from olla.smoke import FIXED_PROMPTS, classify_response, run_smoke_test


def test_classify_response_final_tag_is_compliant():
    assert classify_response("<final>The answer is 42</final>") == "compliant"


def test_classify_response_tool_args_tags_is_compliant():
    assert classify_response("<tool>shell</tool><args>ls -la</args>") == "compliant"


def test_classify_response_native_qwen_tool_call_is_reverted():
    content = '<tool_call>{"name": "shell", "arguments": {"command": "ls"}}'
    assert classify_response(content) == "reverted_to_native_format"


def test_classify_response_native_gemma_tool_json_is_reverted():
    content = '<tool>{"name": "shell"}'
    assert classify_response(content) == "reverted_to_native_format"


def test_classify_response_prose_is_non_compliant():
    content = "I think I should run a command but I'm not sure how."
    assert classify_response(content) == "non_compliant"


def test_run_smoke_test_calls_call_model_for_each_think_mode_and_prompt(mocker):
    mock_call_model = mocker.patch("olla.smoke.call_model")
    mock_call_model.return_value = "<final>ok</final>"

    run_smoke_test("test-model")

    assert mock_call_model.call_count == 2 * len(FIXED_PROMPTS)

    think_false_calls = [
        call for call in mock_call_model.call_args_list if call.kwargs.get("think") is False
    ]
    think_true_calls = [
        call for call in mock_call_model.call_args_list if call.kwargs.get("think") is True
    ]
    assert len(think_false_calls) == len(FIXED_PROMPTS)
    assert len(think_true_calls) == len(FIXED_PROMPTS)


def test_run_smoke_test_prints_compliance_lines_no_warning_when_fully_compliant(mocker, capsys):
    mock_call_model = mocker.patch("olla.smoke.call_model")
    mock_call_model.return_value = "<final>ok</final>"

    run_smoke_test("test-model")

    captured = capsys.readouterr()
    total = len(FIXED_PROMPTS)
    assert f"think=False): 100% compliant ({total}/{total})" in captured.out
    assert f"think=True): 100% compliant ({total}/{total})" in captured.out
    assert "WARNING" not in captured.out


def test_run_smoke_test_warns_when_think_false_below_80_percent(mocker, capsys):
    mock_call_model = mocker.patch("olla.smoke.call_model")

    def side_effect(model, messages, think=False):
        if think is False:
            return "I think I should run a command but I'm not sure how."
        return "<final>ok</final>"

    mock_call_model.side_effect = side_effect

    run_smoke_test("test-model")

    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    warning_lines = [line for line in lines if "WARNING" in line]
    assert len(warning_lines) == 1
    assert "test-model" in warning_lines[0]
    assert "below 80% threshold" in warning_lines[0]

    # No WARNING line should be associated with the think=True result.
    think_true_line_index = next(
        i for i, line in enumerate(lines) if "think=True)" in line
    )
    # The line immediately after think=True's compliance line must not be a WARNING.
    if think_true_line_index + 1 < len(lines):
        assert "WARNING" not in lines[think_true_line_index + 1]


def test_run_smoke_test_remote_provider(mocker, capsys):
    mock_provider = mocker.MagicMock()
    mock_provider.chat.return_value = "<final>42</final>"
    mock_get = mocker.patch("olla.smoke.get_provider", return_value=(mock_provider, "llama-3.1"))

    run_smoke_test("openrouter/meta-llama/llama-3.1-8b", api_key="test-key", base_url="https://test.api/v1")

    mock_get.assert_called_once_with(
        model="openrouter/meta-llama/llama-3.1-8b",
        api_key="test-key",
        base_url="https://test.api/v1",
    )
    captured = capsys.readouterr()
    assert "100% compliant" in captured.out


def test_run_smoke_test_init_provider_error(mocker, capsys):
    from olla.providers import ProviderError

    mocker.patch("olla.smoke.get_provider", side_effect=ProviderError("Missing API key"))

    run_smoke_test("openrouter/meta-llama/llama-3.1-8b")

    captured = capsys.readouterr()
    assert "Smoke test failed to initialize model" in captured.out
    assert "Missing API key" in captured.out
