"""HLTV.org 选手详情抓取脚本
从每位选手的 profile 页面提取: 国家、年龄、当前战队、Major冠军数、曾效力队伍。
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hltv_scraper import fetch_soup, BASE  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

def resolve_player_slug(player_id: int) -> str | None:
    """通过 HLTV 搜索解析选手 slug。"""
    soup = fetch_soup(f"{BASE}/search?query={player_id}")
    if not soup:
        return None
    import re
    for a in soup.select("a[href*='/player/']"):
        m = re.search(rf"/player/{player_id}/([^/#?]+)", a.get("href", ""))
        if m:
            return m.group(1)
    return None

def scrape_player(player_id: int, slug: str | None = None) -> dict | None:
    """抓取单名选手详情。"""
    if slug:
        soup = fetch_soup(f"{BASE}/player/{player_id}/{slug}")
        if soup:
            return parse_player(soup, player_id)
    # 后备: 搜索解析 slug
    slug = resolve_player_slug(player_id)
    if not slug:
        print(f"  [!] 无法解析 slug for player {player_id}")
        return None
    soup = fetch_soup(f"{BASE}/player/{player_id}/{slug}")
    if not soup:
        return None
    return parse_player(soup, player_id)

def parse_player(soup, player_id: int) -> dict:
    """从已抓取的 soup 解析选手详情。"""

    p = {"id": player_id}

    # 昵称
    nick = soup.select_one(".playerNickname")
    if nick:
        p["nickname"] = nick.get_text(" ", strip=True)
    if "nickname" not in p:
        title = soup.select_one("title")
        if title:
            m = re.search(r"'([^']+)'", title.get_text())
            p["nickname"] = m.group(1) if m else None

    # 真名
    real = soup.select_one(".playerRealname")
    if real:
        p["full_name"] = real.get_text(" ", strip=True)

    # 国家
    flag = soup.select_one("img.flag")
    if flag:
        p["country"] = flag.get("title", "").strip()

    # 年龄
    age_el = soup.select_one(".playerAge [itemprop='text']")
    if not age_el:
        age_el = soup.select_one(".playerAge")
    if age_el:
        m = re.search(r"(\d+)\s*(?:year|岁)", age_el.get_text(" ", strip=True))
        p["age"] = int(m.group(1)) if m else None

    # 当前战队
    team_el = soup.select_one(".playerTeam [itemprop='text']")
    if not team_el:
        team_el = soup.select_one(".playerTeam")
    if team_el:
        p["team"] = team_el.get_text(" ", strip=True)

    # Major 冠军数
    maj = soup.select_one(".majorWinner")
    if maj:
        t = maj.get_text(" ", strip=True)
        m = re.search(r"(\d+)\s*x?\s*Major", t)
        p["major_count"] = int(m.group(1)) if m else (1 if "Major winner" in t else 0)
    else:
        p["major_count"] = 0

    # 曾效力队伍 (含当前, 从 achievement/past-team 表格)
    past = []
    for tr in soup.select("tr.past-team, tr"):
        link = tr.select_one("td a[href*='/team/']")
        if link:
            name = link.get_text(" ", strip=True)
            if name and name not in past:
                past.append(name)
    p["past_teams"] = past

    return p

def load_known_players() -> dict:
    """加载已有数据(支持断点续跑)。"""
    f = DATA / "players_raw.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}

def load_extra_ids() -> dict[int, str]:
    """加载额外选手 ID -> 昵称 (CSGO Major 冠军等)。"""
    extra = {}
    for f in ["major_champ_ids.json"]:
        p = DATA / f
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for nick, pid in d.items():
                extra[int(pid)] = nick
    return extra

if __name__ == "__main__":
    rosters = json.loads((DATA / "rosters.json").read_text(encoding="utf-8"))
    known = load_known_players()

    ids = set(known.keys())
    for name, r in rosters.items():
        if r.get("coach"):
            ids.add(str(r["coach"]["id"]))
        for pl in r.get("players", []):
            if pl.get("status") == "STARTER":
                ids.add(str(pl["id"]))
    extra_nicks = load_extra_ids()  # {id: nickname}
    for eid in extra_nicks:
        ids.add(str(eid))

    # 构建 id -> slug 映射 (现役选手 nickname 即 slug, 教练同, 冠军用昵称)
    id_slug = {str(eid): nick for eid, nick in extra_nicks.items()}
    for name, r in rosters.items():
        if r.get("coach"):
            id_slug[str(r["coach"]["id"])] = r["coach"]["nickname"]
        for pl in r.get("players", []):
            if pl.get("status") == "STARTER":
                id_slug[str(pl["id"])] = pl["nickname"]

    # 保持有序
    ordered = sorted(int(i) for i in ids)
    total = len(ordered)
    for idx, pid in enumerate(ordered, 1):
        skey = str(pid)
        if skey in known:
            continue
        data = scrape_player(pid, id_slug.get(skey))
        if data is None:
            print(f"[{idx}/{total}] FAIL id={pid}")
            continue
        known[skey] = data
        print(f"[{idx}/{total}] OK {data.get('nickname', '?')} | {data.get('country')} | {data.get('age')}岁 | {data.get('team')} | Major x{data.get('major_count')} | 曾效力{len(data.get('past_teams', []))}队")
        (DATA / "players_raw.json").write_text(
            json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1.0)

    print(f"\n完成: {len(known)}/{total} 名选手")
