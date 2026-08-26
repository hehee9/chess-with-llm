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
TakebackAction = Literal["request", "accept", "reject"]
TakebackState = Literal["pending", "accepted", "rejected"]


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


class TakebackStateError(GameError):
    """현재 게임 상태에서 요청할 수 없는 되돌리기 동작이다."""

    def __init__(self, reason: str) -> None:
        messages = {
            "no_move": "되돌릴 자신의 수가 없습니다.",
            "duplicate": "이미 되돌리기 요청이 대기 중입니다.",
            "own_request": "자신이 요청한 되돌리기에 응답할 수 없습니다.",
            "no_pending": "대기 중인 되돌리기 요청이 없습니다.",
            "pending_move": "되돌리기 요청이 대기 중일 때는 수를 둘 수 없습니다.",
        }
        super().__init__(messages[reason], 409)


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


@dataclass(frozen=True)
class _TakebackData:
    """되돌리기 요청과 처리 결과를 직렬화한다."""

    state: TakebackState
    requester: ActorName
    target_ply: int
    undone_plies: int

    def as_dict(self) -> dict[str, object]:
        """되돌리기 정보를 API 응답 모양으로 변환한다."""
        return {
            "state": self.state,
            "requester": self.requester,
            "target_ply": self.target_ply,
            "undone_plies": self.undone_plies,
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
        self._takeback: _TakebackData | None = None
        self._resigned_by: ActorName | None = None
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
        resigned_by = self._resigned_by

        if board is not None:
            if resigned_by is not None:
                status = "resigned"
                status_reason = "resignation"
                resigned_color = self._human_color if resigned_by == "human" else self._llm_color
                winner_color = "black" if resigned_color == "white" else "white"
                result = "1-0" if winner_color == "white" else "0-1"
            else:
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
            takeback_pending = self._takeback is not None and self._takeback.state == "pending"
            if status == "active" and not takeback_pending:
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
            if takeback_pending:
                status = "active"
                status_reason = "takeback_pending"

        return {
            "event": self._event,
            "game_id": self._game_id,
            "revision": self._revision,
            "status": status,
            "status_reason": status_reason,
            "resigned_by": resigned_by,
            "takeback": self._takeback.as_dict() if self._takeback else None,
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
            if snapshot["status"] in {"checkmate", "draw", "resigned"}:
                return snapshot
            takeback = snapshot.get("takeback")
            takeback_is_pending = isinstance(takeback, dict) and takeback.get("state") == "pending"
            if takeback_is_pending and takeback.get("requester") == "human":
                return snapshot
            if snapshot["turn"] == "llm" and not takeback_is_pending:
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
            self._takeback = None
            self._resigned_by = None
            event = "game_reset" if was_existing_game else "game_started"
            snapshot = self._publish_unlocked(event)
            self._condition.notify_all()
            return snapshot

    def _require_board_unlocked(self) -> chess.Board:
        if self._board is None:
            raise NoGameError()
        if self._resigned_by is not None:
            raise GameOverError()
        outcome = self._board.outcome(claim_draw=True)
        if outcome is not None:
            raise GameOverError()
        return self._board

    def _require_move_board_unlocked(self) -> chess.Board:
        """수 적용에 필요한 게임 상태를 확인한다."""
        board = self._require_board_unlocked()
        if self._takeback is not None and self._takeback.state == "pending":
            raise TakebackStateError("pending_move")
        return board

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
        if self._takeback is not None and self._takeback.state != "pending":
            self._takeback = None

    async def human_move(self, move_text: str) -> dict[str, object]:
        """UCI로 사람의 수를 적용한다."""
        async with self._condition:
            board = self._require_move_board_unlocked()
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
            board = self._require_move_board_unlocked()
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
            takeback = current.get("takeback")
            takeback_is_pending = isinstance(takeback, dict) and takeback.get("state") == "pending"
            if (
                current["status"] in {"checkmate", "draw", "resigned"}
                or (current["turn"] == "llm" and not takeback_is_pending)
                or (takeback_is_pending and takeback.get("requester") == "human")
            ):
                return current
            waited_revision = int(current["revision"])
            while True:
                while self._revision <= waited_revision:
                    await self._condition.wait()
                result = self._wait_result_unlocked(waited_revision)
                if result is not None:
                    return result
                waited_revision = self._revision

    async def takeback(self, actor: ActorName, action: TakebackAction) -> dict[str, object]:
        """되돌리기를 요청하거나 상대의 요청에 응답한다."""
        if action not in {"request", "accept", "reject"}:
            raise GameError("유효하지 않은 되돌리기 동작입니다.", 422)
        async with self._condition:
            board = self._require_board_unlocked()
            pending = self._takeback
            if action == "request":
                if pending is not None and pending.state == "pending":
                    raise TakebackStateError("duplicate")
                own_move_index = next(
                    (index for index in range(len(self._move_history) - 1, -1, -1)
                     if self._move_history[index].actor == actor),
                    None,
                )
                if own_move_index is None:
                    raise TakebackStateError("no_move")
                target = self._move_history[own_move_index]
                undone_plies = 1 if own_move_index == len(self._move_history) - 1 else 2
                request = _TakebackData(
                    state="pending",
                    requester=actor,
                    target_ply=target.ply,
                    undone_plies=undone_plies,
                )
                self._takeback = request
                event = "takeback_requested"
                snapshot = self._publish_unlocked(event)
                self._condition.notify_all()
                if actor == "llm":
                    while self._takeback is request:
                        await self._condition.wait()
                    response_events = {
                        "takeback_accepted",
                        "takeback_rejected",
                        "human_resigned",
                        "llm_resigned",
                        "game_reset",
                    }
                    for response in self._snapshots_after_unlocked(int(snapshot["revision"])):
                        if response["event"] in response_events:
                            return response
                    raise RuntimeError("되돌리기 응답 이벤트가 없습니다.")
                return snapshot

            if pending is None or pending.state != "pending":
                raise TakebackStateError("no_pending")
            if pending.requester == actor:
                raise TakebackStateError("own_request")
            if action == "reject":
                self._takeback = _TakebackData(
                    state="rejected",
                    requester=pending.requester,
                    target_ply=pending.target_ply,
                    undone_plies=0,
                )
                snapshot = self._publish_unlocked("takeback_rejected")
                self._condition.notify_all()
                return snapshot
            own_move_index = next(
                (index for index in range(len(self._move_history) - 1, -1, -1)
                 if self._move_history[index].actor == pending.requester),
                None,
            )
            if own_move_index is None:
                raise TakebackStateError("no_move")
            undone_plies = 1 if own_move_index == len(self._move_history) - 1 else 2
            for _ in range(undone_plies):
                board.pop()
            self._move_history = self._move_history[:-undone_plies]
            self._last_move = self._move_history[-1] if self._move_history else None
            self._takeback = _TakebackData(
                state="accepted",
                requester=pending.requester,
                target_ply=pending.target_ply,
                undone_plies=undone_plies,
            )
            snapshot = self._publish_unlocked("takeback_accepted")
            self._condition.notify_all()
            return snapshot

    async def resign(self, actor: ActorName) -> dict[str, object]:
        """행위자의 사임으로 게임을 종료한다."""
        async with self._condition:
            self._require_board_unlocked()
            self._takeback = None
            self._resigned_by = actor
            snapshot = self._publish_unlocked(f"{actor}_resigned")
            self._condition.notify_all()
            return snapshot

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
