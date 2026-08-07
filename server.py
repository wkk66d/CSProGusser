"""CS2 猜选手游戏 - 服务器
aiohttp: HTTP 静态文件 + WebSocket 游戏服务。
本地运行, 用 cloudflared 映射外网。
"""
import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web, WSMsgType

from game_engine import GameEngine, ROUND_TIME, BETWEEN_ROUNDS, MAX_GUESSES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("csguess")

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
HOST = "0.0.0.0"
PORT = 8899

engine = GameEngine()

# session_id -> WebSocket
connections: dict[str, web.WebSocketResponse] = {}
# HTTP 轮询模式: session_id -> 待取消息队列
poll_queues: dict[str, list] = {}
# 后台任务
timer_tasks: dict[str, asyncio.Task] = {}


# ---------- WebSocket 工具 ----------

def room_of(sid: str):
    return engine.get_room_by_session(sid)


def ws_of(sid: str):
    return connections.get(sid)


async def send(sid: str, msg: dict):
    """发送消息: WS 模式直接推送, HTTP 轮询模式进队列"""
    if sid in poll_queues:
        poll_queues[sid].append(msg)
        return
    ws = connections.get(sid)
    if ws and not ws.closed:
        try:
            await ws.send_json(msg)
        except Exception:
            pass


async def broadcast(room, msg: dict, exclude: str = None):
    for sid in list(room.players.keys()):
        if sid != exclude:
            await send(sid, msg)


def room_public(room, sid: str) -> dict:
    state = engine.room_public_state(room, sid)
    state["players_list"] = [{"session_id": k, "name": v.name, "score": v.score,
                              "guess_count": len(v.guesses_this_round)}
                             for k, v in room.players.items()]
    return state


# ---------- 回合调度 ----------

async def broadcast_timer(room_code: str):
    """每秒广播剩余时间"""
    room = engine.rooms.get(room_code)
    if not room:
        return
    while room.round_active:
        left = int(engine.round_time_left(room))
        await broadcast(room, {"type": "timer", "time_left": left})
        if left <= 0:
            # 时间耗尽, 结束回合
            result = engine.end_round(room, reason="timeout")
            await on_round_end(room, result)
            return
        await asyncio.sleep(1)


async def schedule_next_round(room, delay: float = BETWEEN_ROUNDS):
    """延迟后自动开始下一回合 (若未结束)"""
    await asyncio.sleep(delay)
    if room.code not in engine.rooms:
        return
    room = engine.rooms[room.code]
    if room.game_over or room.round_active:
        return
    if not room.players:
        return
    if not engine.start_round(room):
        return
    await send_round_start(room)


async def on_round_end(room, result: dict):
    """回合结束: 广播结果, 安排下一回合"""
    await broadcast(room, {"type": "round_end", **result})
    if result.get("game_over"):
        await broadcast(room, {"type": "game_over",
                               "winner": room.players[room.winner].name if room.winner else None,
                               "scores": room.player_scores()})
        return
    # 5 秒后自动下一回合
    asyncio.create_task(schedule_next_round(room))


async def send_round_start(room):
    """广播新回合开始"""
    if not room.target:
        return
    msg = {
        "type": "round_start",
        "round": room.round_number,
        "round_time": ROUND_TIME,
        "max_guesses": MAX_GUESSES,
    }
    await broadcast(room, msg)
    # 启动计时器
    t = asyncio.create_task(broadcast_timer(room.code))
    timer_tasks[room.code] = t


# ---------- WebSocket 消息处理 ----------

async def handle_message(ws: web.WebSocketResponse, conn_state: dict, data: dict):
    """处理一条 WebSocket 消息. conn_state = {"sid": str} 可变连接状态"""
    mtype = data.get("type")
    sid = conn_state["sid"]
    room = room_of(sid)

    if mtype == "create_room":
        name = data.get("name", "玩家")
        target_score = int(data.get("target_score", 2))
        room, sid = engine.create_room(name, target_score)
        conn_state["sid"] = sid
        if ws:
            connections[sid] = ws
        else:
            poll_queues[sid] = []   # HTTP 模式注册轮询队列
        await send(sid, {"type": "room_created", "code": room.code, "session_id": sid})
        await send(sid, {"type": "state", "state": room_public(room, sid)})
        return

    if mtype == "join_room":
        code = data.get("code", "")
        name = data.get("name", "玩家")
        room, sid, err = engine.join_room(code, name)
        if err:
            if ws:
                await ws.send_json({"type": "error", "message": err})
            else:
                conn_state["_error"] = err
            return
        conn_state["sid"] = sid
        if ws:
            connections[sid] = ws
        else:
            poll_queues[sid] = []
        await send(sid, {"type": "joined", "code": room.code, "session_id": sid})
        await broadcast(room, {"type": "player_joined",
                               "player": {"session_id": sid, "name": room.players[sid].name}})
        # 向房间内所有玩家广播最新状态 (修复: 房主看不到新加入对手)
        for psid in list(room.players.keys()):
            await send(psid, {"type": "state", "state": room_public(room, psid)})
        return

    if not room:
        await send(sid, {"type": "error", "message": "未加入房间"})
        return

    if mtype == "set_mode":
        if sid == room.host_id and not room.round_active:
            room.target_score = min(max(int(data.get("target_score", 2)), 1), 4)
            await broadcast(room, {"type": "mode_changed", "target_score": room.target_score})
        return

    if mtype == "start_game":
        if sid != room.host_id:
            await send(sid, {"type": "error", "message": "只有房主可以开始"})
            return
        if len(room.players) < 2:
            await send(sid, {"type": "error", "message": "至少需要 2 名玩家"})
            return
        engine.start_game(room)
        await broadcast(room, {"type": "game_started",
                               "target_score": room.target_score,
                               "players": room_public(room, sid)["players_list"]})
        if engine.start_round(room):
            await send_round_start(room)
        return

    if mtype == "guess":
        if not room.round_active:
            await send(sid, {"type": "error", "message": "回合未开始"})
            return
        player_id = str(data.get("player_id", ""))
        result, err = engine.submit_guess(room, sid, player_id)
        if err:
            await send(sid, {"type": "error", "message": err})
            return
        # 私有: 猜测者收到完整反馈
        await send(sid, {"type": "guess_result", **result})
        # 公开: 其他人只收到颜色
        await broadcast(room, {
            "type": "opponent_guess",
            "player_name": room.players[sid].name,
            "player_session": sid,
            "colors": result["colors"],
            "guess_number": result["guess_number"],
        }, exclude=sid)
        if result["correct"]:
            # 有人猜中, 立即结束回合
            await asyncio.sleep(1.5)  # 短暂展示
            if room.round_active:
                res = engine.end_round(room, winner_sid=sid, reason="correct")
                await on_round_end(room, res)
        return

    if mtype == "rematch":
        engine.start_game(room)
        await broadcast(room, {"type": "game_started",
                               "target_score": room.target_score,
                               "players": room_public(room, sid)["players_list"]})
        if engine.start_round(room):
            await send_round_start(room)
        return

    if mtype == "ping":
        await send(sid, {"type": "pong"})
        return


