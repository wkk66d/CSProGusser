"""HLTV.org 队伍 ID 解析脚本
通过 HLTV 搜索接口查找全部目标队伍的 ID。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hltv_scraper import fetch_soup  # noqa: E402

TEAMS = [
    "Falcons", "Spirit", "FURIA", "Vitality", "MOUZ", "NaVi", "9z", "Aurora",
    "G2", "BetBoom", "FaZe", "Legacy", "Astralis", "The MongolZ", "PARIVISION",
    "Liquid", "3DMAX", "paiN", "MIBR", "TYLOO", "Ninjas in Pajamas", "HEROIC",
    "Lynn Vision", "100 Thieves",
]

def resolve_team_ids(names: list[str]) -> dict[str, int]:
    """解析队伍名 → HLTV 队伍 ID。"""
    ids = {}
    for name in names:
        soup = fetch_soup(f"https://www.hltv.org/search?query={name.replace(' ', '%20')}")
        if not soup:
            print(f"[FAIL] {name}: 页面获取失败")
            continue
        candidates = []
        for a in soup.select("a[href*='/team/']"):
            href = a.get("href", "")
            import re
            m = re.search(r"/team/(\d+)/([^/]+)", href)
            if m and m.group(2).lower() == name.lower().replace(" ", "-"):
                candidates.append(int(m.group(1)))
        if candidates:
            ids[name] = candidates[0]
            print(f"[OK] {name} -> {ids[name]}")
        else:
            print(f"[WARN] {name}: 未找到精确匹配，列出候选:")
            for a in soup.select("a[href*='/team/']")[:5]:
                print(f"    {a.get('href')} | {a.get_text(' ', strip=True)[:40]}")
        time.sleep(0.8)
    return ids

if __name__ == "__main__":
    result = resolve_team_ids(TEAMS)
    out = Path(__file__).parent.parent / "data" / "team_ids.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共解析 {len(result)}/{len(TEAMS)} 支队伍 -> {out}")
