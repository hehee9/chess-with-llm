import re

from llm_chess import cli


def _assert_english(output: str) -> None:
    assert re.search(r"[가-힣]", output) is None


def test_help_is_markdown(capsys) -> None:
    assert cli.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("# chess")
    assert "chess move MOVE" in output
    assert "Control a local human-vs-LLM chess game." in output
    _assert_english(output)


def test_status_renders_event_first(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_request",
        lambda method, path, payload=None: ({
            "event": "human_move",
            "human_color": "white",
            "llm_color": "black",
            "turn": "llm",
            "status": "active",
            "status_reason": "in_progress",
            "check": False,
            "result": None,
            "fen": "fen",
            "pieces": {"e4": "P"},
            "legal_moves": [{"uci": "e7e5", "san": "e5"}],
            "last_move": {"actor": "human", "uci": "e2e4", "san": "e4"},
        }, 0),
    )
    assert cli.main(["status"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("**Event:** human_move")
    assert "**Human move:** `e2e4` (`e4`)" in output
    assert "**Check:** `No`" in output
    assert "**Legal moves:**" in output
    assert "| `e7e5` | `e5` |" in output
    _assert_english(output)


def test_reset_wake_is_nonzero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_request",
        lambda method, path, payload=None, **kwargs: ({"event": "game_reset"}, 0),
    )
    assert cli.main(["wait"]) == 1
    output = capsys.readouterr().out
    assert "game_reset" in output
    _assert_english(output)


def test_server_errors_are_rendered_in_english() -> None:
    assert cli._english_server_error(
        "진행 중인 게임이 없습니다. 먼저 게임을 시작하세요.",
        409,
    ) == "No game is in progress. Start a game first."
    assert cli._english_server_error(
        "불법 수입니다: e2e5",
        422,
    ) == "Illegal move: e2e5"
    assert cli._english_server_error(
        "알 수 없는 서버 오류",
        500,
    ) == "Server request failed (HTTP 500)."
