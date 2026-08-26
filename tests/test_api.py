import asyncio

import httpx
import pytest

from llm_chess.app import app, manager


@pytest.fixture(autouse=True)
def reset_manager() -> None:
    manager._condition = asyncio.Condition()
    manager._board = None
    manager._game_id = None
    manager._human_color = None
    manager._llm_color = None
    manager._move_history = []
    manager._last_move = None
    manager._takeback = None
    manager._resigned_by = None
    manager._revision = 0
    manager._event = "setup"
    manager._published = [manager._snapshot_unlocked()]


@pytest.mark.asyncio
async def test_api_game_flow_and_errors() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        assert health.json()["app"] == "llm-chess"
        assert app.version == "0.2.0"
        state = await client.get("/api/state")
        assert state.json()["status"] == "setup"
        no_game = await client.post("/api/human/moves", json={"move": "e2e4"})
        assert no_game.status_code == 409
        started = await client.post("/api/games", json={"human_color": "white"})
        assert started.status_code == 200
        human = await client.post("/api/human/moves", json={"move": "e2e4"})
        assert human.json()["last_move"]["uci"] == "e2e4"
        wrong_turn = await client.post("/api/human/moves", json={"move": "d2d4"})
        assert wrong_turn.status_code == 409
        llm = await client.post("/api/llm/moves", json={"move": "e5", "wait": False})
        assert llm.json()["last_move"]["san"] == "e5"


@pytest.mark.asyncio
async def test_llm_wait_starts_after_human_move() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        waiter = asyncio.create_task(client.post("/api/llm/wait"))
        await asyncio.sleep(0)
        await client.post("/api/games", json={"human_color": "white"})
        await client.post("/api/human/moves", json={"move": "e2e4"})
        response = await asyncio.wait_for(waiter, timeout=1)
        assert response.json()["event"] == "human_move"


@pytest.mark.asyncio
async def test_sse_source_starts_with_snapshot() -> None:
    from llm_chess.app import manager

    stream = manager.event_stream()
    first = await anext(stream)
    await stream.aclose()
    assert first["event"] == "setup"


@pytest.mark.asyncio
async def test_takeback_api_is_strict_and_supports_acceptance() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/games", json={"human_color": "white"})
        no_move = await client.post("/api/human/takeback", json={"action": "request"})
        assert no_move.status_code == 409
        await client.post("/api/human/moves", json={"move": "e2e4"})
        pending = await client.post("/api/human/takeback", json={"action": "request"})
        assert pending.status_code == 200
        assert pending.json()["event"] == "takeback_requested"
        extra = await client.post(
            "/api/llm/takeback",
            json={"action": "accept", "extra": True},
        )
        assert extra.status_code == 422
        accepted = await client.post("/api/llm/takeback", json={"action": "accept"})
        assert accepted.status_code == 200
        assert accepted.json()["takeback"]["state"] == "accepted"
        assert accepted.json()["move_history"] == []


@pytest.mark.asyncio
async def test_llm_takeback_blocks_until_human_response_and_resign_is_terminal() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/games", json={"human_color": "white"})
        await client.post("/api/human/moves", json={"move": "e2e4"})
        await client.post("/api/llm/moves", json={"move": "e7e5", "wait": False})
        waiting = asyncio.create_task(
            client.post("/api/llm/takeback", json={"action": "request"})
        )
        await asyncio.sleep(0)
        state = await client.get("/api/state")
        assert state.json()["takeback"]["state"] == "pending"
        resigned = await client.post("/api/human/resign")
        assert resigned.status_code == 200
        assert resigned.json()["status"] == "resigned"
        result = await asyncio.wait_for(waiting, timeout=1)
        assert result.json()["event"] == "human_resigned"
        assert result.json()["resigned_by"] == "human"
        assert result.json()["result"] == "0-1"
        terminal_request = await client.post("/api/llm/resign")
        assert terminal_request.status_code == 409
