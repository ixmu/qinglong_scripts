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
#    我没法访问该站需要登录后才能看到的页面逐一核对，脚本会自动探测任务页面里
#    的相关链接；如果探测不到，会打印页面片段到日志，你需要抓包确认真实链接后
#    通过 MANUAL_TASK_URL 环境变量指定。
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
# (5) 查看日志：任务日志里能看到本脚本的 print 输出，包括 formhash、
#     登录返回内容前几百字符、任务链接请求结果等，方便逐步排查。
# ===================================================================

import os
import re
import sys
import json

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[错误] 缺少依赖，请在青龙 '依赖管理 -> pip' 中添加 requests 和 beautifulsoup4")
    sys.exit(1)

# 青龙常见的通知模块，本地调试时若不存在会自动跳过，不影响脚本运行
try:
    sys.path.append("/ql/data/scripts")
    from notify import send  # 青龙面板自带的 notify.py
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False

    def send(title, content):
        print(f"[通知-未配置QL notify，仅本地打印]\n{title}\n{content}")


BASE_URL = "https://www.chinadsl.net"
TASK_ID = 1
TASK_VIEW_URL = f"{BASE_URL}/home.php?mod=task&do=view&id={TASK_ID}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def load_accounts():
    """
    从环境变量 CHINADSL_ACCOUNTS 读取账号，JSON 数组格式，例如：
        [{"user":"用户名1","pass":"密码1"},{"user":"用户名2","pass":"密码2"}]
    用 JSON 是因为密码里可能包含 & # | 等任意特殊字符，用固定分隔符切割
    容易和密码本身的字符冲突，JSON 能完整保留密码原文。
    """
    raw = os.environ.get("CHINADSL_ACCOUNTS", "").strip()
    if not raw:
        print("[错误] 未检测到环境变量 CHINADSL_ACCOUNTS，请在青龙'环境变量管理'中添加。")
        print('格式示例：[{"user":"用户名1","pass":"密码1"},{"user":"用户名2","pass":"密码2"}]')
        sys.exit(1)

    try:
        raw_accounts = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[错误] CHINADSL_ACCOUNTS 不是合法的 JSON：{e}")
        print('请确认格式类似：[{"user":"用户名1","pass":"密码1"}]')
        sys.exit(1)

    accounts = []
    for item in raw_accounts:
        user = item.get("user", "").strip()
        pwd = item.get("pass", "")
        if not user or not pwd:
            print(f"[警告] 跳过缺少 user/pass 字段的项：{item}")
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
        login_page_url = f"{self.base_url}/member.php?mod=logging&action=login"
        resp = self.session.get(login_page_url, timeout=15)
        resp.encoding = "utf-8"
        formhash = self._get_formhash(resp.text)
        print(f"[调试] 登录页 formhash = '{formhash}'")
        if not formhash:
            print("[警告] 未解析出 formhash，登录接口可能已变化，"
                  "请检查登录页 HTML 结构（可打开 task_page_debug 类似方式保存排查）。")

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
        print(f"[调试] 登录返回片段: {text[:300]}")

        if "欢迎您回来" in text or "succeedhandle" in text or "action=logout" in text:
            print(f"[成功] 账号 {username} 登录成功。")
            return True

        check = self.session.get(self.base_url + "/", timeout=15)
        if "action=logout" in check.text or username in check.text:
            print(f"[成功] 账号 {username} 登录成功（二次检测确认）。")
            return True

        print(f"[失败] 账号 {username} 登录未成功。")
        return False

    def do_task_checkin(self, task_view_url: str, manual_task_url: str = "") -> str:
        """返回结果描述字符串，用于最终通知汇总。"""
        if manual_task_url:
            r = self.session.get(manual_task_url, timeout=15)
            r.encoding = "utf-8"
            msg = f"使用手动链接签到，返回：{r.text[:200]}"
            print(f"[提示] {msg}")
            return msg

        resp = self.session.get(task_view_url, timeout=15)
        resp.encoding = "utf-8"

        if "需要先登录" in resp.text or "您需要登录后才能继续" in resp.text:
            msg = "访问任务页提示需要登录，登录态未生效"
            print(f"[失败] {msg}")
            return msg

        soup = BeautifulSoup(resp.text, "html.parser")

        # 情况一：任务按钮处于禁用状态（今日/本周期已完成），class 里带 "taskda"
        # 典型 HTML： <a ... class="taskbtn taskda" onclick="doane(event);showDialog('2026-7-19 00:00 后可以再次申请')">
        disabled_btn = soup.find("a", class_=re.compile(r"\btaskda\b"))
        if disabled_btn:
            onclick = disabled_btn.get("onclick", "")
            m = re.search(r"showDialog\('([^']+)'\)", onclick)
            next_time = m.group(1) if m else "未知时间"
            msg = f"任务今日/本周期已完成，需等到 {next_time} 才能再次申请（无需重复操作）"
            print(f"[提示] {msg}")
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
                # 链接藏在 onclick 里，尝试提取形如 home.php?mod=task&do=apply&id=1&formhash=xxx 的片段
                m = re.search(r"(home\.php\?mod=task[^'\"\)]+)", onclick)
                if m:
                    candidate_links.append(m.group(1).replace("&amp;", "&"))
                else:
                    print(f"[调试] 找到可点击的任务按钮，但无法从 onclick 中解析出请求地址：{onclick}")

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
                print(f"[提示] 未自动识别到任务链接，页面已保存到 {debug_path}")
            except Exception:
                print("[提示] 未自动识别到任务链接，且无法写入调试文件，"
                      "以下是任务页面前 800 字符：")
                print(resp.text[:800])
            print("请浏览器登录后手动点击'签到/领取'，用 F12->Network 找到真实请求URL，"
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
            print(f"[请求] {full_url}")
            print(f"[返回] {r.text[:300]}")
            results.append(r.text[:100])

        return "; ".join(results)


def main():
    accounts = load_accounts()
    manual_task_url = os.environ.get("MANUAL_TASK_URL", "").strip()

    summary_lines = []
    for username, password in accounts:
        print(f"\n===== 开始处理账号：{username} =====")
        client = DiscuzClient(BASE_URL)

        if not client.login(username, password):
            summary_lines.append(f"[{username}] 登录失败")
            continue

        result = client.do_task_checkin(TASK_VIEW_URL, manual_task_url)
        summary_lines.append(f"[{username}] {result}")

    summary = "\n".join(summary_lines)
    print(f"\n===== 全部账号处理完毕 =====\n{summary}")
    send("宽带技术网签到结果", summary)


if __name__ == "__main__":
    main()