# ---------- WebSocket 入口 ----------

async def ws_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=60)
    await ws.prepare(request)
    log.info(f"WS 连接建立: {request.remote}")
    conn_state = {"sid": ""}  # 连接状态, 由 handle_message 更新

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                await handle_message(ws, conn_state, data)
            except Exception as e:
                log.error(f"消息处理异常: {e}")
                await send(conn_state["sid"], {"type": "error", "message": "消息格式错误"})
        elif msg.type == WSMsgType.ERROR:
            break

    # 断开处理
    sid = conn_state["sid"]
    log.info(f"WS 连接断开: {request.remote} sid={sid or '无'}")
    if sid:
        room = engine.get_room_by_session(sid)
        connections.pop(sid, None)
        if room:
            engine.remove_player(sid)
            await broadcast(room, {"type": "player_left", "session_id": sid,
                                   "name": "玩家"})
            # 同步最新状态给剩余玩家
            for psid in list(room.players.keys()):
                await send(psid, {"type": "state", "state": room_public(room, psid)})
    return ws


# ---------- HTTP 路由 ----------

async def index_handler(request: web.Request):
    resp = web.FileResponse(STATIC / "index.html")
    # 禁止缓存, 避免部署新版本后浏览器仍使用旧前端
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


async def api_players(request: web.Request):
    """选手列表 (自动补全用)"""
    players = [{"id": p.id, "nickname": p.nickname, "full_name": p.full_name,
                "team": p.team, "country": p.country, "role": p.role,
                "continent": p.continent}
               for p in engine.pool]
    return web.json_response(players)


async def api_health(request: web.Request):
    """健康检查 (排查部署问题)"""
    return web.json_response({
        "status": "ok",
        "players": len(engine.pool),
        "rooms": len(engine.rooms),
    })


async def api_action(request: web.Request):
    """HTTP 动作端点 (WS 不可用时的降级方案)
    body: {type: ..., ..., sid: 已有会话ID 或 ""}
    返回: {session_id, messages: [服务器消息...]}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "请求格式错误"}, status=400)
    sid = str(data.pop("sid", ""))
    conn_state = {"sid": sid}
    # 若该 sid 尚无轮询队列, 建立 (用于接收推送消息)
    if conn_state["sid"] and conn_state["sid"] not in poll_queues:
        poll_queues[conn_state["sid"]] = []
    try:
        await handle_message(None, conn_state, data)
    except Exception as e:
        log.error(f"HTTP 动作异常: {e}")
        return web.json_response({"error": str(e)}, status=500)
    err = conn_state.pop("_error", None)
    new_sid = conn_state["sid"]
    if new_sid and new_sid not in poll_queues:
        poll_queues[new_sid] = []
    # 取出该会话积压的消息
    messages = poll_queues.get(new_sid, [])
    poll_queues[new_sid] = []
    return web.json_response({"session_id": new_sid, "messages": messages, "error": err})


async def api_poll(request: web.Request):
    """轮询端点: 取出该会话积压的消息"""
    sid = request.query.get("sid", "")
    if sid in poll_queues:
        messages = poll_queues[sid]
        poll_queues[sid] = []
    else:
        messages = []
    return web.json_response({"messages": messages})


async def api_search(request: web.Request):
    q = request.query.get("q", "")
    return web.json_response(engine.search_players(q))


async def static_handler(request: web.Request):
    path = STATIC / request.match_info["filename"]
    if not path.is_file():
        raise web.HTTPNotFound()
    resp = web.FileResponse(path)
    # 前端资源不缓存, 确保始终加载最新版本
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/api/players", api_players)
    app.router.add_get("/api/search", api_search)
    app.router.add_get("/api/health", api_health)
    app.router.add_post("/api/action", api_action)
    app.router.add_get("/api/poll", api_poll)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/{filename}", static_handler)
    return app


async def cleanup_loop():
    """定期清理无活动房间 (每 10 分钟, 清理 2 小时无活动)"""
    while True:
        await asyncio.sleep(600)
        n = engine.cleanup_stale_rooms()
        if n:
            log.info(f"已清理 {n} 个无活动房间, 剩余 {len(engine.rooms)}")


if __name__ == "__main__":
    log.info(f"启动服务器: http://localhost:{PORT} (选手池 {len(engine.pool)} 人)")
    app = make_app()
    web.run_app(app, host=HOST, port=PORT)
