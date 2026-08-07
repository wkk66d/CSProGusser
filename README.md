# CS2 猜选手游戏 (CSProGusser)

一个基于 HLTV.org 数据的多人 CS2 选手猜测游戏。浏览器访问，支持多人同房间对战。

## 功能

- **选手池** (186 人): 24 支知名战队现役选手 + 教练、BC.Game 选手、CSGO 时期 Major 冠军、4 名知名解说员
- **每名选手 6 项属性**: 国家、战队、年龄、Major 冠军数、位置（步枪手/狙击手/教练/解说）、最高 HLTV Top20 排名
- **智能猜测栏**: 输入自动补全匹配，回车选择第一个匹配，上下方向键在候选间导航，提交后自动清空
- **抢 N 赛制**: 可选抢 1/2/3/4
- **每小局**: 2 分钟 / 8 次猜测
- **反馈系统**: 绿色（相同）/ 黄色（接近）/ 灰色（不接近），年龄/Major/Top 用箭头表示高低
- **多人房间**: 一个房间多人加入，左侧显示自己的猜测表格，右侧显示对手的颜色块（不含文字），自动缩放
- **自动补全**: 输入昵称的一部分即可匹配候选
- **中文界面**

## 数据来源

所有选手数据均来自 [HLTV.org](https://www.hltv.org)，通过网络搜索核实，不依赖任何预设知识库：

| 数据 | 来源 | 采集方式 |
|---|---|---|
| 选手基本信息 (国家/年龄/战队/Major/曾效力队) | HLTV 选手主页 | `scraper/scrape_players.py` 抓取 |
| 队伍阵容 | HLTV 队伍主页 `#rosterBox` | `scraper/scrape_rosters.py` 抓取 |
| Top20 排名 (2013-2025) | HLTV 年度 Top20 文章 | `scraper/scrape_top20.py` 抓取 |
| 位置 (狙击手/步枪手) | 各队阵容报道 (网络搜索核实) | 手工核实表 |
| 解说员信息 | 网络搜索核实 | 手工条目 |

数据文件: `data/players.json` (186 名选手)

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

## 游戏玩法

1. 创建房间或输入房间码加入
2. 房主选择抢 N (1/2/3/4)
3. 每小局开始后，系统随机选择一名目标选手
4. 玩家通过输入昵称猜测目标选手
5. 每次猜测后，6 项属性分别显示反馈：
   - **绿色**: 与目标选手一致
   - **黄色**: 接近（国家同洲/CIS 同区；战队是目标曾效力过的队伍）
   - **灰色**: 不接近
   - **↑↓**: 年龄/Major 数/Top 位 比目标高或低
6. 率先猜中者得分；无人猜中则 2 分钟超时或 8 次猜测用尽后结束
7. 先达到抢 N 分的玩家获胜

## 项目结构

```
CSProGusser/
├── server.py              # 后端主入口 (HTTP + WebSocket + 静态文件)
├── game_engine.py         # 游戏逻辑 (房间管理、回合、计分、反馈算法)
├── scraper/               # HLTV 数据抓取工具
│   ├── hltv_scraper.py    # 抓取核心 (curl_cffi 模拟浏览器)
│   ├── scrape_rosters.py  # 队伍阵容抓取
│   ├── scrape_players.py  # 选手详情抓取
│   ├── scrape_top20.py    # 年度 Top20 名单抓取
│   └── build_player_db.py # 合并生成 data/players.json
├── data/
│   └── players.json       # 选手数据库 (182 人)
├── static/
│   ├── index.html         # 游戏页面 (中文)
│   ├── style.css          # 样式
│   └── game.js            # 前端游戏逻辑
├── tests/                 # 自动化测试
│   └── test_player_data.py
└── README.md              # 本文档 (中文)
```

## 测试

```bash
python -m pytest tests/ -v
```

覆盖: 选手数据完整性、反馈算法 (绿/黄/灰 + 箭头方向 + CIS 分区)、房间与回合生命周期、WebSocket 完整游戏流程、HTTP API。当前 35 项测试全部通过。

## 更新选手数据

```bash
python scraper/scrape_rosters.py      # 更新队伍阵容
python scraper/scrape_players.py      # 更新选手详情
python scraper/build_player_db.py     # 重建 data/players.json
```
