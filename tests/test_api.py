import asyncio

import httpx
import pytest

from llm_chess.app import app, manager


@pytest.fixture(autouse=True)
def reset_manager() -> None:
    manager._board = None
    manager._game_id = None
    manager._human_color = None
    manager._llm_color = None
    manager._move_history = []
    manager._last_move = None
    manager._revision = 0
    manager._event = "setup"
    manager._published = [manager._snapshot_unlocked()]


@pytest.mark.asyncio
async def test_api_game_flow_and_errors() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        assert health.json()["app"] == "llm-chess"
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
