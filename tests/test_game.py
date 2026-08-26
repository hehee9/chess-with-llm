import asyncio

import chess
import pytest

from llm_chess.game import (
    GameManager,
    GameOverError,
    IllegalMoveError,
    TakebackStateError,
    WrongTurnError,
)


@pytest.mark.asyncio
async def test_game_snapshot_and_turn_enforcement() -> None:
    manager = GameManager()

    initial = await manager.snapshot()
    assert initial["status"] == "setup"
    started = await manager.start_game("white")
    assert started["status"] == "active"
    assert started["turn"] == "human"
    assert len(started["pieces"]) == 32

    human_move = await manager.human_move("e2e4")
    assert human_move["last_move"]["san"] == "e4"
    assert human_move["turn"] == "llm"
    with pytest.raises(WrongTurnError):
        await manager.human_move("d2d4")

    llm_move = await manager.llm_move("e5", wait=False)
    assert llm_move["last_move"]["actor"] == "llm"
    assert llm_move["turn"] == "human"


@pytest.mark.asyncio
async def test_llm_wait_does_not_lose_human_move() -> None:
    manager = GameManager()
    waiter = asyncio.create_task(manager.wait_for_llm())
    await asyncio.sleep(0)
    await manager.start_game("white")
    await manager.human_move("e2e4")
    snapshot = await asyncio.wait_for(waiter, timeout=1)
    assert snapshot["event"] == "human_move"
    assert snapshot["turn"] == "llm"


@pytest.mark.asyncio
async def test_llm_move_wait_returns_reset() -> None:
    manager = GameManager()
    await manager.start_game("black")
    await manager.llm_move("e2e4", wait=False)
    await manager.human_move("e7e5")
    waiting_move = asyncio.create_task(manager.llm_move("g1f3", wait=True))
    await asyncio.sleep(0)
    reset = await manager.start_game("white")
    result = await asyncio.wait_for(waiting_move, timeout=1)
    assert reset["event"] == "game_reset"
    assert result["event"] == "game_reset"


@pytest.mark.asyncio
async def test_llm_move_wait_prefers_reset_after_a_fast_human_move() -> None:
    manager = GameManager()
    await manager.start_game("black")
    await manager.llm_move("e2e4", wait=False)
    await manager.human_move("e7e5")
    waiting_move = asyncio.create_task(manager.llm_move("g1f3", wait=True))
    await asyncio.sleep(0)

    await manager.human_move("b8c6")
    await manager.start_game("white")

    result = await asyncio.wait_for(waiting_move, timeout=1)
    assert result["event"] == "game_reset"


@pytest.mark.asyncio
async def test_illegal_and_terminal_moves_are_domain_errors() -> None:
    manager = GameManager()
    await manager.start_game("white")
    with pytest.raises(IllegalMoveError):
        await manager.human_move("e4")
    await manager.human_move("f2f3")
    await manager.llm_move("e5", wait=False)
    await manager.human_move("g2g4")
    terminal = await manager.llm_move("d8h4", wait=False)
    assert terminal["status"] == "checkmate"
    assert terminal["result"] == "0-1"
    with pytest.raises(GameOverError):
        await manager.human_move("a2a3")


@pytest.mark.asyncio
async def test_castling_and_en_passant_follow_standard_rules() -> None:
    castling = GameManager()
    await castling.start_game("white")
    await castling.human_move("e2e4")
    await castling.llm_move("e7e5", wait=False)
    await castling.human_move("g1f3")
    await castling.llm_move("b8c6", wait=False)
    await castling.human_move("f1e2")
    await castling.llm_move("g8f6", wait=False)
    castled = await castling.human_move("e1g1")
    assert castled["pieces"]["g1"] == "K"
    assert castled["pieces"]["f1"] == "R"

    en_passant = GameManager()
    await en_passant.start_game("white")
    await en_passant.human_move("e2e4")
    await en_passant.llm_move("a7a6", wait=False)
    await en_passant.human_move("e4e5")
    await en_passant.llm_move("d7d5", wait=False)
    captured = await en_passant.human_move("e5d6")
    assert captured["pieces"]["d6"] == "P"
    assert "d5" not in captured["pieces"]


