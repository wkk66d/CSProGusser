"""CS2 猜选手游戏 - 游戏逻辑引擎
负责: 选手池加载、房间管理、回合状态机、反馈算法。
不依赖网络层, 便于单元测试。
"""
import asyncio
import json
import random
import string
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROUND_TIME = 120          # 每小局 2 分钟
MAX_GUESSES = 8           # 每局最多猜测次数
BETWEEN_ROUNDS = 5        # 回合间展示结果秒数
DATA_FILE = Path(__file__).parent / "data" / "players.json"


# ---------- 数据模型 ----------

@dataclass
class Player:
    id: str
    nickname: str
    full_name: str
    country: str
    continent: str
    team: str
    age: int
    major_count: int
    role: str
    peak_top: object  # int (1-20) 或 ">20"
    past_teams: list
    is_caster: bool = False
    country_zh: str = ""  # 中文国家名

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(
            id=str(d["id"]), nickname=d["nickname"], full_name=d.get("full_name", ""),
            country=d["country"], country_zh=d.get("country_zh", d["country"]),
            continent=d["continent"], team=d["team"],
            age=d["age"], major_count=d["major_count"], role=d["role"],
            peak_top=d["peak_top"], past_teams=d.get("past_teams", []),
            is_caster=d.get("is_caster", False),
        )


@dataclass
class GuessRecord:
    """一次猜测及其反馈"""
    player: Player
    feedback: dict          # {attr: {"color": str, "value": str, "arrow": str}}
    colors: list            # 6 个颜色序列 (给对手显示)


@dataclass
class PlayerState:
    session_id: str
    name: str
    score: int = 0
    guesses_this_round: list = field(default_factory=list)  # list[GuessRecord]


@dataclass
class Room:
    code: str
    players: dict = field(default_factory=dict)   # session_id -> PlayerState
    host_id: Optional[str] = None
    target_score: int = 2                          # 抢 N
    target: Optional[Player] = None
    round_number: int = 0
    round_active: bool = False
    round_start_time: float = 0.0
    round_ended_at: float = 0.0
    game_over: bool = False
    winner: Optional[str] = None
    used_targets: set = field(default_factory=set) # 已用过的目标
    waiting: bool = True                           # 等待开始
    last_activity: float = field(default_factory=time.time)  # 最后活动时间

    def player_scores(self) -> dict:
        return {sid: ps.score for sid, ps in self.players.items()}


# ---------- 反馈算法 ----------

# 6 项属性的中文标签 (固定顺序)
ATTR_LABELS = ["国家", "战队", "年龄", "Major", "位置", "最高Top"]


def compare_country(guess: Player, target: Player) -> dict:
    cn = guess.country_zh or guess.country
    if guess.country == target.country:
        return {"color": "green", "value": cn, "arrow": ""}
    if guess.continent == target.continent and guess.continent != "其他":
        return {"color": "yellow", "value": cn, "arrow": ""}
    return {"color": "gray", "value": cn, "arrow": ""}


def compare_team(guess: Player, target: Player) -> dict:
    if guess.team == target.team:
        return {"color": "green", "value": guess.team, "arrow": ""}
    # 目标选手曾效力过 本轮猜测选手所在战队 -> 黄色
    if guess.team != "自由身" and guess.team in target.past_teams:
        return {"color": "yellow", "value": guess.team, "arrow": ""}
    return {"color": "gray", "value": guess.team, "arrow": ""}


def compare_number(guess_val, target_val, close_range=0) -> dict:
    """通用数值比较: 返回颜色与箭头, close_range 内标黄."""
    if guess_val == target_val:
        return {"color": "green", "value": str(guess_val), "arrow": "="}
    if close_range and abs(guess_val - target_val) <= close_range:
        arrow = "↑" if guess_val < target_val else "↓"
        return {"color": "yellow", "value": str(guess_val), "arrow": arrow}
    if guess_val < target_val:
        return {"color": "gray", "value": str(guess_val), "arrow": "↑"}  # 目标更高
    return {"color": "gray", "value": str(guess_val), "arrow": "↓"}      # 目标更低


def compare_age(guess: Player, target: Player) -> dict:
    return compare_number(guess.age, target.age, close_range=3)


def compare_major(guess: Player, target: Player) -> dict:
    return compare_number(guess.major_count, target.major_count, close_range=1)


def compare_role(guess: Player, target: Player) -> dict:
    if guess.role == target.role:
        return {"color": "green", "value": guess.role, "arrow": ""}
    return {"color": "gray", "value": guess.role, "arrow": ""}


def top_value(p: Player) -> object:
    """Top20 数值化: ">20" -> 21 (用于比较)"""
    return p.peak_top if isinstance(p.peak_top, int) else 21


