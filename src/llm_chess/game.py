"""표준 체스 규칙과 비동기 대기 상태를 관리한다."""

from __future__ import annotations

import asyncio
import copy
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import chess


ColorName = Literal["white", "black"]
ActorName = Literal["human", "llm"]


class GameError(Exception):
    """클라이언트에 반환할 정상적인 게임 도메인 오류."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NoGameError(GameError):
    """시작된 게임이 없는 상태에서 게임 동작을 요청했다."""

    def __init__(self) -> None:
        super().__init__("진행 중인 게임이 없습니다. 먼저 게임을 시작하세요.", 409)


class WrongTurnError(GameError):
    """현재 요청한 행위자의 차례가 아니다."""

    def __init__(self, actor: ActorName) -> None:
        actor_name = "사람" if actor == "human" else "LLM"
        super().__init__(f"현재 {actor_name} 차례가 아닙니다.", 409)


class GameOverError(GameError):
    """이미 끝난 게임에 수를 두려고 했다."""

    def __init__(self) -> None:
        super().__init__("게임이 이미 끝났습니다.", 409)


class IllegalMoveError(GameError):
    """표준 체스 규칙에 맞지 않는 수를 요청했다."""

    def __init__(self, move: str) -> None:
        super().__init__(f"불법 수입니다: {move}", 422)


@dataclass(frozen=True)
class _MoveData:
    """직렬화 전 수 기록."""

    ply: int
    uci: str
    san: str
    actor: ActorName
    from_square: str
    to_square: str
    promotion: str | None

    def as_dict(self) -> dict[str, object]:
        """수 기록을 API 응답 모양으로 변환한다."""
        return {
            "ply": self.ply,
            "uci": self.uci,
            "san": self.san,
            "actor": self.actor,
            "from": self.from_square,
            "to": self.to_square,
            "promotion": self.promotion,
        }


class GameManager:
    """한 개의 인메모리 체스 게임과 변경 알림을 소유한다."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._board: chess.Board | None = None
        self._game_id: str | None = None
        self._human_color: ColorName | None = None
        self._llm_color: ColorName | None = None
        self._move_history: list[_MoveData] = []
        self._last_move: _MoveData | None = None
        self._revision = 0
        self._event = "setup"
        self._published: list[dict[str, object]] = []
        self._published.append(self._snapshot_unlocked())

    def _snapshot_unlocked(self) -> dict[str, object]:
        board = self._board
        status = "setup"
        status_reason = "no_game"
        turn: str | None = None
        fen: str | None = None
        pieces: dict[str, str] = {}
        legal_moves: list[dict[str, object]] = []
        check = False
        checked_king_square: str | None = None
        result: str | None = None

        if board is not None:
            outcome = board.outcome(claim_draw=True)
            if outcome is None:
                status = "active"
                status_reason = "in_progress"
                turn = "human" if board.turn == (self._human_color == "white") else "llm"
            else:
                status = "checkmate" if outcome.termination is chess.Termination.CHECKMATE else "draw"
                status_reason = outcome.termination.name.lower()
                result = outcome.result()

            fen = board.fen()
            pieces = {
                chess.square_name(square): piece.symbol()
                for square, piece in board.piece_map().items()
            }
            check = board.is_check()
            if check:
                king_square = board.king(board.turn)
                checked_king_square = chess.square_name(king_square) if king_square is not None else None
            for move in board.legal_moves:
                legal_moves.append(
                    {
                        "uci": move.uci(),
                        "san": board.san(move),
                        "from": chess.square_name(move.from_square),
                        "to": chess.square_name(move.to_square),
                        "promotion": chess.piece_symbol(move.promotion) if move.promotion else None,
                    }
                )

        return {
            "event": self._event,
            "game_id": self._game_id,
            "revision": self._revision,
            "status": status,
            "status_reason": status_reason,
            "human_color": self._human_color,
            "llm_color": self._llm_color,
            "turn": turn,
            "fen": fen,
            "pieces": pieces,
            "legal_moves": legal_moves,
            "move_history": [move.as_dict() for move in self._move_history],
            "last_move": self._last_move.as_dict() if self._last_move else None,
            "check": check,
            "checked_king_square": checked_king_square,
            "result": result,
        }

    def _publish_unlocked(self, event: str) -> dict[str, object]:
        self._event = event
        self._revision += 1
        snapshot = self._snapshot_unlocked()
        self._published.append(snapshot)
        return copy.deepcopy(snapshot)

    def _current_snapshot_unlocked(self) -> dict[str, object]:
        return copy.deepcopy(self._snapshot_unlocked())

    def _snapshots_after_unlocked(self, revision: int) -> list[dict[str, object]]:
        return [copy.deepcopy(item) for item in self._published if item["revision"] > revision]

    def _wait_result_unlocked(self, revision: int) -> dict[str, object] | None:
        pending = self._snapshots_after_unlocked(revision)
        for snapshot in pending:
            if snapshot["event"] == "game_reset":
                return snapshot
        for snapshot in pending:
            if snapshot["status"] in {"checkmate", "draw"} or snapshot["turn"] == "llm":
                return snapshot
        return None

    async def snapshot(self) -> dict[str, object]:
        """현재 상태를 반환한다."""
        async with self._condition:
            return self._current_snapshot_unlocked()

    async def start_game(self, human_color: ColorName) -> dict[str, object]:
        """사람 색으로 새 표준 체스 게임을 시작한다."""
        async with self._condition:
            was_existing_game = self._board is not None
            self._board = chess.Board()
            self._game_id = uuid.uuid4().hex
            self._human_color = human_color
            self._llm_color = "black" if human_color == "white" else "white"
            self._move_history = []
            self._last_move = None
            event = "game_reset" if was_existing_game else "game_started"
            snapshot = self._publish_unlocked(event)
            self._condition.notify_all()
            return snapshot

    def _require_board_unlocked(self) -> chess.Board:
        if self._board is None:
            raise NoGameError()
        outcome = self._board.outcome(claim_draw=True)
        if outcome is not None:
            raise GameOverError()
        return self._board

    def _require_turn_unlocked(self, actor: ActorName, board: chess.Board) -> None:
        expected = self._human_color if actor == "human" else self._llm_color
        actual = "white" if board.turn else "black"
        if expected != actual:
            raise WrongTurnError(actor)

    def _parse_move_unlocked(self, move_text: str, allow_san: bool, board: chess.Board) -> chess.Move:
        try:
            return board.parse_uci(move_text)
        except ValueError:
            if allow_san:
                try:
                    return board.parse_san(move_text)
                except ValueError:
                    pass
            raise IllegalMoveError(move_text) from None

    def _apply_move_unlocked(
        self,
        board: chess.Board,
        move: chess.Move,
        actor: ActorName,
    ) -> None:
        san = board.san(move)
        board.push(move)
        data = _MoveData(
            ply=len(self._move_history) + 1,
            uci=move.uci(),
            san=san,
            actor=actor,
            from_square=chess.square_name(move.from_square),
            to_square=chess.square_name(move.to_square),
            promotion=chess.piece_symbol(move.promotion) if move.promotion else None,
        )
        self._move_history.append(data)
        self._last_move = data

    async def human_move(self, move_text: str) -> dict[str, object]:
        """UCI로 사람의 수를 적용한다."""
        async with self._condition:
            board = self._require_board_unlocked()
            self._require_turn_unlocked("human", board)
            move = self._parse_move_unlocked(move_text, allow_san=False, board=board)
            self._apply_move_unlocked(board, move, "human")
            event = "checkmate" if board.is_checkmate() else "draw" if board.outcome(claim_draw=True) else "human_move"
            snapshot = self._publish_unlocked(event)
            self._condition.notify_all()
            return snapshot

    async def llm_move(self, move_text: str, wait: bool = True) -> dict[str, object]:
        """UCI 또는 SAN으로 언어 모델의 수를 적용하고 필요하면 기다린다."""
        async with self._condition:
            board = self._require_board_unlocked()
            self._require_turn_unlocked("llm", board)
            move = self._parse_move_unlocked(move_text, allow_san=True, board=board)
            self._apply_move_unlocked(board, move, "llm")
            event = "checkmate" if board.is_checkmate() else "draw" if board.outcome(claim_draw=True) else "llm_move"
            snapshot = self._publish_unlocked(event)
            waited_revision = int(snapshot["revision"])
            self._condition.notify_all()
            if not wait or snapshot["status"] != "active":
                return snapshot

            while True:
                while self._revision <= waited_revision:
                    await self._condition.wait()
                result = self._wait_result_unlocked(waited_revision)
                if result is not None:
                    return result
                waited_revision = self._revision

    async def wait_for_llm(self) -> dict[str, object]:
        """언어 모델 차례 또는 게임 종료/초기화를 기다린다."""
        async with self._condition:
            current = self._current_snapshot_unlocked()
            if current["status"] in {"checkmate", "draw"} or current["turn"] == "llm":
                return current
            waited_revision = int(current["revision"])
            while True:
                while self._revision <= waited_revision:
                    await self._condition.wait()
                result = self._wait_result_unlocked(waited_revision)
                if result is not None:
                    return result
                waited_revision = self._revision

    async def event_stream(self) -> AsyncIterator[dict[str, object]]:
        """초기 스냅샷부터 모든 상태 변경을 순서대로 내보낸다."""
        async with self._condition:
            initial = self._current_snapshot_unlocked()
        yield initial
        seen_revision = int(initial["revision"])
        while True:
            async with self._condition:
                while self._revision <= seen_revision:
                    await self._condition.wait()
                pending = self._snapshots_after_unlocked(seen_revision)
            for snapshot in pending:
                seen_revision = int(snapshot["revision"])
                yield snapshot
