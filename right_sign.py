"""
恩山论坛(right.com.cn)签到脚本
签到系统：二零CMS签到系统 v1.0 (erling_qd)
青龙面板 Python3

基于实际抓包分析：
  接口: POST plugin.php?id=erling_qd:action&action=sign
  参数: formhash=xxx
  响应: JSON {success: bool, message: str}

new Env('恩山论坛签到');
cron: 30 8 * * *

"""

import os, re, json, time
import requests

# ==================== 通知 ====================
try:
    from notify import send
    def push(title, content):
        try: send(title, content)
        except: pass
except:
    def push(title, content): pass

# ==================== 配置 ====================
BASE = "https://www.right.com.cn/forum"
SIGN_PAGE = f"{BASE}/erling_qd-sign_in.html"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class Enshan:
    def __init__(self, cookie):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        for item in cookie.strip().split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self.s.cookies.set(k.strip(), v.strip())

    def get(self, url, **kw):
        return self.s.get(url, timeout=15, allow_redirects=True, **kw)

    def post(self, url, **kw):
        return self.s.post(url, timeout=15, allow_redirects=True, **kw)

    # ---------- 获取 formhash ----------
    def get_formhash(self):
        patterns = [
            r"var\s+FORMHASH\s*=\s*'([a-f0-9]{8})'",
            r'var\s+FORMHASH\s*=\s*"([a-f0-9]{8})"',
            r'name="formhash"\s+value="([a-f0-9]{8})"',
            r'formhash=([a-f0-9]{8})',
        ]

        for url in [SIGN_PAGE, f"{BASE}/forum.php"]:
            try:
                print(f"[formhash] 访问: {url}")
                html = self.get(url).text

                for pat in patterns:
                    m = re.search(pat, html)
                    if m:
                        fh = m.group(1)
                        print(f"[formhash] ✅ {fh}")
                        return fh

                print(f"[formhash] 未匹配到")
            except Exception as e:
                print(f"[formhash] 异常: {e}")
        return None

    # ---------- 状态检测 ----------
    def check_status(self):
        try:
            html = self.get(SIGN_PAGE).text

            if "var FORMHASH" not in html:
                return "login_fail", {}

            days_match = re.search(r'<span class="erqd-continuous-days">(\d+)</span>', html)
            btn_match = re.search(r'<button[^>]*id="signin-btn"[^>]*>([^<]+)</button>', html)

            info = {
                "continuous_days": int(days_match.group(1)) if days_match else None,
                "btn_text": btn_match.group(1).strip() if btn_match else None,
            }

            if info["btn_text"] and "已签到" in info["btn_text"]:
                return "signed", info
            if info["continuous_days"] is not None and info["continuous_days"] > 0:
                return "signed", info

            return "unsigned", info

        except Exception as e:
            print(f"[状态] 异常: {e}")
            return "error", {}

    # ---------- 签到 ----------
    def do_sign(self, formhash):
        url = f"{BASE}/plugin.php?id=erling_qd:action&action=sign"
        data = {"formhash": formhash}
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": SIGN_PAGE,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        print(f"[签到] POST {url}")
        print(f"[签到] Data: {data}")

        try:
            resp = self.post(url, data=data, headers=headers)
            text = resp.text.strip()
            print(f"[签到] 响应: {text}")

            result = json.loads(text)
            success = result.get("success", False)
            message = result.get("message", "")

            if success:
                print(f"[签到] ✅ 成功: {message}")
                return "success", message
            else:
                print(f"[签到] ❌ 失败: {message}")
                if "已经" in message or "已签到" in message or "重复" in message:
                    return "already", message
                return "fail", message

        except json.JSONDecodeError:
            print(f"[签到] 非JSON响应: {text[:300]}")
            return "fail", f"响应解析失败: {text[:100]}"
        except Exception as e:
            print(f"[签到] 异常: {e}")
            return "error", str(e)

    # ---------- 主入口 ----------
    def run(self):
        print(f"\n{'='*50}")
        print(f"  恩山论坛签到 | {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}")

        status, info = self.check_status()
        print(f"[状态] 按钮文字: {info.get('btn_text')}")
        print(f"[状态] 连续签到: {info.get('continuous_days')}天")

        if status == "login_fail":
            return False, "Cookie已失效，请重新获取"
        if status == "signed":
            return True, f"今日已签到（连续{info.get('continuous_days')}天）"

        fh = self.get_formhash()
        if not fh:
            return False, "获取formhash失败"

        result, msg = self.do_sign(fh)

        if result == "success":
            return True, f"签到成功 ✅ | {msg}"
        if result == "already":
            return True, f"今日已签到 | {msg}"

        return False, f"签到失败 | {msg}"


# ==================== 主函数 ====================
def main():
    raw = os.environ.get("RIGHT_COOKIE", "")
    cookies = []

    if raw:
        for p in raw.replace("\n", "&").split("&"):
            p = p.strip()
            if p and "=" in p:
                cookies.append(p)

    if not cookies:
        i = 1
        while True:
            c = os.environ.get(f"RIGHT_COOKIE_{i}", "")
            if not c: break
            cookies.append(c.strip())
            i += 1

    if not cookies:
        print("❌ 未设置 RIGHT_COOKIE 环境变量")
        push("恩山论坛签到 ❌", "未配置环境变量 RIGHT_COOKIE")
        return

    print(f"📋 账号数: {len(cookies)}")
    results = []

    for i, ck in enumerate(cookies, 1):
        print(f"\n{'─'*50}")
        print(f" 账号 {i}/{len(cookies)}")
        print(f"{'─'*50}")
        ok, msg = Enshan(ck).run()
        results.append((ok, msg))
        time.sleep(2)

    ok_n = sum(1 for o, _ in results if o)
    lines = [f"账号{i}: {'✅' if o else '❌'} {m}" for i, (o, m) in enumerate(results, 1)]
    summary = "\n".join(lines)

    print(f"\n{'='*50}")
    print(f"  汇总: 成功 {ok_n}/{len(results)}")
    print(f"{'='*50}")
    print(summary)
    print(f"{'='*50}")

    if ok_n == len(results):
        push("恩山论坛签到 ✅", summary)
    else:
        push(f"恩山论坛签到 成功{ok_n}/失败{len(results)-ok_n}", summary)


if __name__ == "__main__":
    main()