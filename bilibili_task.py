#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('B站日常任务');
cron: 15 9 * * *
"""
# ===================================================================
# 青龙面板版：B站（bilibili）每日任务
#   观看视频 + 分享视频 + 自动投币，助力经验值每日满级
#
# 改编自 CY HAN 的 Qinglong_auto 项目（MIT License）：
#   https://github.com/Han-cy77/Qinglong_auto
# 相比原版的改动：
#   - 接入本仓库统一的青龙 notify 推送方式（不再硬编码 Bark URL）
#   - 去掉本地 logs/ 目录落盘逻辑（青龙面板本身保留任务日志，没必要重复写文件）
#   - 账号昵称/UID 做打码处理，避免日志截图泄露
#
# 【使用前必读】
# 1. 只能用于你自己的 B 站账号，遵守 bilibili 用户协议。
# 2. Cookie 有效期有限，过期后任务会提示"登录失效"，需要重新抓取。
# 3. 投币、观看、分享都是真实调用官方接口，请按自己账号情况设置投币数量，
#    不建议把 TOSS_COIN_COUNT 拉满，容易被风控。
#
# 【青龙面板配置步骤】
# (1) 脚本管理 -> 新建 bilibili_task.py，粘贴本文件内容
# (2) 依赖管理 -> pip -> 添加：requests
# (3) 环境变量管理 -> 新增变量：
#       名称: BILI_COOKIE
#       值:   完整的 bilibili.com Cookie 字符串
#       多账号：用 & 符号或换行符分隔多个 Cookie
#     （可选）名称: BILI_TOSS_COIN_COUNT  值: 0~5，每日投币数量，默认 1
# (4) 定时任务 -> 新建任务，命令填：
#       task bilibili_task.py
# (5) 查看日志：登录状态、观看/分享/投币任务结果、最终汇总都有清晰的
#     图标和分段，方便一眼定位问题。
# ===================================================================

import os
import re
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("❌ 缺少依赖，请在青龙 [依赖管理 -> pip] 中添加 requests")
    sys.exit(1)

# 青龙常见的通知模块，本地调试时若不存在会自动跳过，不影响脚本运行
try:
    sys.path.append("/ql/data/scripts")
    from notify import send
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False

    def send(title, content):
        print(f"🔕 未配置青龙通知渠道，以下内容仅本地打印：\n{title}\n{content}")


# 每日自动投币数量（0 = 不投币，最多 5，默认 1 枚最健康）
TOSS_COIN_COUNT = int(os.environ.get("BILI_TOSS_COIN_COUNT", "1"))
TOSS_COIN_COUNT = max(0, min(TOSS_COIN_COUNT, 5))

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
}


# ---------------------------------------------------------------------------
# 日志美化：统一图标 + ANSI 颜色（青龙日志面板支持 ANSI 渲染）
# ---------------------------------------------------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def log_title(text):
    print(f"\n{C.BOLD}{C.CYAN}{'━' * 44}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {text}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'━' * 44}{C.RESET}")


def mask_name(name: str) -> str:
    """对昵称/UID 做轻度打码，避免完整明文暴露在日志截图里。"""
    name = str(name)
    if len(name) <= 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def get_bili_csrf(cookie: str) -> str:
    m = re.search(r"bili_jct=([^;]+)", cookie)
    return m.group(1) if m else ""


def safe_request_json(method: str, url: str, **kwargs):
    """安全地发起请求并解析 JSON，防止 B 站返回 HTML/风控页导致崩溃。"""
    try:
        resp = requests.get(url, **kwargs) if method.upper() == "GET" else requests.post(url, **kwargs)
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        print(f"  ❌ 接口被拦截，状态码 {resp.status_code}，返回片段：{resp.text[:150]}")
        return None
    except Exception as e:
        print(f"  ❌ 请求异常：{e}")
        return None


def do_bili_task(cookie: str, index: int) -> tuple:
    """执行单个账号的 B 站每日任务，返回 (是否成功, 摘要文本)。"""
    headers = dict(HEADERS_BASE)
    headers["Cookie"] = cookie
    csrf = get_bili_csrf(cookie)

    lines = []

    def note(text):
        lines.append(text)
        print(f"  {text}")

    if not csrf:
        note("❌ Cookie 格式错误：缺少 bili_jct 字段，请重新抓取完整的 Cookie")
        return False, "\n".join(lines)

    # 1. 登录状态 + 用户信息
    nav = safe_request_json("GET", "https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=15)
    if not nav or nav.get("code") != 0:
        note("❌ 登录失效或接口被拦截，请检查 Cookie 是否过期，或出口 IP 是否被风控")
        return False, "\n".join(lines)

    data = nav["data"]
    uname = mask_name(data.get("uname", "未知"))
    level = data.get("level_info", {}).get("current_level", "?")
    coins = data.get("money", 0)
    note(f"👤 账号：{uname} (Lv{level})")
    note(f"💰 硬币余额：{coins} 枚")

    # 2. 今日任务完成状态
    reward = safe_request_json(
        "GET", "https://api.bilibili.com/x/member/web/exp/reward", headers=headers, timeout=15
    )
    if not reward:
        return False, "\n".join(lines)
    reward_data = reward.get("data", {})
    watch_done = reward_data.get("watch")
    share_done = reward_data.get("share")
    coin_exp = reward_data.get("coins", 0)

    # 3. 随机取一个热门视频用于观看/分享/投币
    popular = safe_request_json(
        "GET", "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1", headers=headers, timeout=15
    )
    if not popular or popular.get("code") != 0:
        note(f"❌ 获取推荐视频失败：{popular.get('message') if popular else '接口被拦截'}")
        return False, "\n".join(lines)

    video = random.choice(popular["data"]["list"])
    bvid, aid, title = video["bvid"], video["aid"], video["title"]
    note(f"🎯 今日随机视频：《{title[:12]}...》")

    ok = True

    # 4. 观看任务
    if not watch_done:
        w = safe_request_json(
            "POST",
            "https://api.bilibili.com/x/click-interface/web/heartbeat",
            data={"aid": aid, "bvid": bvid, "csrf": csrf, "played_time": 300},
            headers=headers,
            timeout=15,
        )
        if w and w.get("code") == 0:
            note("📺 观看任务：✅ 完成 (+5 经验)")
        else:
            note(f"📺 观看任务：❌ 失败（{w.get('message') if w else '接口解析失败'}）")
            ok = False
        time.sleep(2)
    else:
        note("📺 观看任务：☕ 今日已达标")

    # 5. 分享任务
    if not share_done:
        s = safe_request_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/share/add",
            data={"aid": aid, "bvid": bvid, "csrf": csrf, "share_channel": "copy"},
            headers=headers,
            timeout=15,
        )
        if s and s.get("code") == 0:
            note("↗️ 分享任务：✅ 完成 (+5 经验)")
        else:
            note(f"↗️ 分享任务：❌ 失败（{s.get('message') if s else '接口解析失败'}）")
            ok = False
        time.sleep(2)
    else:
        note("↗️ 分享任务：☕ 今日已达标")

    # 6. 投币任务
    target_exp = TOSS_COIN_COUNT * 10
    if TOSS_COIN_COUNT <= 0:
        note("🪙 投币任务：⚙️ 已设置为不投币")
    elif coin_exp >= target_exp:
        note("🪙 投币任务：☕ 今日投币量已达标")
    elif coins <= 0:
        note("🪙 投币任务：⚠️ 硬币余额不足，跳过")
    else:
        c = safe_request_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/coin/add",
            data={
                "aid": aid,
                "bvid": bvid,
                "multiply": TOSS_COIN_COUNT,
                "select_like": 1,
                "cross_domain": "true",
                "csrf": csrf,
            },
            headers=headers,
            timeout=15,
        )
        if c and c.get("code") == 0:
            note(f"🪙 投币任务：✅ 成功投出 {TOSS_COIN_COUNT} 枚 (+{TOSS_COIN_COUNT * 10} 经验)")
        else:
            err = f"code:{c.get('code')} {c.get('message')}" if c else "接口解析失败"
            note(f"🪙 投币任务：❌ 失败（{err}）")
            ok = False

    return ok, "\n".join(lines)


def get_cookies() -> list:
    """
    从环境变量 BILI_COOKIE 读取账号，支持两种分隔方式：
      - 多个 Cookie 之间用换行符分隔（Cookie 本身较长时更清晰，优先判断）
      - 多个 Cookie 之间用 & 分隔
    注意：Cookie 本身的键值对之间用 "; " 分隔，不会用到 "&"，
    所以只要出现 "&" 就按多账号处理是安全的。
    """
    raw = os.environ.get("BILI_COOKIE", "").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [c.strip() for c in raw.split("\n") if c.strip()]
    if "&" in raw:
        return [c.strip() for c in raw.split("&") if c.strip()]
    return [raw]


def main():
    start_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_title(f"📺 B站日常任务  {start_ts}")

    cookies = get_cookies()
    if not cookies:
        print("❌ 未检测到环境变量 BILI_COOKIE，请在青龙 [环境变量管理] 中添加。")
        sys.exit(1)

    print(f"ℹ️  共读取到 {len(cookies)} 个账号，投币数量设置为 {TOSS_COIN_COUNT} 枚，开始并发执行...")

    summary_rows = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(do_bili_task, cookie, i + 1): i + 1 for i, cookie in enumerate(cookies)}
        for future in as_completed(futures):
            idx = futures[future]
            print(f"\n{C.BOLD}── 账号 {idx}/{len(cookies)} ──{C.RESET}")
            try:
                ok, detail = future.result()
                summary_rows.append((idx, ok, detail))
            except Exception as exc:
                print(f"  ❌ 执行异常：{exc}")
                summary_rows.append((idx, False, f"执行异常：{exc}"))

    summary_rows.sort(key=lambda x: x[0])

    log_title("📋 执行结果汇总")
    summary_lines = []
    for idx, ok, detail in summary_rows:
        icon = "✅" if ok else "❌"
        block = f"{icon} 账号 {idx}：\n{detail}"
        print(block)
        summary_lines.append(block)

    summary = "\n\n".join(summary_lines)
    send("📺 B站日常任务签到结果", summary)

    end_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{C.GRAY}结束时间 {end_ts}{C.RESET}")


if __name__ == "__main__":
    main()
