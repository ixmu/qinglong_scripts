# 青龙面板签到脚本合集

个人在[青龙面板（QinglongPanel）](https://github.com/whyour/qinglong)上跑的几个自动签到脚本，整理出来方便自己管理，也顺手分享给需要的人。

| 脚本文件 | 语言 | 说明 |
| --- | --- | --- |
| [`discuz_auto_checkin_ql.py`](./discuz_auto_checkin_ql.py) | Python | 宽带技术网（Discuz! X5.0）任务签到，自动申请"领取猫粮" |
| [`ql_netease_full_sign.js`](./ql_netease_full_sign.js) | JavaScript (Node) | 网易云音乐完整签到：普通签到 + 云贝签到/任务 + 黑胶乐签 + VIP成长值 |
| [`tianyiyun.py`](./tianyiyun.py) | Python | 天翼云盘每日签到，领取容量奖励 |
| [`bilibili_task.py`](./bilibili_task.py) | Python | B站每日任务：观看 + 分享 + 自动投币，助力经验值满级 |

## ⚠️ 免责声明

- 以上脚本均为**个人学习交流**用途，基于对应网站/App 的公开接口逆向而来，仅供参考。
- 请只用于**你自己拥有的账号**，并遵守对应网站/服务的用户协议。因使用本仓库脚本造成的任何账号风险（封禁、限流等）由使用者自行承担。
- 脚本不会收集、上传任何账号密码或个人数据，所有账号信息通过青龙面板的环境变量在**本地**读取和使用。
- 各网站接口可能随时变更，脚本失效属正常情况，欢迎提 Issue / PR。

## 快速开始（通用步骤）

1. **脚本管理** → 新建对应脚本文件，把仓库里的代码粘贴进去（或者直接用青龙的"拉取文件"功能，从 `raw.githubusercontent.com` 拉取本仓库对应文件）。
2. **依赖管理** → 按下方各脚本说明安装所需依赖（pip / npm）。
3. **环境变量管理** → 按下方各脚本要求添加账号相关环境变量。
4. **定时任务** → 新建任务，命令填 `task <脚本文件名>`，cron 参考各脚本头部注释或下方建议。
5. 首次配置完先手动点"运行"看日志，确认没问题后再依赖定时任务自动跑。

---

## 1. discuz_auto_checkin_ql.py — 宽带技术网任务签到

模拟登录 [宽带技术网](https://www.chinadsl.net)（Discuz! X5.0 论坛），自动申请"领取猫粮"任务。

**功能特性**
- 标准 Discuz ajax 接口登录
- 自动探测任务页面里的"申请/领取"按钮及真实请求链接（兼容按钮禁用、onclick 藏参数等情况）
- 自动解析 Discuz 提示页成功/失败正文
- 多账号支持（JSON 数组，密码含任意特殊字符都不受影响）
- 日志分段 + 图标 + ANSI 颜色，账号打码处理

**依赖**：`pip install requests beautifulsoup4 --break-system-packages`

**环境变量**

| 变量名 | 必填 | 说明 |
| --- | --- | --- |
| `CHINADSL_ACCOUNTS` | 是 | JSON 数组，例：`[{"user":"用户名1","pass":"密码1"}]` |
| `MANUAL_TASK_URL` | 否 | 自动探测失败时，手动抓包填入真实签到请求 URL |

**定时任务**：`task discuz_auto_checkin_ql.py`，建议 cron `30 8 * * *`

**常见问题**
- 提示"未能自动识别任务提交链接"：脚本会把整页 HTML 存到 `/ql/data/log/task_page_debug.html`，浏览器登录后手动点一次按钮抓包，把真实链接填入 `MANUAL_TASK_URL`。
- 提示"今日/本周期已完成"：正常状态，无需重复操作。
- 登录失败：先确认账号密码；若站点有验证码/滑块，脚本无法处理，需人工登录一次或更换出口 IP。

---

## 2. ql_netease_full_sign.js — 网易云音乐完整签到

基于 weapi 加密接口的网易云音乐全自动签到脚本，Node.js 环境运行。

**功能特性**
1. 普通签到（PC 端 + 安卓端）
2. 云贝签到 + 连续签到奖励领取
3. 云贝日常任务自动完成
4. 黑胶乐签打卡（+3 成长值）
5. VIP 成长日常任务领取
6. VIP 成长值一键领取奖励

**依赖**：仅需 Node.js 内置模块（`https`、`crypto`），无需 `npm install`。

**环境变量**

| 变量名 | 必填 | 说明 |
| --- | --- | --- |
| `NETEASE_MUSIC_U` | 是 | 网易云音乐 Cookie 中的 `MUSIC_U` 值（浏览器登录后 F12 → Application → Cookie 查看，有效期有限，失效需重新获取） |

**定时任务**：`task ql_netease_full_sign.js`，建议 cron `0 9 * * *`

**通知**：调用青龙内置 `sendNotify`，无需额外配置，青龙里配置好任意推送渠道即可自动收到结果。

参考项目：[chaunsin/netease-cloud-music](https://github.com/chaunsin/netease-cloud-music)、[NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)

---

## 3. tianyiyun.py — 天翼云盘签到

模拟登录天翼云盘（189 云盘），自动完成每日签到领取容量奖励。

**功能特性**
- 完整模拟移动端 RSA 加密登录流程
- 每日签到，区分"首次签到"与"已签到"两种状态
- 手机号后四位打码后再打印/推送
- 结果汇总以表格形式通过 WxPusher 推送

**依赖**：`pip install requests rsa --break-system-packages`

**环境变量**

| 变量名 | 必填 | 说明 |
| --- | --- | --- |
| `ty_username` | 是 | 登录手机号，多账号用 `&` 分隔 |
| `ty_password` | 是 | 登录密码，多账号用 `&` 分隔，需与 `ty_username` 一一对应 |
| `WXPUSHER_APP_TOKEN` | 否 | WxPusher 应用 Token |
| `WXPUSHER_UID` | 否 | WxPusher 用户 UID，多个用 `&` 分隔 |

> ⚠️ `ty_password` 若密码本身含 `&` 会和多账号分隔符冲突，建议密码避开该符号。

**定时任务**：`task tianyiyun.py`，建议 cron `30 4 * * *`

**常见问题**
- 出现图形验证码：触发风控，多是出口 IP 被标记，可先浏览器手动登录过验证码，或更换/静置 IP 后重试。
- 登录报"获取RSA密钥失败"等：天翼云盘登录接口常调整，优先检查是否有新版本脚本。

参考项目：[vistal8/tianyiyun](https://github.com/vistal8/tianyiyun)、[52pojie 原帖](https://www.52pojie.cn/thread-1231190-1-1.html)

---

## 4. bilibili_task.py — B站每日任务

模拟已登录状态调用 bilibili 官方接口，自动完成每日"观看 + 分享"经验任务，并按设置自动投币。

**功能特性**
- 登录状态检查 + 账号信息获取（昵称打码显示）
- 随机抽取一个热门视频用于观看/分享/投币，避免每天固定刷同一个视频
- 观看、分享任务分别 +5 经验，已完成会自动跳过
- 可配置每日投币数量（0~5 枚，默认 1 枚最健康，避免硬币被无脑刷空）
- 多账号并发执行（默认 3 线程），单账号失败不影响其他账号
- 日志分段 + 图标 + ANSI 颜色，账号昵称/UID 打码处理

**依赖**：`pip install requests --break-system-packages`

**环境变量**

| 变量名 | 必填 | 说明 |
| --- | --- | --- |
| `BILI_COOKIE` | 是 | 完整的 bilibili.com Cookie 字符串（需包含 `bili_jct`、`DedeUserID` 等字段），多账号用 `&` 或换行符分隔 |
| `BILI_TOSS_COIN_COUNT` | 否 | 每日投币数量，0~5，默认 1 |

**获取 Cookie 方式**：浏览器登录 [bilibili.com](https://www.bilibili.com) → F12 → Network 任意请求 → Headers 里复制完整 `Cookie` 字段值。

**定时任务**：`task bilibili_task.py`，建议 cron `15 9 * * *`

**常见问题**
- 提示"登录失效或接口被拦截"：优先检查 Cookie 是否过期（重新登录浏览器抓一份新的），其次考虑是否触发了风控（更换/静置出口 IP）。
- 投币任务提示"硬币余额不足"：属正常情况，硬币不够就不会强行投币。

> 本脚本改编自 [Han-cy77/Qinglong_auto](https://github.com/Han-cy77/Qinglong_auto)（MIT License），感谢原作者。相比原版：接入了本仓库统一的 QL `notify` 推送方式（不再需要在脚本里硬编码 Bark URL）、去掉了本地 `logs/` 目录落盘逻辑、修复了多账号按 `&` 分隔在特定情况下失效的问题。

---

## License

本仓库以 [MIT License](./LICENSE) 开源。天翼云盘脚本部分逻辑参考自 [vistal8/tianyiyun](https://github.com/vistal8/tianyiyun)，网易云脚本参考自 [chaunsin/netease-cloud-music](https://github.com/chaunsin/netease-cloud-music) 与 [NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)，B站脚本改编自 [Han-cy77/Qinglong_auto](https://github.com/Han-cy77/Qinglong_auto)，感谢原作者。
