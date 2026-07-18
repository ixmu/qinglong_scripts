#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('宽带技术网签到');
cron: 30 8 * * *
"""
# ===================================================================
# 青龙面板版：Discuz! X5.0 自动登录 + 任务签到（chinadsl.net 示例）
#
# 【使用前必读】
# 1. 只能用于你自己账号的站点，遵守目标站点用户协议。
# 2. 任务模块（home.php?mod=task）具体的 do= 参数因站点安装的任务插件不同而不同，
#    脚本会自动探测任务页面里的相关链接；如果探测不到，会打印页面片段到日志，
#    你需要抓包确认真实链接后通过 MANUAL_TASK_URL 环境变量指定。
# 3. 站点若有验证码/滑块，本脚本无法处理，需要人工介入。
#
# 【青龙面板配置步骤】
# (1) 脚本管理 -> 新建 discuz_auto_checkin_ql.py，粘贴本文件内容
# (2) 依赖管理 -> pip -> 添加：requests、beautifulsoup4
# (3) 环境变量管理 -> 新增变量：
#       名称: CHINADSL_ACCOUNTS
#       值（JSON数组，密码含任何特殊符号如 & # | 都不受影响）：
#       [{"user":"用户名1","pass":"密码1"},{"user":"用户名2","pass":"密码2"}]
#     （可选）名称: MANUAL_TASK_URL  值: 抓包确认的真实签到请求URL
# (4) 定时任务 -> 新建任务，命令填：
#       task discuz_auto_checkin_ql.py
#     或直接在脚本管理里点“运行”按钮手动跑一次，看日志输出调试
# (5) 查看日志：任务日志里能看到本脚本的美化输出，登录、任务申请、
#     最终汇总都有清晰的分段和图标标识，方便一眼定位问题。
# ===================================================================

import os
import re
import sys
import json
import time

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ 缺少依赖，请在青龙 [依赖管理 -> pip] 中添加 requests 和 beautifulsoup4")
    sys.exit(1)

# 青龙常见的通知模块，本地调试时若不存在会自动跳过，不影响脚本运行
try:
    sys.path.append("/ql/data/scripts")
    from notify import send  # 青龙面板自带的 notify.py
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False

    def send(title, content):
        print(f"🔕 未配置青龙通知渠道，以下内容仅本地打印：\n{title}\n{content}")


BASE_URL = "https://www.chinadsl.net"
TASK_ID = 1
TASK_VIEW_URL = f"{BASE_URL}/home.php?mod=task&do=view&id={TASK_ID}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
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


def log_step(icon, text, color=""):
    print(f"{color}{icon} {text}{C.RESET}")


def log_ok(text):
    log_step("✅", text, C.GREEN)


def log_fail(text):
    log_step("❌", text, C.RED)


def log_warn(text):
    log_step("⚠️ ", text, C.YELLOW)


def log_info(text):
    log_step("ℹ️ ", text, C.CYAN)


def log_debug(text):
    log_step("🔍", text, C.GRAY)


def mask_username(name: str) -> str:
    """日志里对用户名做轻度打码，avoid 完整明文暴露在日志截图里。"""
    if len(name) <= 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def load_accounts():
    """
    从环境变量 CHINADSL_ACCOUNTS 读取账号，JSON 数组格式，例如：
        [{"user":"用户名1","pass":"密码1"},{"user":"用户名2","pass":"密码2"}]
    用 JSON 是因为密码里可能包含 & # | 等任意特殊字符，用固定分隔符切割
    容易和密码本身的字符冲突，JSON 能完整保留密码原文。
    """
    raw = os.environ.get("CHINADSL_ACCOUNTS", "").strip()
    if not raw:
        log_fail("未检测到环境变量 CHINADSL_ACCOUNTS，请在青龙 [环境变量管理] 中添加。")
        log_info('格式示例：[{"user":"用户名1","pass":"密码1"},{"user":"用户名2","pass":"密码2"}]')
        sys.exit(1)

    try:
        raw_accounts = json.loads(raw)
    except json.JSONDecodeError as e:
        log_fail(f"CHINADSL_ACCOUNTS 不是合法的 JSON：{e}")
        log_info('请确认格式类似：[{"user":"用户名1","pass":"密码1"}]')
        sys.exit(1)

    accounts = []
    for item in raw_accounts:
        user = item.get("user", "").strip()
        pwd = item.get("pass", "")
        if not user or not pwd:
            log_warn(f"跳过缺少 user/pass 字段的项：{item}")
            continue
        accounts.append((user, pwd))
    return accounts


class DiscuzClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_formhash(self, html: str) -> str:
        m = re.search(r'name="formhash"\s+value="([0-9a-zA-Z]+)"', html)
        if not m:
            m = re.search(r'formhash=([0-9a-zA-Z]+)', html)
        return m.group(1) if m else ""

    def login(self, username: str, password: str) -> bool:
        masked = mask_username(username)
        login_page_url = f"{self.base_url}/member.php?mod=logging&action=login"
        resp = self.session.get(login_page_url, timeout=15)
        resp.encoding = "utf-8"
        formhash = self._get_formhash(resp.text)
        log_debug(f"登录页 formhash = '{formhash}'")
        if not formhash:
            log_warn("未解析出 formhash，登录接口可能已变化，请检查登录页 HTML 结构。")

        login_action_url = (
            f"{self.base_url}/member.php?mod=logging&action=login"
            f"&loginsubmit=yes&infloat=yes&lssubmit=true&inajax=1"
        )
        data = {
            "formhash": formhash,
            "referer": self.base_url + "/",
            "loginfield": "username",
            "username": username,
            "password": password,
            "questionid": "0",
            "answer": "",
        }
        resp2 = self.session.post(login_action_url, data=data, timeout=15)
        resp2.encoding = "utf-8"
        text = resp2.text

        if "欢迎您回来" in text or "succeedhandle" in text or "action=logout" in text:
            log_ok(f"账号 {masked} 登录成功")
            return True

        check = self.session.get(self.base_url + "/", timeout=15)
        if "action=logout" in check.text or username in check.text:
            log_ok(f"账号 {masked} 登录成功（二次检测确认）")
            return True

        log_fail(f"账号 {masked} 登录失败")
        log_debug(f"登录接口返回片段：{text[:200]}")
        return False

    def do_task_checkin(self, task_view_url: str, manual_task_url: str = "") -> str:
        """返回结果描述字符串，用于最终通知汇总。"""
        if manual_task_url:
            r = self.session.get(manual_task_url, timeout=15)
            r.encoding = "utf-8"
            msg = f"使用手动链接签到，返回：{r.text[:200]}"
            log_info(msg)
            return msg

        resp = self.session.get(task_view_url, timeout=15)
        resp.encoding = "utf-8"

        if "需要先登录" in resp.text or "您需要登录后才能继续" in resp.text:
            msg = "访问任务页提示需要登录，登录态未生效"
            log_fail(msg)
            return msg

        soup = BeautifulSoup(resp.text, "html.parser")

        # 情况一：任务按钮处于禁用状态（今日/本周期已完成），class 里带 "taskda"
        disabled_btn = soup.find("a", class_=re.compile(r"\btaskda\b"))
        if disabled_btn:
            onclick = disabled_btn.get("onclick", "")
            m = re.search(r"showDialog\('([^']+)'\)", onclick)
            next_time = m.group(1) if m else "未知时间"
            msg = f"今日/本周期已完成，{next_time}"
            log_info(msg + "（无需重复操作）")
            return msg

        # 情况二：任务按钮可点击（class 只有 "taskbtn"，没有 taskda）
        active_btn = soup.find("a", class_=re.compile(r"\btaskbtn\b(?!\s*taskda)"))
        candidate_links = []
        if active_btn:
            href = active_btn.get("href", "")
            onclick = active_btn.get("onclick", "")
            if href and href not in ("javascript:;", "javascript:void(0);", "#"):
                candidate_links.append(href)
            else:
                m = re.search(r"(home\.php\?mod=task[^'\"\)]+)", onclick)
                if m:
                    candidate_links.append(m.group(1).replace("&amp;", "&"))
                else:
                    log_debug(f"找到可点击的任务按钮，但无法从 onclick 解析出请求地址：{onclick}")

        # 情况三：兜底，继续按关键词扫描全部链接（兼容其他任务插件写法）
        candidate_keywords = ["do=apply", "do=perform", "do=finish", "do=complete", "do=draw"]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "mod=task" in href and any(k in href for k in candidate_keywords) and href not in candidate_links:
                candidate_links.append(href)

        if not candidate_links:
            debug_path = "/ql/data/log/task_page_debug.html"
            try:
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(resp.text)
                log_warn(f"未自动识别到任务链接，页面已保存到 {debug_path}")
            except Exception:
                log_warn("未自动识别到任务链接，且无法写入调试文件，以下是任务页面前 800 字符：")
                print(resp.text[:800])
            log_info("请浏览器登录后手动点击签到按钮，用 F12->Network 找到真实请求URL，"
                     "配置到环境变量 MANUAL_TASK_URL 后重新运行。")
            return "未能自动识别任务提交链接，需要人工抓包确认"

        results = []
        task_page_formhash = self._get_formhash(resp.text)
        for link in candidate_links:
            full_url = link if link.startswith("http") else f"{self.base_url}/{link.lstrip('/')}"
            if "formhash=" not in full_url and task_page_formhash:
                sep = "&" if "?" in full_url else "?"
                full_url = f"{full_url}{sep}formhash={task_page_formhash}"
            r = self.session.get(full_url, timeout=15)
            r.encoding = "utf-8"
            log_debug(f"请求任务接口 -> {full_url}")

            msg_soup = BeautifulSoup(r.text, "html.parser")
            msg_box = msg_soup.find(id="messagetext") or msg_soup.find(
                "div", class_=re.compile(r"alert_(right|error|info)")
            )
            is_error = bool(msg_soup.find("div", class_=re.compile(r"alert_error")))
            if msg_box:
                msg_text = msg_box.get_text(strip=True, separator=" ")
            else:
                body_start = r.text.find("<body")
                msg_text = re.sub(r"<[^>]+>", " ", r.text[body_start:body_start + 1200]).strip()
                msg_text = re.sub(r"\s+", " ", msg_text)

            if is_error:
                log_fail(f"任务提交返回：{msg_text}")
            else:
                log_ok(f"任务提交返回：{msg_text}")
            results.append(msg_text[:150])

        return "; ".join(results)


def main():
    start_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_title(f"🐾 宽带技术网自动签到  {start_ts}")

    accounts = load_accounts()
    log_info(f"共读取到 {len(accounts)} 个账号")

    summary_rows = []
    for idx, (username, password) in enumerate(accounts, 1):
        masked = mask_username(username)
        print(f"\n{C.BOLD}── [{idx}/{len(accounts)}] 账号 {masked} ──{C.RESET}")
        client = DiscuzClient(BASE_URL)

        if not client.login(username, password):
            summary_rows.append((masked, "❌", "登录失败"))
            continue

        result = client.do_task_checkin(TASK_VIEW_URL, os.environ.get("MANUAL_TASK_URL", "").strip())
        icon = "❌" if ("失败" in result or "未能自动识别" in result) else "✅"
        summary_rows.append((masked, icon, result))

    log_title("📋 执行结果汇总")
    summary_lines = []
    for masked, icon, result in summary_rows:
        line = f"{icon} {masked}：{result}"
        print(line)
        summary_lines.append(line)

    summary = "\n".join(summary_lines)
    send("宽带技术网签到结果", summary)

    end_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{C.GRAY}耗时统计由青龙面板自动记录，结束时间 {end_ts}{C.RESET}")


if __name__ == "__main__":
    main()