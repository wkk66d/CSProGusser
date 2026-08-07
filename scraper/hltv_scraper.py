"""HLTV.org 数据抓取模块
使用 curl_cffi 模拟浏览器 TLS 指纹绕过 Cloudflare 基础防护。
"""
import re
import time
import json
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

BASE = "https://www.hltv.org"
REQUEST_DELAY = 1.0  # 秒，礼貌性限速

_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.hltv.org/",
}

def fetch(url: str, max_retries: int = 3) -> str:
    """抓取页面 HTML，带重试。"""
    for attempt in range(max_retries):
        try:
            r = curl_requests.get(url, impersonate="chrome", timeout=25,
                                  headers=_headers)
            if r.status_code == 200:
                return r.text
            print(f"  [!] {url} -> HTTP {r.status_code} (尝试 {attempt+1})")
        except Exception as e:
            print(f"  [!] {url} -> 异常: {e} (尝试 {attempt+1})")
        time.sleep(2 * (attempt + 1))
    return ""

def fetch_soup(url: str) -> BeautifulSoup:
    html = fetch(url)
    if not html:
        return None
    return BeautifulSoup(html, "html.parser")

def team_id_from_search(name: str) -> int | None:
    """通过 HLTV 搜索接口获取队伍 ID。"""
    soup = fetch_soup(f"{BASE}/search?query={name.replace(' ', '%20')}")
    if not soup:
        return None
    for a in soup.select("a"):
        m = re.search(r"/team/(\d+)/", a.get("href", ""))
        if m:
            return int(m.group(1))
    return None
