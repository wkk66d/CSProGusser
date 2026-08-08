"""构建最终 data/players.json
合并: 抓取的选手详情 + 角色核实 + Top20 + 大洲分类 + 解说员。

所有数据来源:
- 选手详情: HLTV.org player 页面 (curl_cffi 抓取)
- Top20: HLTV.org 年度 Top20 文章 (2013-2025)
- 角色: 经网络搜索核实的各队阵容角色 (AWPer 表)
- 解说员: 网络搜索核实 (真实姓名/国家/出生日期)
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

# ---- 角色核实表 (经网络搜索) ----
# 每队主狙击手 (AWPer)
AWPER_BY_TEAM = {
    "Falcons": ["m0nesy"],
    "Spirit": ["sh1ro"],
    "FURIA": ["molodoy"],
    "Vitality": ["zywoo"],
    "MOUZ": ["torzsi"],
    "NaVi": ["w0nderful"],
    "9z": ["meyern"],
    "Aurora": ["woxic"],
    "G2": ["r1nkle"],
    "BetBoom": ["zorte"],
    "FaZe": ["jboen"],
    "Legacy": ["try"],
    "Astralis": ["phzy"],
    "The MongolZ": ["910"],
    "PARIVISION": ["jame"],
    "Liquid": ["jorko"],
    "3DMAX": ["maka"],
    "paiN": ["saffee"],
    "MIBR": ["nqz"],
    "TYLOO": ["jee"],
    "Ninjas in Pajamas": ["stavn"],
    "HEROIC": ["martinezsa"],
    "Lynn Vision": ["z4kr"],
    "100 Thieves": ["device"],
}

# 退役/历史选手中的狙击手 (经搜索核实: kennyS, GuardiaN, JW, Skadoodle, s1mple)
LEGEND_AWPERS = {"kennys", "guardian", "jw", "skadoodle", "s1mple"}

# ---- 大洲划分 (CIS 单独, 乌克兰属于欧洲) ----
CIS = {"Russia", "Belarus", "Kazakhstan", "Uzbekistan", "Kyrgyzstan",
       "Armenia", "Azerbaijan", "Georgia", "Moldova", "Tajikistan"}
EUROPE = {"Denmark", "Sweden", "Norway", "Finland", "Germany", "France", "UK",
          "United Kingdom", "Poland", "Spain", "Portugal", "Netherlands", "Belgium",
          "Switzerland", "Austria", "Czech Republic", "Slovakia", "Hungary", "Romania",
          "Bulgaria", "Serbia", "Croatia", "Slovenia", "Bosnia and Herzegovina",
          "Montenegro", "North Macedonia", "Albania", "Greece", "Turkey", "Türkiye",
          "Estonia", "Latvia", "Lithuania", "Israel", "Kosovo", "Ukraine"}
ASIA = {"China", "Mongolia", "South Korea", "Japan", "India", "Indonesia",
        "Malaysia", "Philippines", "Thailand", "Vietnam", "Singapore", "Hong Kong"}
NORTH_AMERICA = {"USA", "United States", "Canada", "Mexico", "Guatemala"}
SOUTH_AMERICA = {"Brazil", "Argentina", "Chile", "Colombia", "Uruguay", "Peru",
                 "Ecuador", "Paraguay", "Bolivia", "Venezuela"}
OCEANIA = {"Australia", "New Zealand"}
AFRICA = {"South Africa"}

# ---- 国家名中英对照 ----
COUNTRY_ZH = {
    "Denmark": "丹麦", "Sweden": "瑞典", "Norway": "挪威", "Finland": "芬兰",
    "Germany": "德国", "France": "法国", "UK": "英国", "United Kingdom": "英国",
    "Poland": "波兰", "Spain": "西班牙", "Portugal": "葡萄牙", "Netherlands": "荷兰",
    "Belgium": "比利时", "Switzerland": "瑞士", "Austria": "奥地利",
    "Czech Republic": "捷克", "Slovakia": "斯洛伐克", "Hungary": "匈牙利",
    "Romania": "罗马尼亚", "Bulgaria": "保加利亚", "Serbia": "塞尔维亚",
    "Croatia": "克罗地亚", "Slovenia": "斯洛文尼亚",
    "Bosnia and Herzegovina": "波黑", "Montenegro": "黑山",
    "North Macedonia": "北马其顿", "Albania": "阿尔巴尼亚", "Greece": "希腊",
    "Turkey": "土耳其", "Türkiye": "土耳其",
    "Estonia": "爱沙尼亚", "Latvia": "拉脱维亚", "Lithuania": "立陶宛",
    "Israel": "以色列", "Kosovo": "科索沃",
    "Russia": "俄罗斯", "Ukraine": "乌克兰", "Belarus": "白俄罗斯",
    "Kazakhstan": "哈萨克斯坦", "Uzbekistan": "乌兹别克斯坦",
    "Kyrgyzstan": "吉尔吉斯斯坦", "Armenia": "亚美尼亚", "Azerbaijan": "阿塞拜疆",
    "Georgia": "格鲁吉亚", "Moldova": "摩尔多瓦", "Tajikistan": "塔吉克斯坦",
    "China": "中国", "Mongolia": "蒙古", "South Korea": "韩国", "Japan": "日本",
    "India": "印度", "Indonesia": "印度尼西亚", "Malaysia": "马来西亚",
    "Philippines": "菲律宾", "Thailand": "泰国", "Vietnam": "越南",
    "Singapore": "新加坡", "Hong Kong": "中国香港",
    "USA": "美国", "United States": "美国", "Canada": "加拿大", "Mexico": "墨西哥",
    "Guatemala": "危地马拉",
    "Brazil": "巴西", "Argentina": "阿根廷", "Chile": "智利",
    "Colombia": "哥伦比亚", "Uruguay": "乌拉圭", "Peru": "秘鲁",
    "Ecuador": "厄瓜多尔", "Paraguay": "巴拉圭", "Bolivia": "玻利维亚",
    "Venezuela": "委内瑞拉",
    "Australia": "澳大利亚", "New Zealand": "新西兰",
    "South Africa": "南非",
}

def continent_of(country: str) -> str:
    if country in CIS:
        return "CIS"
    if country in EUROPE:
        return "欧洲"
    if country in ASIA:
        return "亚洲"
    if country in NORTH_AMERICA:
        return "北美洲"
    if country in SOUTH_AMERICA:
        return "南美洲"
    if country in OCEANIA:
        return "大洋洲"
    if country in AFRICA:
        return "非洲"
    return "其他"

# ---- 解说员 (网络搜索核实) ----
# MachineWJQ(玩机器Machine): 刘亦博, 中国, 1996-01-11
# Banks: James Banks, 英国, 1990-05-13
# machine: Alex Richardson, 英国, 1993-08-31
# SPUNJ: Chad Burchill, 澳大利亚, 1989-07-24
CASTERS = [
    {
        "id": "caster_machine_wjq", "nickname": "MachineWJQ", "full_name": "刘亦博",
        "country": "China", "continent": "亚洲", "team": "自由身", "age": 30,
        "major_count": 0, "role": "解说", "peak_top": ">20", "past_teams": [],
        "is_caster": True,
    },
    {
        "id": "caster_banks", "nickname": "Banks", "full_name": "James Banks",
        "country": "UK", "continent": "欧洲", "team": "自由身", "age": 36,
        "major_count": 0, "role": "解说", "peak_top": ">20", "past_teams": [],
        "is_caster": True,
    },
    {
        "id": "caster_machine", "nickname": "machine", "full_name": "Alex Richardson",
        "country": "UK", "continent": "欧洲", "team": "自由身", "age": 32,
        "major_count": 0, "role": "解说", "peak_top": ">20", "past_teams": [],
        "is_caster": True,
    },
    {
        "id": "caster_spunj", "nickname": "SPUNJ", "full_name": "Chad Burchill",
        "country": "Australia", "continent": "大洋洲", "team": "自由身", "age": 37,
        "major_count": 0, "role": "解说", "peak_top": ">20", "past_teams": [],
        "is_caster": True,
    },
]

# ---- 手动补充选手 (HLTV 页面无完整数据, 经网络搜索核实) ----
# TaZ: Wiktor Wojtas, 波兰, 1986-06-06, BC.Game 主教练 (2026-01 上任, 经网络搜索核实),
# 曾为 VP 2014 Major 冠军选手
EXTRA_PLAYERS = [
    {
        "id": "extra_taz", "nickname": "TaZ", "full_name": "Wiktor Wojtas",
        "country": "Poland", "continent": "欧洲", "team": "BC.Game", "age": 40,
        "major_count": 1, "role": "教练", "peak_top": ">20",
        "past_teams": ["Virtus.pro", "HONORIS", "Kinguin", "ESC Gaming", "Frag eXecutors"],
        "is_caster": False,
    },
]

def match_top20(raw: dict) -> dict:
    """将 Top20 名单匹配到选手 (昵称归一化), 返回 id -> 最佳排名。"""
    lists = json.loads((DATA / "top20_lists.json").read_text(encoding="utf-8"))

    def norm(s: str) -> str:
        return s.lower().replace("-", "").replace("_", "").replace(".", "").replace("^", "").replace(" ", "")

    nick_best = {}
    for year, lst in lists.items():
        for rank, nick in enumerate(lst, 1):
            if nick == "?":
                continue
            n = norm(nick)
            if n not in nick_best or rank < nick_best[n]:
                nick_best[n] = rank

    result = {}
    for pid, v in raw.items():
        nick = v.get("nickname", "")
        best = nick_best.get(norm(nick))
        if best is None:
            nn = norm(nick)
            for n, r in nick_best.items():
                if nn and (nn in n or n in nn):
                    best = r
                    break
        result[pid] = best if best else ">20"
    return result

# ---- 知名教练白名单 (zonic/B1ad3 级别) ----
FAMOUS_COACHES = {
    "zonic",    # 5x Major 冠军教练 (Astralis ×4 + Falcons ×1)
    "B1ad3",    # Major 冠军教练 (NaVi Copenhagen 2024)
    "hally",    # Major 冠军教练 (Spirit Shanghai 2024)
    "XTQZZZ",   # 2x Major 冠军教练 (Vitality Austin + Budapest 2025)
    "dastan",   # Major 冠军教练 (Outsiders Rio 2022)
    "sAw",      # G2 知名教练
    "sycrone",  # MOUZ 青训体系教练
    "neo",      # 传奇选手转 Astralis 教练
    "TaZ",      # 传奇选手转 BC.Game 教练
    "gla1ve",   # 4x Major 冠军 IGL 转 100T 教练
    "Xizt",     # 传奇选手转 NiP 教练
}

def main():
    raw = json.loads((DATA / "players_raw.json").read_text(encoding="utf-8"))
    top20_map = match_top20(raw)
    rosters = json.loads((DATA / "rosters.json").read_text(encoding="utf-8"))

    # 队伍名 -> 选手 id 集合 (STARTER)
    team_members = {}
    coach_ids = {}
    for tname, r in rosters.items():
        team_members[tname] = {str(p["id"]) for p in r["players"] if p["status"] == "STARTER"}
        if r.get("coach"):
            coach_ids[str(r["coach"]["id"])] = tname

    # 选手 id -> 队伍名
    id_to_team = {}
    for tname, ids in team_members.items():
        for pid in ids:
            id_to_team[pid] = tname

    players = []
    for pid, v in raw.items():
        nick = v["nickname"]
        team = id_to_team.get(pid)
        is_coach = pid in coach_ids
        if is_coach:
            # 仅保留知名教练 (zonic/B1ad3 级别)
            if nick not in FAMOUS_COACHES:
                continue
            team = coach_ids[pid]  # 教练的战队 = 执教队伍
        role = "教练" if is_coach else None
        if role is None:
            role = "狙击手" if nick.lower() in LEGEND_AWPERS else "步枪手"
            # 当前队伍的狙击手
            if team and nick.lower() in {a.lower() for a in AWPER_BY_TEAM.get(team, [])}:
                role = "狙击手"
            # 教练同时是选手的退役冠军 (e.g. zonic 曾为选手) 保持教练角色
        if team is None:
            team = v.get("team") or "自由身"
        # 退役/下放/无队 -> 自由身 (统一为一类)
        if any(x in team for x in ("Retired", "Benched", "Inactive", "No team", "Free agent", "Bench")):
            team = "自由身"
        country = v["country"]
        country_zh = COUNTRY_ZH.get(country, country)
        players.append({
            "id": pid,
            "nickname": nick,
            "full_name": v.get("full_name", ""),
            "country": country,
            "country_zh": country_zh,
            "continent": continent_of(country),
            "team": team,
            "age": v["age"],
            "major_count": v["major_count"],
            "role": role,
            "peak_top": top20_map.get(pid, ">20"),
            "past_teams": v.get("past_teams", []),
            "is_caster": False,
        })

    players.extend(CASTERS)
    players.extend(EXTRA_PLAYERS)

    # 排序: 按昵称
    players.sort(key=lambda p: p["nickname"].lower())

    out = DATA / "players.json"
    out.write_text(json.dumps(players, ensure_ascii=False, indent=2), encoding="utf-8")

    # 统计
    from collections import Counter
    roles = Counter(p["role"] for p in players)
    continents = Counter(p["continent"] for p in players)
    teams = Counter(p["team"] for p in players)
    print(f"总选手数: {len(players)}")
    print(f"角色: {dict(roles)}")
    print(f"大洲: {dict(continents)}")
    print(f"队伍: {len(teams)} 支 (含自由身 {teams.get('自由身', 0)} 人)")
    awpers = [p["nickname"] for p in players if p["role"] == "狙击手"]
    print(f"狙击手({len(awpers)}): {sorted(awpers)}")
    print(f"已写入: {out}")

if __name__ == "__main__":
    main()
