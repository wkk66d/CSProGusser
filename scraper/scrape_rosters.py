"""HLTV.org 队伍阵容抓取脚本
从每支队伍页面提取: 现役选手(STARTER)、教练。
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

def resolve_team_slug(team_id: int, name: str) -> str | None:
    """通过搜索获取队伍 slug。"""
    soup = fetch_soup(f"{BASE}/search?query={name.replace(' ', '%20')}")
    if not soup:
        return None
    for a in soup.select("a[href*='/team/']"):
        m = re.search(rf"/team/{team_id}/([^/]+)", a.get("href", ""))
        if m:
            return m.group(1)
    return None

def scrape_roster(team_id: int, slug: str) -> dict:
    """抓取单支队伍阵容。返回 {coach, players: [{id, nickname, full_name, status}]}"""
    soup = fetch_soup(f"{BASE}/team/{team_id}/{slug}")
    if not soup:
        return None
    roster = soup.select_one("#rosterBox")
    if not roster:
        return None

    result = {"team_id": team_id, "coach": None, "players": []}

    # 教练
    coach_el = roster.select_one("a[href*='/coach/']")
    if coach_el:
        m = re.search(r"/coach/(\d+)/([^/]+)", coach_el.get("href", ""))
        if m:
            result["coach"] = {"id": int(m.group(1)), "nickname": m.group(2)}

    # 选手: 需要 status 为 STARTER
    for row in roster.select("tr"):
        link = row.select_one("td a[href*='/player/']")
        if not link:
            continue
        m = re.search(r"/player/(\d+)/([^/]+)", link.get("href", ""))
        if not m:
            continue
        tds = row.select("td")
        status = tds[1].get_text(" ", strip=True) if len(tds) > 1 else "?"
        img = link.select_one("img")
        full_name = img.get("title", "") if img else ""
        result["players"].append({
            "id": int(m.group(1)),
            "nickname": m.group(2),
            "full_name": full_name,
            "status": status,
        })
    return result

if __name__ == "__main__":
    team_ids = json.loads((DATA / "team_ids.json").read_text(encoding="utf-8"))
    rosters = {}
    for name, tid in team_ids.items():
        slug = resolve_team_slug(tid, name)
        if not slug:
            # 回退: 直接尝试无 slug 的 URL 拿到重定向/或已知常见 slug
            slug = {"Ninjas in Pajamas": "ninjas-in-pyjamas"}.get(name)
        if not slug:
            print(f"[FAIL] {name} ({tid}): 无法解析 slug")
            continue
        r = scrape_roster(tid, slug)
        if r is None:
            print(f"[FAIL] {name} ({tid})")
            continue
        rosters[name] = r
        starters = [p for p in r["players"] if p["status"] == "STARTER"]
        coach = r["coach"]["nickname"] if r["coach"] else "-"
        print(f"[OK] {name}: 教练={coach} 现役={[p['nickname'] for p in starters]}")
        time.sleep(1.0)

    (DATA / "rosters.json").write_text(
        json.dumps(rosters, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len([p for p in r["players"] if p["status"] == "STARTER"]) for r in rosters.values())
    print(f"\n共抓取 {len(rosters)} 支队伍, 现役选手 {total} 人")
