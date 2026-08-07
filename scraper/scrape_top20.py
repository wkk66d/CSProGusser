"""HLTV.org 年度 Top20 名单抓取脚本
通过每年度的 intro/final-list 文章提取完整排名 (2013-2025)。
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hltv_scraper import fetch, fetch_soup, BASE  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

# 每年已知的文章入口 (intro 或 final-list 或任意单名文章)
ENTRIES = {
    2025: ("final-list", 43492, "top-20-players-of-2025-final-list"),
    2024: ("final-list", 40608, "top-20-players-of-2024-final-list"),
    2023: ("intro", 37845, "top-20-players-of-2023-introduction"),
    2022: ("entry", 35329, "top-20-players-of-2022-rain-13"),
    2021: ("intro", 33039, "top-20-players-of-2021-introduction"),
    2020: ("entry", 31024, "top-20-players-of-2020-zywoo-1"),
    2019: ("entry", 28877, "top-20-players-of-2019-zywoo-1"),
    2018: ("intro", 25735, "top-20-players-of-2018-introduction"),
    2017: ("entry", 22516, "top-20-players-of-2017-coldzera-1"),
    2016: ("entry", 19560, "top-20-players-of-2016-dennis-20"),
    2014: ("entry", 13990, "top-20-players-of-2014-jw-5"),
}

def find_intro_link(soup) -> str | None:
    """在文章中找到 intro 文章链接。"""
    for a in soup.select("a[href*='/news/']"):
        t = a.get_text(" ", strip=True).lower()
        href = a.get("href", "")
        if "introduction" in t or "introduction" in href:
            m = re.search(r"/news/(\d+)/([^#?]+)", href)
            if m:
                return f"{BASE}/news/{m.group(1)}/{m.group(2)}"
    return None

def extract_list(soup) -> list[str]:
    """从文章正文提取 '1. nickname' 到 '20. nickname' 的有序名单。"""
    art = soup.select_one("article")
    text = art.get_text(" ", strip=True) if art else soup.get_text(" ", strip=True)
    # 清除零宽字符 (u200B, u2060 等)
    text = re.sub(r"[​⁠﻿]", "", text)
    # 匹配 "N. Nickname" 模式（引号内为昵称）
    pattern = re.compile(r"(\d{1,2})\.\s*[^\n]{0,80}?\"\s*([A-Za-z0-9_.\-^]+)\s*\"", re.S)
    matches = pattern.findall(text)
    ordered = {}
    for rank, nick in matches:
        r = int(rank)
        if 1 <= r <= 20:
            ordered[r] = nick
    if len(ordered) < 15:
        return []
    return [ordered.get(i, "?") for i in range(1, 21)]

def scrape_year(year: int, kind: str, art_id: int, slug: str) -> dict:
    """抓取某年 Top20 名单。"""
    soup = fetch_soup(f"{BASE}/news/{art_id}/{slug}")
    if not soup:
        return None
    if kind != "intro" and kind != "final-list":
        intro_link = find_intro_link(soup)
        if intro_link:
            soup = fetch_soup(intro_link)
            if not soup:
                return None
    lst = extract_list(soup)
    return {"year": year, "top20": lst}

if __name__ == "__main__":
    results = {}
    for year, (kind, art_id, slug) in ENTRIES.items():
        r = scrape_year(year, kind, art_id, slug)
        if r is None:
            print(f"[FAIL] {year}")
            continue
        results[str(year)] = r["top20"]
        print(f"[OK] {year}: {' | '.join(f'{i+1}.{n}' for i, n in enumerate(r['top20']))}")
        time.sleep(1.0)

    (DATA / "top20_lists.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n共抓取 {len(results)} 个年份")