@pytest.mark.asyncio
@pytest.mark.parametrize("promotion", ["q", "r", "b", "n"])
async def test_all_promotion_choices_are_applied(promotion: str) -> None:
    manager = GameManager()
    manager._board = chess.Board("8/P7/8/8/8/8/7k/K7 w - - 0 1")
    manager._game_id = "promotion"
    manager._human_color = "white"
    manager._llm_color = "black"

    snapshot = await manager.human_move(f"a7a8{promotion}")

    assert snapshot["last_move"]["promotion"] == promotion
    assert snapshot["pieces"]["a8"] == promotion.upper()


@pytest.mark.asyncio
async def test_stalemate_repetition_and_fifty_move_draws_are_detected() -> None:
    stalemate = GameManager()
    stalemate._board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    stalemate._game_id = "stalemate"
    stalemate._human_color = "black"
    stalemate._llm_color = "white"
    stalemate_snapshot = await stalemate.snapshot()
    assert stalemate_snapshot["status"] == "draw"
    assert stalemate_snapshot["status_reason"] == "stalemate"

    fifty_move = GameManager()
    fifty_move._board = chess.Board("7k/8/8/8/8/8/8/KR6 w - - 100 51")
    fifty_move._game_id = "fifty-move"
    fifty_move._human_color = "white"
    fifty_move._llm_color = "black"
    fifty_move_snapshot = await fifty_move.snapshot()
    assert fifty_move_snapshot["status"] == "draw"
    assert fifty_move_snapshot["status_reason"] == "fifty_moves"
    assert fifty_move_snapshot["legal_moves"] == []

    repetition = GameManager()
    await repetition.start_game("white")
    await repetition.human_move("g1f3")
    await repetition.llm_move("g8f6", wait=False)
    await repetition.human_move("f3g1")
    await repetition.llm_move("f6g8", wait=False)
    await repetition.human_move("g1f3")
    await repetition.llm_move("g8f6", wait=False)
    repeated = await repetition.human_move("f3g1")
    assert repeated["status"] == "draw"
    assert repeated["status_reason"] == "threefold_repetition"


@pytest.mark.asyncio
async def test_takeback_request_and_acceptance_undo_one_or_two_plies() -> None:
    one_ply = GameManager()
    await one_ply.start_game("white")
    await one_ply.human_move("e2e4")
    pending = await one_ply.takeback("human", "request")
    assert pending["event"] == "takeback_requested"
    assert pending["status"] == "active"
    assert pending["status_reason"] == "takeback_pending"
    assert pending["takeback"] == {
        "state": "pending",
        "requester": "human",
        "target_ply": 1,
        "undone_plies": 1,
    }
    assert pending["legal_moves"] == []
    accepted = await one_ply.takeback("llm", "accept")
    assert accepted["event"] == "takeback_accepted"
    assert accepted["takeback"]["undone_plies"] == 1
    assert accepted["turn"] == "human"
    assert accepted["move_history"] == []
    assert accepted["last_move"] is None

    two_plies = GameManager()
    await two_plies.start_game("white")
    await two_plies.human_move("e2e4")
    await two_plies.llm_move("e7e5", wait=False)
    pending = await two_plies.takeback("human", "request")
    assert pending["takeback"]["undone_plies"] == 2
    accepted = await two_plies.takeback("llm", "accept")
    assert accepted["takeback"]["undone_plies"] == 2
    assert accepted["turn"] == "human"
    assert accepted["move_history"] == []
    assert accepted["last_move"] is None


