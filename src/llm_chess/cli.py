"""로컬 체스 서버용 명령줄 인터페이스."""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence
from typing import Any

import httpx
import uvicorn


HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
_SHORT_TIMEOUT = httpx.Timeout(1.5, connect=0.6)
_WAIT_TIMEOUT = httpx.Timeout(connect=0.6, read=None, write=1.5, pool=1.5)
_SERVER_ERROR_TRANSLATIONS = {
    "진행 중인 게임이 없습니다. 먼저 게임을 시작하세요.": "No game is in progress. Start a game first.",
    "현재 사람 차례가 아닙니다.": "It is not the human's turn.",
    "현재 LLM 차례가 아닙니다.": "It is not the LLM's turn.",
    "게임이 이미 끝났습니다.": "The game has already ended.",
}
_ILLEGAL_MOVE_PREFIX = "불법 수입니다:"


def _help_text() -> str:
    """Markdown 형식의 명령 도움말을 반환한다."""
    return """# chess

Control a local human-vs-LLM chess game.

## Usage

```text
chess start
chess status
chess wait
chess move MOVE [--no-wait]
```

Enter `MOVE` in UCI or SAN notation when it is the LLM's turn.
"""


def _english_server_error(detail: object, status_code: int) -> str:
    """서버 오류를 CLI용 영어 문구로 변환한다."""
    if isinstance(detail, str):
        translated = _SERVER_ERROR_TRANSLATIONS.get(detail)
        if translated is not None:
            return translated
        if detail.startswith(_ILLEGAL_MOVE_PREFIX):
            move = detail.removeprefix(_ILLEGAL_MOVE_PREFIX).strip()
            return f"Illegal move: {move}"
        if detail.isascii():
            return detail
    return f"Server request failed (HTTP {status_code})."


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    wait_for_event: bool = False,
) -> tuple[dict[str, Any] | None, int]:
    """로컬 API를 호출하고 도메인 오류를 Markdown으로 출력한다."""
    timeout = _WAIT_TIMEOUT if wait_for_event else _SHORT_TIMEOUT
    try:
        with httpx.Client(base_url=BASE_URL, timeout=timeout) as client:
            response = client.request(method, path, json=payload)
    except httpx.RequestError:
        print(f"**Error:** Unable to connect to the server at `{BASE_URL}`.")
        return None, 1

    if response.is_success:
        try:
            body = response.json()
        except ValueError:
            print("**Error:** The server returned invalid JSON.")
            return None, 1
        return body, 0

    try:
        body = response.json()
    except ValueError:
        print(f"**Error:** Server request failed (HTTP {response.status_code}).")
        return None, 1
    detail = body.get("detail") if isinstance(body, dict) else None
    print(f"**Error:** {_english_server_error(detail, response.status_code)}")
    return None, 1


def _render_board(pieces: dict[str, str]) -> list[str]:
    """기물을 흰색 기준 ASCII 보드로 렌더링한다."""
    lines = ["**Board:**", "", "```text", "    a b c d e f g h"]
    for rank in range(8, 0, -1):
        cells = [pieces.get(f"{file}{rank}", ".") for file in "abcdefgh"]
        lines.append(f"{rank}   {' '.join(cells)}  {rank}")
    lines.extend(["    a b c d e f g h", "```"])
    return lines


def render_snapshot(snapshot: dict[str, Any]) -> str:
    """게임 스냅샷을 문서형 Markdown으로 렌더링한다."""
    lines = [f"**Event:** {snapshot.get('event', 'unknown')}"]
    last_move = snapshot.get("last_move")
    if isinstance(last_move, dict):
        actor = last_move.get("actor", "unknown")
        move_text = f"`{last_move.get('uci')}` (`{last_move.get('san')}`)"
        label = "Human move" if actor == "human" else "LLM move"
        lines.append(f"**{label}:** {move_text}")

    human_color = snapshot.get("human_color") or "—"
    llm_color = snapshot.get("llm_color") or "—"
    lines.extend(
        [
            f"**Colors:** Human `{human_color}` · LLM `{llm_color}`",
            f"**Turn:** `{snapshot.get('turn') or '—'}`",
            f"**Status:** `{snapshot.get('status')}` ({snapshot.get('status_reason')})",
            f"**Check:** `{'Yes' if snapshot.get('check') else 'No'}`",
            f"**Result:** `{snapshot.get('result') or '—'}`",
            f"**FEN:** `{snapshot.get('fen') or '—'}`",
        ]
    )

    pieces = snapshot.get("pieces")
    if isinstance(pieces, dict) and snapshot.get("fen"):
        lines.extend(["", *_render_board(pieces)])
    else:
        lines.extend(["", "**Board:** _(no game in progress)_"])

    legal_moves = snapshot.get("legal_moves")
    if isinstance(legal_moves, list):
        lines.extend(["", "**Legal moves:**", "", "| UCI | SAN |", "| --- | --- |"])
        for move in legal_moves:
            if isinstance(move, dict):
                lines.append(f"| `{move.get('uci')}` | `{move.get('san')}` |")
        if not legal_moves:
            lines.append("| — | — |")
    return "\n".join(lines)


def _server_is_running() -> bool:
    """해당 주소의 상태 확인 응답이 이 앱인지 확인한다."""
    try:
        with httpx.Client(timeout=_SHORT_TIMEOUT) as client:
            response = client.get(f"{BASE_URL}/api/health")
    except httpx.RequestError:
        return False
    if not response.is_success:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("app") == "llm-chess"


def _open_browser_when_ready() -> None:
    """서버 상태 확인이 성공한 뒤 브라우저를 연다."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _server_is_running():
            webbrowser.open(BASE_URL)
            return
        time.sleep(0.1)


def _start() -> int:
    """서버를 시작하고 브라우저를 연다."""
    if _server_is_running():
        webbrowser.open(BASE_URL)
        return 0
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    print(f"LLM Chess server: {BASE_URL}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        uvicorn.run(
            "llm_chess.app:app",
            host=HOST,
            port=PORT,
            timeout_graceful_shutdown=1,
            access_log=False,
            log_level="critical",
        )
    except OSError:
        print("**Error:** Unable to start the server.")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """CLI 인자를 구성한다."""
    parser = argparse.ArgumentParser(prog="chess", add_help=False)
    parser.add_argument("--help", action="store_true", dest="show_help")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("start")
    subparsers.add_parser("status")
    subparsers.add_parser("wait")
    move_parser = subparsers.add_parser("move")
    move_parser.add_argument("move")
    move_parser.add_argument("--no-wait", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """명령을 실행하고 종료 코드를 반환한다."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.show_help or args.command is None:
        print(_help_text())
        return 0
    if args.command == "start":
        return _start()
    if args.command == "status":
        snapshot, exit_code = _request("GET", "/api/state")
    elif args.command == "wait":
        snapshot, exit_code = _request("POST", "/api/llm/wait", wait_for_event=True)
    else:
        snapshot, exit_code = _request(
            "POST",
            "/api/llm/moves",
            {"move": args.move, "wait": not args.no_wait},
            wait_for_event=not args.no_wait,
        )
    if snapshot is None:
        return exit_code
    print(render_snapshot(snapshot))
    if args.command in {"wait", "move"} and snapshot.get("event") == "game_reset":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
