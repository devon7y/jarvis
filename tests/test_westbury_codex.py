import json
from pathlib import Path

from server import extract_action
from westbury_codex import (
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    build_codex_command,
    build_database_prompt,
    parse_database_response,
)


def test_build_database_prompt_mentions_multi_query_and_tool():
    prompt = build_database_prompt("What has Westbury studied about humor?")
    assert "query_westbury_papers" in prompt
    assert "You may call the MCP tool multiple times." in prompt
    assert "What has Westbury studied about humor?" in prompt


def test_build_codex_command_uses_expected_flags(tmp_path: Path):
    output_file = tmp_path / "result.json"
    schema_file = tmp_path / "schema.json"

    cmd = build_codex_command(
        session_dir=tmp_path,
        output_file=output_file,
        schema_file=schema_file,
    )

    assert cmd[:2] == ["codex", "exec"]
    assert "--full-auto" in cmd
    assert "--skip-git-repo-check" in cmd
    assert CODEX_MODEL in cmd
    assert f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"' in cmd
    assert str(output_file) in cmd
    assert str(schema_file) in cmd
    assert cmd[-1] == "-"


def test_parse_database_response_normalizes_fields():
    raw = json.dumps({
        "answer": "  Humor research   often links incongruity and entropy.  ",
        "confidence": "HIGH",
        "evidence": [" One paper tied surprise to humor perception. ", " Another examined entropy in language. "],
        "used_follow_up_queries": True,
        "follow_up_question": " Would you like the specific paper names? ",
    })

    result = parse_database_response(raw)

    assert result.answer == "Humor research often links incongruity and entropy."
    assert result.confidence == "high"
    assert result.evidence == [
        "One paper tied surprise to humor perception.",
        "Another examined entropy in language.",
    ]
    assert result.used_follow_up_queries is True
    assert result.follow_up_question == "Would you like the specific paper names?"


def test_parse_database_response_requires_answer():
    raw = json.dumps({
        "answer": "   ",
        "confidence": "medium",
        "evidence": [],
        "used_follow_up_queries": False,
        "follow_up_question": "",
    })

    try:
        parse_database_response(raw)
    except ValueError as exc:
        assert "answer" in str(exc).lower()
    else:
        raise AssertionError("Expected parse_database_response to reject an empty answer")


def test_extract_action_supports_database():
    clean, action = extract_action(
        "Checking the papers now, sir. [ACTION:DATABASE] what has Westbury studied about humor and incongruity?"
    )
    assert clean == "Checking the papers now, sir."
    assert action == {
        "action": "database",
        "target": "what has Westbury studied about humor and incongruity?",
    }