@pytest.mark.asyncio
async def test_takeback_rejection_preserves_position_and_move_clears_result() -> None:
    manager = GameManager()
    await manager.start_game("white")
    await manager.human_move("e2e4")
    await manager.llm_move("e7e5", wait=False)
    before = await manager.snapshot()
    await manager.takeback("human", "request")
    rejected = await manager.takeback("llm", "reject")
    assert rejected["event"] == "takeback_rejected"
    assert rejected["takeback"]["state"] == "rejected"
    assert rejected["takeback"]["undone_plies"] == 0
    assert rejected["fen"] == before["fen"]
    assert rejected["move_history"] == before["move_history"]
    resumed = await manager.human_move("g1f3")
    assert resumed["takeback"] is None


@pytest.mark.asyncio
async def test_pending_takeback_freezes_moves_and_wakes_waiters() -> None:
    manager = GameManager()
    await manager.start_game("black")
    await manager.llm_move("e2e4", wait=False)
    await manager.human_move("e7e5")
    waiting_move = asyncio.create_task(manager.llm_move("g1f3", wait=True))
    await asyncio.sleep(0)
    await manager.takeback("human", "request")
    result = await asyncio.wait_for(waiting_move, timeout=1)
    assert result["event"] == "takeback_requested"
    with pytest.raises(TakebackStateError):
        await manager.llm_move("g1f3", wait=False)
    with pytest.raises(TakebackStateError):
        await manager.takeback("human", "request")
    assert (await manager.wait_for_llm())["event"] == "takeback_requested"


@pytest.mark.asyncio
async def test_llm_takeback_waits_for_human_and_resignation_wakes_it() -> None:
    manager = GameManager()
    await manager.start_game("white")
    await manager.human_move("e2e4")
    await manager.llm_move("e7e5", wait=False)
    request = asyncio.create_task(manager.takeback("llm", "request"))
    await asyncio.sleep(0)
    assert (await manager.snapshot())["takeback"]["state"] == "pending"
    resigned = await manager.resign("human")
    result = await asyncio.wait_for(request, timeout=1)
    assert resigned["event"] == "human_resigned"
    assert result["status"] == "resigned"
    assert result["status_reason"] == "resignation"
    assert result["resigned_by"] == "human"
    assert result["turn"] is None
    assert result["legal_moves"] == []
    assert result["result"] == "0-1"


@pytest.mark.asyncio
async def test_llm_takeback_waiter_returns_its_original_reset_after_new_request() -> None:
    manager = GameManager()
    await manager.start_game("white")
    await manager.human_move("e2e4")
    await manager.llm_move("e7e5", wait=False)
    original = asyncio.create_task(manager.takeback("llm", "request"))
    await asyncio.sleep(0)

    await manager.start_game("white")
    await manager.human_move("e2e4")
    await manager.takeback("human", "request")

    result = await asyncio.wait_for(original, timeout=1)
    assert result["event"] == "game_reset"


@pytest.mark.asyncio
async def test_llm_pending_takeback_does_not_wake_llm_wait_or_blocking_move() -> None:
    manager = GameManager()
    await manager.start_game("black")
    await manager.llm_move("e2e4", wait=False)
    await manager.human_move("e7e5")
    blocking_move = asyncio.create_task(manager.llm_move("g1f3", wait=True))
    await asyncio.sleep(0)
    request = asyncio.create_task(manager.takeback("llm", "request"))
    await asyncio.sleep(0)
    assert not blocking_move.done()

    waiting = asyncio.create_task(manager.wait_for_llm())
    await asyncio.sleep(0)
    assert not waiting.done()

    rejected = await manager.takeback("human", "reject")
    assert rejected["event"] == "takeback_rejected"
    assert not blocking_move.done()
    assert not waiting.done()
    await manager.human_move("d7d5")

    move_result = await asyncio.wait_for(blocking_move, timeout=1)
    wait_result = await asyncio.wait_for(waiting, timeout=1)
    request_result = await asyncio.wait_for(request, timeout=1)
    assert move_result["event"] == "human_move"
    assert wait_result["event"] == "human_move"
    assert request_result["event"] == "takeback_rejected"
