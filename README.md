# CS2 猜选手游戏 (CSProGusser)

一个基于 HLTV.org 数据的多人 CS2 选手猜测游戏。浏览器访问，支持多人同房间对战。界面采用**液态玻璃 (Liquid Glass)** 风格设计。

## 功能

- **选手池** (161 人): 24 支知名战队现役选手 + CS2 Major 冠军 + 2018 以来 CSGO Major 冠军 + 8 名传奇选手 (olofmeister/GuardiaN/kennyS/coldzera/Snax/f0rest/GeT_RiGhT/HObbit) + 知名教练 (zonic/B1ad3 级别) + 4 名解说员
- **每名选手 6 项属性**: 国家（中文显示）、战队、年龄、Major 冠军数、位置（步枪手/狙击手/教练/解说）、最高 HLTV Top20 排名
- **智能猜测栏**: 输入自动补全，**首字母优先匹配**（输入 b → b1t 而非 Aleksib），**支持数字替换模糊匹配**（`1↔i` `3↔e` `4↔a` 等，输入 bit 可匹配 b1t），回车选择第一个匹配，上下方向键在候选间导航，提交后自动清空
- **反馈系统**:
  - 绿色: 与目标选手一致
  - 黄色: 接近 — 同洲国家（CIS 独立分区，乌克兰属欧洲）、数值相近（年龄 ±3 / Major ±1 / Top ±3）、目标曾效力过猜测选手所在战队
  - 灰色: 不接近
  - ↑↓: 年龄/Major/Top 比目标高或低
- **抢 N 赛制**: 可选抢 1/2/3/4
- **每小局**: 2 分钟 / 8 次猜测；时间耗尽或所有人猜测次数用完立即结束
- **多人房间**: 一个房间多人加入，左侧显示自己的猜测表格（含全部历史反馈），右侧显示对手的颜色块矩阵（带列标题，不含文字），自动缩放
- **通信**: HTTP 轮询为主（cloudflared 隧道中 100% 可靠），实时同步比分/计时/对手猜测
- **中文界面** + 液态玻璃 UI

## 数据来源

所有选手数据均来自 [HLTV.org](https://www.hltv.org)，通过网络搜索核实，不依赖任何预设知识库：

| 数据 | 来源 | 采集方式 |
|---|---|---|
| 选手基本信息 (国家/年龄/战队/Major/曾效力队) | HLTV 选手主页 | `scraper/scrape_players.py` 抓取 |
| 队伍阵容 | HLTV 队伍主页 `#rosterBox` | `scraper/scrape_rosters.py` 抓取 |
| Top20 排名 (2013-2025) | HLTV 年度 Top20 文章 | `scraper/scrape_top20.py` 抓取 |
| 位置 (狙击手/步枪手) | 各队阵容报道 (网络搜索核实) | 手工核实表 |
| 解说员信息 | 网络搜索核实 | 手工条目 |

数据文件: `data/players.json` (161 名选手，国家名含中英对照)

## 快速开始

### 1. 安装依赖

```bash
pip install aiohttp
```

### 2. 启动服务器

```bash
python server.py
```

服务器默认运行在 `http://localhost:8899`。

### 3. 映射到外网 (try.cloudflare)

```bash
cloudflared tunnel --url http://localhost:8899
```

将生成的 `https://xxx.trycloudflare.com` 链接分享给朋友即可加入同一房间。

> 注意: try.cloudflare 临时隧道不支持 WebSocket，本项目已使用纯 HTTP 轮询，不受影响。

## 游戏玩法

1. 创建房间或输入房间码加入
2. 房主选择抢 N (1/2/3/4)
3. 每小局开始后，系统随机选择一名目标选手
4. 玩家通过输入昵称猜测目标选手（自动补全，首字母优先 + 数字替换匹配）
5. 每次猜测后，6 项属性分别显示反馈（绿/黄/灰 + 箭头）
6. 率先猜中者得分；无人猜中则 2 分钟超时或 8 次猜测用尽后结束
7. 先达到抢 N 分的玩家获胜

## 项目结构

```
CSProGusser/
├── server.py              # 后端主入口 (HTTP + 轮询 + 静态文件)
├── game_engine.py         # 游戏逻辑 (房间管理、回合、计分、反馈算法、搜索匹配)
├── scraper/               # HLTV 数据抓取工具
│   ├── hltv_scraper.py    # 抓取核心 (curl_cffi 模拟浏览器)
│   ├── scrape_rosters.py  # 队伍阵容抓取
│   ├── scrape_players.py  # 选手详情抓取
│   ├── scrape_top20.py    # 年度 Top20 名单抓取
│   └── build_player_db.py # 合并生成 data/players.json (含中英国家对照)
├── data/
│   └── players.json       # 选手数据库 (161 人)
├── static/
│   ├── index.html         # 游戏页面 (中文)
│   ├── style.css          # 液态玻璃样式
│   └── game.js            # 前端游戏逻辑 (HTTP 轮询 + 智能补全)
├── tests/                 # 自动化测试
│   ├── test_player_data.py
│   ├── test_game_engine.py
│   └── test_server.py
└── README.md              # 本文档 (中文)
```

## 测试

```bash
python -m pytest tests/ -v
```

覆盖: 选手数据完整性、反馈算法 (绿/黄/灰 + 相近标黄 + 箭头方向 + CIS 分区)、昵称搜索匹配、房间与回合生命周期、HTTP 轮询完整游戏流程、HTTP API。当前 37 项测试全部通过。

## 更新选手数据

```bash
python scraper/scrape_rosters.py      # 更新队伍阵容
python scraper/scrape_players.py      # 更新选手详情
python scraper/build_player_db.py     # 重建 data/players.json
```

## 更新日志

- 2026-08: 液态玻璃 UI、智能昵称匹配 (首字母优先 + 数字替换)、数值相近标黄、中文国家名、乌克兰归欧洲、回合耗尽立即结束
- 2026-08: 选手池更新 (161 人): 添加 CS2 Major 冠军、仅保留 2018+ CSGO 冠军、知名教练精简、加回 8 名传奇选手
- 2026-08: 纯 HTTP 轮询通信 (cloudflared 隧道兼容)、比分实时更新