def compare_top(guess: Player, target: Player) -> dict:
    gv, tv = top_value(guess), top_value(target)
    if gv == tv:
        return {"color": "green", "value": str(guess.peak_top), "arrow": "="}
    # 仅对数值 Top20 做相近标黄 (差值 ≤3)
    if isinstance(guess.peak_top, int) and isinstance(target.peak_top, int):
        if abs(gv - tv) <= 3:
            arrow = "↑" if gv < tv else "↓"
            return {"color": "yellow", "value": str(guess.peak_top), "arrow": arrow}
    if gv < tv:
        return {"color": "gray", "value": str(guess.peak_top), "arrow": "↑"}
    return {"color": "gray", "value": str(guess.peak_top), "arrow": "↓"}


COMPARATORS = [compare_country, compare_team, compare_age, compare_major, compare_role, compare_top]


def evaluate_guess(guess: Player, target: Player) -> tuple[dict, list]:
    """评估一次猜测, 返回 (feedback dict, colors 列表)"""
    feedback = {}
    colors = []
    for label, fn in zip(ATTR_LABELS, COMPARATORS):
        fb = fn(guess, target)
        feedback[label] = fb
        colors.append(fb["color"])
    return feedback, colors


# ---------- 游戏引擎 ----------

class GameEngine:
    def __init__(self, players_data: list = None):
        self._pool: list[Player] = []
        self.rooms: dict[str, Room] = {}
        self.load_players(players_data)

    def load_players(self, players_data: list = None) -> None:
        if players_data is None:
            players_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        self._pool = [Player.from_dict(d) for d in players_data]

    @property
    def pool(self) -> list[Player]:
        return self._pool

    def find_player(self, player_id: str) -> Optional[Player]:
        for p in self._pool:
            if p.id == player_id:
                return p
        return None

    # 数字↔字母归一化: 配对整体替换为规范形式, 确保 b1t↔bit 相互匹配
    _LEET_PAIRS = [("0", "o"), ("1", "i"), ("3", "e"), ("4", "a"), ("5", "s"), ("7", "t")]

    @classmethod
    def _normalize(cls, s: str) -> str:
        """归一化: 将数字/字母配对统一替换为占位符, 使 b1t=bit."""
        s = s.lower()
        for d, l in cls._LEET_PAIRS:
            s = s.replace(d, "_").replace(l, "_")
        return s

    def search_players(self, query: str, limit: int = 8) -> list[dict]:
        """按昵称搜索, 优先首字母匹配 + 支持数字替换模糊匹配."""
        q = query.lower().strip()
        if not q:
            return []
        q_norm = self._normalize(q)
        results = []
        for p in self._pool:
            nick = p.nickname.lower()
            nick_norm = self._normalize(nick)
            score = 0
            # 首字母精确匹配 (输入 b → b1t 优先于 Aleksib)
            if nick.startswith(q):
                score = 100
            elif nick_norm.startswith(q_norm):
                score = 90
            # 包含匹配
            elif q in nick:
                score = 50
            elif q_norm in nick_norm:
                score = 40
            else:
                continue
            results.append((score, {
                "id": p.id, "nickname": p.nickname, "team": p.team,
                "country": p.country, "role": p.role,
            }))
        # 按分数降序, 同分按昵称长度升序(越短越匹配), 再按字母序
        results.sort(key=lambda r: (-r[0], len(r[1]["nickname"]), r[1]["nickname"].lower()))
        return [r[1] for r in results[:limit]]

    # ---- 房间管理 ----

    @staticmethod
    def gen_code() -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def create_room(self, host_name: str, target_score: int = 2) -> tuple[Room, str]:
        code = self.gen_code()
        while code in self.rooms:
            code = self.gen_code()
        room = Room(code=code, target_score=min(max(target_score, 1), 99))
        sid = self._new_session_id()
        room.players[sid] = PlayerState(session_id=sid, name=host_name or "房主")
        room.host_id = sid
        room.last_activity = time.time()
        self.rooms[code] = room
        return room, sid

    def join_room(self, code: str, name: str) -> tuple[Optional[Room], Optional[str], str]:
        room = self.rooms.get(code.upper().strip())
        if not room:
            return None, None, "房间不存在"
        if room.game_over:
            return None, None, "游戏已结束"
        sid = self._new_session_id()
        room.players[sid] = PlayerState(session_id=sid, name=name or "玩家")
        room.last_activity = time.time()
        return room, sid, ""

    def _new_session_id(self) -> str:
        return f"s{int(time.time()*1000)}{random.randint(100, 999)}"

    def get_room_by_session(self, sid: str) -> Optional[Room]:
        for room in self.rooms.values():
            if sid in room.players:
                return room
        return None

    def remove_player(self, sid: str) -> Optional[Room]:
        room = self.get_room_by_session(sid)
        if not room:
            return None
        room.players.pop(sid, None)
        if room.host_id == sid:
            room.host_id = next(iter(room.players), None)
        if not room.players:
            self.rooms.pop(room.code, None)
        return room

    # ---- 回合生命周期 ----

    def start_game(self, room: Room) -> None:
        room.round_number = 0
        room.game_over = False
        room.winner = None
        room.used_targets = set()
        for ps in room.players.values():
            ps.score = 0

    def start_round(self, room: Room) -> bool:
        """开始新回合, 返回是否成功"""
        if room.game_over or not room.players:
            return False
        # 选择目标 (排除已用过)
        candidates = [p for p in self._pool if p.id not in room.used_targets]
        if not candidates:
            room.used_targets = set()
            candidates = list(self._pool)
        room.target = random.choice(candidates)
        room.used_targets.add(room.target.id)
        room.round_number += 1
        room.round_active = True
        room.round_ended_at = 0.0
        room.round_start_time = time.time()
        for ps in room.players.values():
            ps.guesses_this_round = []
        return True

    def submit_guess(self, room: Room, sid: str, player_id: str) -> tuple[Optional[dict], str]:
        """提交猜测, 返回 (guess_result, error) 或 ("exhausted", result)"""
        ps = room.players.get(sid)
        if not ps:
            return None, "未加入房间"
        if not room.round_active:
            return None, "回合未开始"
        room.last_activity = time.time()
        if len(ps.guesses_this_round) >= MAX_GUESSES:
            return None, f"本轮猜测次数已用完 ({MAX_GUESSES}/{MAX_GUESSES})"
        guess = self.find_player(player_id)
        if guess is None:
            return None, "选手不存在"
        feedback, colors = evaluate_guess(guess, room.target)
        record = GuessRecord(player=guess, feedback=feedback, colors=colors)
        ps.guesses_this_round.append(record)
        is_correct = colors == ["green"] * 6

        # 检查是否所有人猜测次数均耗尽
        all_exhausted = all(
            len(p.guesses_this_round) >= MAX_GUESSES
            for p in room.players.values()
        )

        result = {
            "correct": is_correct,
            "guess_number": len(ps.guesses_this_round),
            "guesses_left": MAX_GUESSES - len(ps.guesses_this_round),
            "guess_nickname": guess.nickname,
            "feedback": {k: v for k, v in feedback.items()},
            "colors": colors,
            "all_exhausted": all_exhausted,
        }
        return result, ""

    def round_time_left(self, room: Room, now: float = None) -> float:
        if not room.round_active:
            return 0
        now = now or time.time()
        return max(0.0, ROUND_TIME - (now - room.round_start_time))

    # ---- 回合结束 ----

    def end_round(self, room: Room, winner_sid: Optional[str] = None,
                  reason: str = "timeout") -> dict:
        """结束当前回合, 返回结果信息"""
        if not room.round_active:
            return {}
        room.round_active = False
        room.round_ended_at = time.time()

        result = {
            "round": room.round_number,
            "winner": winner_sid,
            "reason": reason,          # correct / timeout / exhausted
            "target": self._target_summary(room.target),
            "scores": room.player_scores(),
        }

        if winner_sid:
            room.players[winner_sid].score += 1
            if room.players[winner_sid].score >= room.target_score:
                room.game_over = True
                room.winner = winner_sid
                result["game_over"] = True
                result["final_winner"] = room.players[winner_sid].name

        # 检查是否所有人都用完猜测
        if reason == "timeout" and all(
            len(ps.guesses_this_round) >= MAX_GUESSES for ps in room.players.values()
        ):
            reason = "exhausted"
            result["reason"] = reason

        return result

    def _target_summary(self, target: Player) -> dict:
        """回合结束后向所有人展示目标信息"""
        return {
            "nickname": target.nickname,
            "full_name": target.full_name,
            "country": target.country,
            "team": target.team,
            "age": target.age,
            "major_count": target.major_count,
            "role": target.role,
            "peak_top": str(target.peak_top),
        }

    # ---- 清理 ----

    def cleanup_stale_rooms(self, max_idle: float = 2 * 3600) -> int:
        """清理超过 max_idle 秒无活动的房间, 返回清理数量"""
        now = time.time()
        stale = [code for code, room in self.rooms.items()
                 if now - room.last_activity > max_idle]
        for code in stale:
            self.rooms.pop(code, None)
        return len(stale)

    # ---- 查询 ----

    def room_public_state(self, room: Room, sid: str) -> dict:
        """给某客户端发送的房间公共状态"""
        return {
            "code": room.code,
            "target_score": room.target_score,
            "round_number": room.round_number,
            "round_active": room.round_active,
            "game_over": room.game_over,
            "winner_name": room.players[room.winner].name if room.winner else None,
            "scores": room.player_scores(),
            "players": [
                {"session_id": k, "name": v.name, "score": v.score}
                for k, v in room.players.items()
            ],
            "host_id": room.host_id,
            "you": sid,
            "time_left": int(self.round_time_left(room)),
            "max_guesses": MAX_GUESSES,
        }
