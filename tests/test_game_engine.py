"""游戏引擎单元测试"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from game_engine import (  # noqa: E402
    GameEngine, Player, evaluate_guess, compare_country, compare_team,
    compare_age, compare_major, compare_role, compare_top,
    MAX_GUESSES, ROUND_TIME,
)

DATA = json.loads((Path(__file__).parent.parent / "data" / "players.json").read_text(encoding="utf-8"))


def make_player(**kw) -> Player:
    base = dict(id="x1", nickname="test", full_name="", country="Denmark",
                continent="欧洲", team="Falcons", age=25, major_count=1,
                role="步枪手", peak_top=5, past_teams=[], is_caster=False)
    base.update(kw)
    return Player.from_dict(base)


def test_engine_loads_data():
    eng = GameEngine()
    assert len(eng.pool) >= 140


def test_find_and_search():
    eng = GameEngine()
    p = eng.find_player(eng.pool[0].id)
    assert p is not None
    results = eng.search_players("kar")
    assert len(results) >= 1
    assert results[0]["nickname"].lower().startswith("kar")


def test_compare_country_same():
    g = make_player(country="Denmark", continent="欧洲")
    t = make_player(country="Denmark", continent="欧洲")
    assert compare_country(g, t)["color"] == "green"


def test_compare_country_same_continent():
    g = make_player(country="Sweden", continent="欧洲")
    t = make_player(country="Denmark", continent="欧洲")
    assert compare_country(g, t)["color"] == "yellow"


def test_compare_country_cis_separate():
    # CIS 单独一区: 俄罗斯 vs 丹麦 -> 灰色 (即使都算欧洲之外)
    g = make_player(country="Russia", continent="CIS")
    t = make_player(country="Denmark", continent="欧洲")
    assert compare_country(g, t)["color"] == "gray"


def test_compare_country_cis_same():
    g = make_player(country="Russia", continent="CIS")
    t = make_player(country="Kazakhstan", continent="CIS")
    assert compare_country(g, t)["color"] == "yellow"


def test_compare_country_ukraine_europe():
    # 乌克兰属于欧洲: 乌克兰 vs 丹麦 同洲 -> 黄
    g = make_player(country="Ukraine", continent="欧洲")
    t = make_player(country="Denmark", continent="欧洲")
    assert compare_country(g, t)["color"] == "yellow"
    # 乌克兰 vs 俄罗斯 (CIS) -> 灰
    t2 = make_player(country="Russia", continent="CIS")
    assert compare_country(g, t2)["color"] == "gray"


def test_compare_team_same():
    g = make_player(team="Falcons")
    t = make_player(team="Falcons")
    assert compare_team(g, t)["color"] == "green"


def test_compare_team_past_team():
    # 目标曾效力 Falcons -> guess Falcons 为黄色
    t = make_player(team="FaZe", past_teams=["Falcons", "MOUZ"])
    g = make_player(team="Falcons")
    assert compare_team(g, t)["color"] == "yellow"


def test_compare_team_no_relation():
    g = make_player(team="Spirit")
    t = make_player(team="FaZe", past_teams=["MOUZ"])
    assert compare_team(g, t)["color"] == "gray"


def test_compare_age_arrows():
    g = make_player(age=20)
    t = make_player(age=30)
    fb = compare_age(g, t)
    assert fb["color"] == "gray" and fb["arrow"] == "↑"
    g2 = make_player(age=40)
    fb2 = compare_age(g2, t)
    assert fb2["color"] == "gray" and fb2["arrow"] == "↓"
    g3 = make_player(age=30)
    assert compare_age(g3, t)["arrow"] == "="


def test_compare_major_arrows():
    g = make_player(major_count=0)
    t = make_player(major_count=3)
    assert compare_major(g, t)["arrow"] == "↑"
    g2 = make_player(major_count=4)
    assert compare_major(g2, t)["arrow"] == "↓"


def test_compare_role():
    g = make_player(role="狙击手")
    t = make_player(role="狙击手")
    assert compare_role(g, t)["color"] == "green"
    g2 = make_player(role="步枪手")
    assert compare_role(g2, t)["color"] == "gray"


def test_compare_top_arrows():
    g = make_player(peak_top=15)
    t = make_player(peak_top=5)
    fb = compare_top(g, t)
    assert fb["color"] == "gray" and fb["arrow"] == "↓"  # 15 比 5 差
    g2 = make_player(peak_top=2)
    assert compare_top(g2, t)["arrow"] == "↑"            # 2 比 5 好但不同
    g3 = make_player(peak_top=5)
    assert compare_top(g3, t)["color"] == "green"


def test_compare_top_outside20():
    # 目标 >20, 猜 >20 -> 绿; 猜 15 -> 灰 + ↑
    t = make_player(peak_top=">20")
    g = make_player(peak_top=">20")
    assert compare_top(g, t)["color"] == "green"
    g2 = make_player(peak_top=15)
    fb = compare_top(g2, t)
    assert fb["color"] == "gray" and fb["arrow"] == "↑"


def test_evaluate_guess_full():
    g = make_player()
    t = make_player()
    feedback, colors = evaluate_guess(g, t)
    assert len(colors) == 6
    assert colors == ["green"] * 6
    assert set(feedback.keys()) == {"国家", "战队", "年龄", "Major", "位置", "最高Top"}


def test_room_lifecycle():
    eng = GameEngine()
    room, sid1 = eng.create_room("小明", target_score=2)
    room2, sid2, err = eng.join_room(room.code, "小红")
    assert room2 is room and err == ""
    assert len(room.players) == 2

    eng.start_game(room)
    assert eng.start_round(room) is True
    assert room.round_active
    assert room.target is not None

    # 提交猜测
    result, err = eng.submit_guess(room, sid1, room.target.id)
    assert err == "" and result["correct"] is True

    # 结束回合
    res = eng.end_round(room, winner_sid=sid1, reason="correct")
    assert res["winner"] == sid1
    assert room.players[sid1].score == 1
    assert room.game_over is False  # 抢2 未到


def test_game_over():
    eng = GameEngine()
    room, sid1 = eng.create_room("A", target_score=1)
    room2, sid2, _ = eng.join_room(room.code, "B")
    eng.start_game(room)
    eng.start_round(room)
    res = eng.end_round(room, winner_sid=sid1, reason="correct")
    assert res.get("game_over") is True
    assert room.winner == sid1


def test_guess_limits():
    eng = GameEngine()
    room, sid1 = eng.create_room("A")
    eng.start_game(room)
    eng.start_round(room)
    target_id = room.target.id
    other = [p for p in eng.pool if p.id != target_id][0]
    for i in range(MAX_GUESSES):
        result, err = eng.submit_guess(room, sid1, other.id)
        assert err == ""
    result, err = eng.submit_guess(room, sid1, other.id)
    assert err != ""  # 第 9 次被拒绝


def test_timeout_end_round():
    eng = GameEngine()
    room, sid1 = eng.create_room("A")
    eng.start_game(room)
    eng.start_round(room)
    res = eng.end_round(room, reason="timeout")
    assert res["reason"] == "timeout"
    assert res["winner"] is None


def test_exhausted_detection():
    eng = GameEngine()
    room, sid1 = eng.create_room("A")
    eng.start_game(room)
    eng.start_round(room)
    other = [p for p in eng.pool if p.id != room.target.id][0]
    for i in range(MAX_GUESSES):
        eng.submit_guess(room, sid1, other.id)
    res = eng.end_round(room, reason="timeout")
    assert res["reason"] == "exhausted"


def test_remove_player_cleans_room():
    eng = GameEngine()
    room, sid1 = eng.create_room("A")
    room2, sid2, _ = eng.join_room(room.code, "B")
    eng.remove_player(sid2)
    assert sid2 not in room.players
    eng.remove_player(sid1)
    assert room.code not in eng.rooms  # 空房间删除


def test_room_code_unique():
    eng = GameEngine()
    rooms = set()
    for i in range(50):
        room, _ = eng.create_room(f"P{i}")
        assert room.code not in rooms
        rooms.add(room.code)


def test_round_end_scores_after_increment():
    """round_end 的 scores 必须包含加分后的最新比分 (回归测试)"""
    eng = GameEngine()
    room, sid1 = eng.create_room("A", target_score=3)
    room2, sid2, _ = eng.join_room(room.code, "B")
    eng.start_game(room)
    eng.start_round(room)
    res = eng.end_round(room, winner_sid=sid1, reason="correct")
    # 加分后: sid1 应为 1 分
    assert res["scores"][sid1] == 1, f"scores 应为加分后比分: {res['scores']}"
    assert room.players[sid1].score == 1


def test_rematch_resets_scores():
    """再来一局后所有玩家分数归零"""
    eng = GameEngine()
    room, sid1 = eng.create_room("A", target_score=1)
    room2, sid2, _ = eng.join_room(room.code, "B")
    eng.start_game(room)
    eng.start_round(room)
    eng.end_round(room, winner_sid=sid1, reason="correct")
    assert room.players[sid1].score == 1
    assert room.game_over is True
    # 再来一局
    eng.start_game(room)
    assert room.players[sid1].score == 0
    assert room.players[sid2].score == 0
    assert room.game_over is False
    assert room.winner is None
