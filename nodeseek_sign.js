/*
cron: 30 8 * * *
new Env('NodeSeek 自动签到 (完美收官版)');
*/

const { exec } = require('child_process');

// 获取环境变量并清洗
let cookie = process.env.NODESEEK_COOKIE;
if (cookie) {
    cookie = cookie.replace(/[\r\n]/g, '').trim();
}
const ua = process.env.NODESEEK_UA || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const signType = process.env.NODESEEK_SIGN_TYPE === 'fixed' ? 'false' : 'true'; 

if (!cookie) {
    console.log('❌ 错误: 未检测到 NODESEEK_COOKIE 环境变量，请先在青龙中配置！');
    process.exit(0);
}

function doSign() {
    console.log(`🚀 开始 NodeSeek 签到 (完美收官版)，选择模式: ${signType === 'true' ? '试试手气' : '固定鸡腿'}`);

    const url = `https://www.nodeseek.com/api/attendance?random=${signType}`;

    // 标准原生 curl 强袭命令
    const cmd = `curl -s -X POST "${url}" \
      --http1.1 \
      -H "Host: www.nodeseek.com" \
      -H "Connection: keep-alive" \
      -H "Accept: application/json, text/plain, */*" \
      -H "User-Agent: ${ua}" \
      -H "Content-Type: application/json" \
      -H "Origin: https://www.nodeseek.com" \
      -H "Referer: https://www.nodeseek.com/board" \
      -H "Accept-Language: zh-CN,zh;q=0.9" \
      -H "Cookie: ${cookie}" \
      -d "{}"`;

    exec(cmd, (error, stdout, stderr) => {
        if (error) {
            console.log('❌ 执行底层命令发生错误:', error.message);
            return;
        }

        const data = stdout.trim();
        if (!data) {
            console.log('❌ 服务器未返回任何内容，可能被拦截。');
            return;
        }

        // 精准处理响应逻辑
        if (data.includes('已完成签到') || data.includes('请勿重复操作')) {
            console.log(`⚠️ 今天已经签到过了，请勿重复操作。`);
            return;
        }

        try {
            const result = JSON.parse(data);
            // 匹配包含“鸡腿”或 success 为 true 的成功回执
            if (result.success || data.includes('"success":true') || data.includes('鸡腿')) {
                console.log(`✅ 签到成功！`);
                console.log(`📝 服务器返回信息: ${result.message || data}`);
            } else {
                console.log(`⚠️ 接口响应成功，但有其他提示: ${result.message || data}`);
            }
        } catch (e) {
            // 防止部分情况下非 JSON 返回但实际包含成功关键字
            if (data.includes('鸡腿') || data.includes('成功')) {
                console.log(`✅ 签到成功！(字符串匹配)`);
                console.log(`📝 原始返回: ${data}`);
            } else {
                console.log(`❌ 解析返回数据失败，原始数据: ${data}`);
            }
        }
    });
}

doSign();