"""服务器 WebSocket 集成测试
在随机端口启动真实服务器, 用 aiohttp 客户端模拟两位玩家完整游戏。
"""
import asyncio
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402
import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

import server  # noqa: E402


@pytest.fixture(scope="module")
def server_url():
    """在随机端口启动服务器, 返回 ws/http 基地址"""
    app = server.make_app()
    runner = web.AppRunner(app)
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    fut = asyncio.run_coroutine_threadsafe(runner.setup(), loop)
    fut.result()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    site_fut = asyncio.run_coroutine_threadsafe(site.start(), loop)
    site_fut.result()
    port = site._server.sockets[0].getsockname()[1]

    base = f"http://127.0.0.1:{port}"
    yield base

    asyncio.run_coroutine_threadsafe(runner.cleanup(), loop).result()
    loop.call_soon_threadsafe(loop.stop)


async def ws_connect(base, session=None):
    if session is None:
        session = aiohttp.ClientSession()
        return await session.ws_connect(base.replace("http", "ws") + "/ws"), session
    return await session.ws_connect(base.replace("http", "ws") + "/ws"), None


async def recv_until(ws, mtype, timeout=10):
    """接收消息直到指定类型"""
    async def _recv():
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            if data.get("type") == mtype:
                return data
    return await asyncio.wait_for(_recv(), timeout)


@pytest.mark.asyncio
async def test_full_game_flow(server_url):
    """完整流程: 创建 → 加入 → 开始 → 猜错 → 猜中 → 结束"""
    session1 = aiohttp.ClientSession()
    session2 = aiohttp.ClientSession()
    ws1, _ = await ws_connect(server_url, session1)
    ws2, _ = await ws_connect(server_url, session2)
    try:
        # 1. 创建房间 (服务器会发 room_created + state)
        await ws1.send_json({"type": "create_room", "name": "小明", "target_score": 1})
        created = await recv_until(ws1, "room_created")
        code = created["code"]
        assert len(code) == 6
        initial = await recv_until(ws1, "state")
        assert len(initial["state"]["players"]) == 1

        # 2. 加入房间
        await ws2.send_json({"type": "join_room", "code": code, "name": "小红"})
        joined = await recv_until(ws2, "joined")
        assert joined["code"] == code
        await recv_until(ws1, "player_joined")
        # ws2 收到 state (含 2 名玩家)
        state2 = await recv_until(ws2, "state")
        assert len(state2["state"]["players"]) == 2

        # 3. 开始游戏
        await ws1.send_json({"type": "start_game"})
        await recv_until(ws1, "game_started")
        await recv_until(ws2, "game_started")
        rs1 = await recv_until(ws1, "round_start")
        assert rs1["round"] == 1 and rs1["max_guesses"] == 8

        # 获取目标
        room = list(server.engine.rooms.values())[0]
        target_id = room.target.id

        # 4. 猜错
        wrong = [p for p in server.engine.pool if p.id != target_id][0]
        await ws1.send_json({"type": "guess", "player_id": wrong.id})
        result = await recv_until(ws1, "guess_result")
        assert result["correct"] is False
        assert len(result["colors"]) == 6
        assert len(result["feedback"]) == 6

        # 对手只收到颜色
        opp = await recv_until(ws2, "opponent_guess")
        assert len(opp["colors"]) == 6
        assert "feedback" not in opp

        # 5. 猜中
        await ws2.send_json({"type": "guess", "player_id": target_id})
        result2 = await recv_until(ws2, "guess_result")
        assert result2["correct"] is True

        re1 = await recv_until(ws1, "round_end")
        re2 = await recv_until(ws2, "round_end")
        assert re1["winner"] is not None
        assert re1["target"]["nickname"] == room.target.nickname
        assert re1["reason"] == "correct"

        # 抢1 -> game_over
        go1 = await recv_until(ws1, "game_over")
        assert go1["winner"] == "小红"
    finally:
        await ws1.close()
        await ws2.close()
        await session1.close()
        await session2.close()


@pytest.mark.asyncio
async def test_join_nonexistent_room(server_url):
    session = aiohttp.ClientSession()
    ws, _ = await ws_connect(server_url, session)
    try:
        await ws.send_json({"type": "join_room", "code": "ZZZZZZ", "name": "路人"})
        err = await recv_until(ws, "error")
        assert "房间不存在" in err["message"]
    finally:
        await ws.close()
        await session.close()


@pytest.mark.asyncio
async def test_guess_before_round(server_url):
    session = aiohttp.ClientSession()
    ws, _ = await ws_connect(server_url, session)
    try:
        await ws.send_json({"type": "create_room", "name": "A", "target_score": 1})
        await recv_until(ws, "room_created")
        await ws.send_json({"type": "guess", "player_id": "x"})
        err = await recv_until(ws, "error")
        assert "回合" in err["message"]
    finally:
        await ws.close()
        await session.close()


@pytest.mark.asyncio
async def test_http_api(server_url):
    async with aiohttp.ClientSession() as session:
        # 首页
        async with session.get(server_url + "/") as resp:
            assert resp.status == 200
            html = await resp.text()
            assert "猜选手" in html
        # 选手池
        async with session.get(server_url + "/api/players") as resp:
            assert resp.status == 200
            players = await resp.json()
            assert len(players) >= 170
        # 搜索
        async with session.get(server_url + "/api/search?q=kar") as resp:
            results = await resp.json()
            assert len(results) >= 1
            assert "kar" in results[0]["nickname"].lower()
