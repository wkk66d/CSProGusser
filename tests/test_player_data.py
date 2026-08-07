"""选手数据完整性测试"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLAYERS = json.loads((ROOT / "data" / "players.json").read_text(encoding="utf-8"))

VALID_ROLES = {"步枪手", "狙击手", "教练", "解说"}
VALID_CONTINENTS = {"CIS", "欧洲", "亚洲", "北美洲", "南美洲", "大洋洲", "非洲"}

def test_player_count():
    """选手总数 >= 170 (24队*5 + 24教练 + 冠军 + 4解说)"""
    assert len(PLAYERS) >= 170, f"选手太少: {len(PLAYERS)}"

def test_unique_ids():
    """ID 唯一"""
    ids = [p["id"] for p in PLAYERS]
    assert len(ids) == len(set(ids)), "存在重复 ID"

def test_required_fields():
    """所有必填字段存在且非空"""
    for p in PLAYERS:
        assert p["nickname"], f"缺少昵称: {p}"
        assert p["country"], f"{p['nickname']} 缺少国家"
        assert p["continent"] in VALID_CONTINENTS, f"{p['nickname']} 大洲无效: {p['continent']}"
        assert p["team"], f"{p['nickname']} 缺少队伍"
        assert isinstance(p["age"], int) and 16 <= p["age"] <= 45, f"{p['nickname']} 年龄异常: {p['age']}"
        assert isinstance(p["major_count"], int) and 0 <= p["major_count"] <= 10, f"{p['nickname']} Major 数异常"
        assert p["role"] in VALID_ROLES, f"{p['nickname']} 位置无效: {p['role']}"
        assert p["peak_top"] == ">20" or (isinstance(p["peak_top"], int) and 1 <= p["peak_top"] <= 20), \
            f"{p['nickname']} Top 位无效: {p['peak_top']}"

def test_casters_present():
    """4 名解说员必须存在"""
    casters = [p["nickname"] for p in PLAYERS if p["is_caster"]]
    assert "MachineWJQ" in casters, "缺少 MachineWJQ"
    assert "Banks" in casters, "缺少 Banks"
    assert "machine" in casters, "缺少 machine"
    assert "SPUNJ" in casters, "缺少 SPUNJ"

def test_teams_represented():
    """全部 24 支目标队伍都有选手"""
    rosters = json.loads((ROOT / "data" / "rosters.json").read_text(encoding="utf-8"))
    for tname in rosters:
        members = [p for p in PLAYERS if p["team"] == tname]
        assert len(members) >= 5, f"队伍 {tname} 选手不足: {len(members)}"

def test_bcgame_players():
    """BC.Game 选手 (s1mple, electroNic, Senzu, TaZ 教练) 存在"""
    by_nick = {p["nickname"].lower(): p for p in PLAYERS}
    assert by_nick["s1mple"]["team"] == "BC.Game", "s1mple 应在 BC.Game"
    assert by_nick["electronic"]["team"] == "BC.Game", "electroNic 应在 BC.Game"
    assert by_nick["senzu"]["team"] == "BC.Game", "Senzu 应在 BC.Game"
    assert by_nick["taz"]["team"] == "BC.Game", "TaZ 应在 BC.Game (教练)"
    assert by_nick["taz"]["role"] == "教练", "TaZ 应为教练"
    assert by_nick["magisk"]["team"] == "BC.Game", "Magisk 应在 BC.Game"

def test_known_players():
    """关键选手存在"""
    nicks = {p["nickname"].lower() for p in PLAYERS}
    for n in ["karrigan", "niko", "donk", "zywoo", "s1mple", "device", "guardian", "kennyS", "coldzera"]:
        assert n.lower() in nicks, f"缺少关键选手: {n}"

def test_awpers_correct():
    """各队主狙击手角色正确"""
    by_nick = {p["nickname"].lower(): p for p in PLAYERS}
    for nick in ["m0nesy", "sh1ro", "zywoo", "torzsi", "w0nderful", "device", "s1mple", "guardian", "kennys"]:
        assert by_nick[nick.lower()]["role"] == "狙击手", f"{nick} 应为狙击手"

def test_top20_known_players():
    """知名选手 Top20 排名正确"""
    by_nick = {p["nickname"].lower(): p for p in PLAYERS}
    assert by_nick["zywoo"]["peak_top"] == 1, "ZywOo 应为 Top1"
    assert by_nick["donk"]["peak_top"] == 1, "donk 应为 Top1"
    assert by_nick["s1mple"]["peak_top"] == 1, "s1mple 应为 Top1"
    assert by_nick["device"]["peak_top"] == 2, "device 应为 Top2"
    assert by_nick["niko"]["peak_top"] == 2, "NiKo 应为 Top2"
