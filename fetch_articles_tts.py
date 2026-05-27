"""
微信公众号文章TTS语音合成自动化脚本
每天定时抓取猫笔刀、刘备教授的最新文章，转为MP3语音

使用方法:
  python fetch_articles_tts.py              # 本地模式（含WorkBuddy同步）
  python fetch_articles_tts.py --serverless  # Serverless模式（仅生成文件，不依赖本地路径）
  python fetch_articles_tts.py --output-dir ./output  # 自定义输出目录

定时任务:
  - 每天上午8点执行，抓取最新文章并生成语音
  - MP3文件保存到 AUDIO_DIR 目录
  - 日志记录到 LOG_FILE
"""

import asyncio
import edge_tts
import httpx
import re
import os
import sys
import json
import subprocess
import shutil
import argparse
from datetime import datetime

# ============== 配置区 ==============
VOICE = "zh-CN-XiaoxiaoNeural"
VOICE_RATE = "+10%"
VOICE_PITCH = "+0Hz"

# 本地模式路径
AUDIO_DIR = r"C:\Users\yuhaoxiong\WorkBuddy\articles_tts"
LOG_FILE = os.path.join(AUDIO_DIR, "tts_log.txt")
WORKSPACE_DIR = r"C:\Users\yuhaoxiong\WorkBuddy\2026-05-19-task-2"
NOTIFICATION_FILE = os.path.join(WORKSPACE_DIR, "daily_article_notification.md")
ARTICLES_JSON = os.path.join(WORKSPACE_DIR, "web", "data", "articles.json")
WECHAT_SEARCH_SCRIPT = r"C:\Users\yuhaoxiong\.workbuddy\skills\wechat-article-search\scripts\search_wechat.js"

# 文章源配置
SOURCES = [
    {"name": "猫笔刀", "search_query": "猫笔刀"},
    {"name": "刘备教授", "search_query": "刘备教授"},
]

# ============== 全局模式 ==============
SERVERLESS = False
OUTPUT_DIR = ""


def parse_args():
    """解析命令行参数"""
    global SERVERLESS, OUTPUT_DIR, AUDIO_DIR, LOG_FILE, WORKSPACE_DIR, NOTIFICATION_FILE, ARTICLES_JSON

    parser = argparse.ArgumentParser(description="微信公众号文章TTS抓取")
    parser.add_argument("--serverless", action="store_true", help="Serverless模式（CI/CD环境使用）")
    parser.add_argument("--output-dir", type=str, default="./output", help="Serverless模式输出目录")
    args = parser.parse_args()

    if args.serverless:
        SERVERLESS = True
        OUTPUT_DIR = os.path.abspath(args.output_dir)
        AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
        LOG_FILE = os.path.join(OUTPUT_DIR, "tts_log.txt")
        WORKSPACE_DIR = OUTPUT_DIR
        NOTIFICATION_FILE = os.path.join(OUTPUT_DIR, "daily_article_notification.md")
        ARTICLES_JSON = os.path.join(OUTPUT_DIR, "articles.json")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[LOG ERROR] {e}")


async def search_latest_article(name: str, query: str) -> dict:
    """通过 wechat-article-search 脚本搜索最新文章（仅用于刘备教授，因为fugay是动态渲染）"""
    try:
        skill_dir = os.path.dirname(WECHAT_SEARCH_SCRIPT)
        result = subprocess.run(
            [sys.executable, "-c",
             f"import subprocess, sys; r = subprocess.run(['node', r'{WECHAT_SEARCH_SCRIPT}', '{query}', '-n', '5'], "
             f"capture_output=True, text=True, cwd=r'{skill_dir}'); print(r.stdout[:5000])"],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout
        json_start = output.find('{')
        json_end = output.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(output[json_start:json_end])
            articles = data.get("articles", [])
            # Filter to only articles from the correct official account source
            if articles:
                for a in articles:
                    src = a.get("source", "")
                    # 刘备教授官方来源
                    if name == "刘备教授" and ("刘备教授" in src or "刘备" in src):
                        return {"title": a.get("title",""), "url": a.get("url",""),
                                "datetime": a.get("datetime",""), "source": src}
                    # 猫笔刀官方来源
                    if name == "猫笔刀" and ("猫笔刀" in src or "猫笔" in src or "招财大牛猫" in src):
                        return {"title": a.get("title",""), "url": a.get("url",""),
                                "datetime": a.get("datetime",""), "source": src}
                # Fallback: return first article if filter fails
                first = articles[0]
                return {"title": first.get("title",""), "url": first.get("url",""),
                        "datetime": first.get("datetime",""), "source": first.get("source","")}
        log(f"[WARN] {name}: 搜索未返回文章数据")
        return {}
    except subprocess.TimeoutExpired:
        log(f"[ERROR] {name}: 搜索超时")
        return {}
    except Exception as e:
        log(f"[ERROR] {name}: 搜索失败 - {e}")
        return {}


def clean_article_text(text: str) -> str:
    """清理文章正文"""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'点击蓝字.*', '', text)
    text = re.sub(r'来源.*', '', text)
    text = re.sub(r'作者.*', '', text)
    text = re.sub(r'关注.*', '', text)
    text = re.sub(r'分享.*', '', text)
    text = re.sub(r'赞.*', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\.{3,}', '……', text)
    return text.strip()


def truncate_for_tts(text: str, max_chars: int = 3500) -> str:
    """截断文本以符合TTS限制"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_punct = max(truncated.rfind('。'), truncated.rfind('！'), truncated.rfind('？'))
    if last_punct > max_chars * 0.6:
        return truncated[:last_punct + 1]
    return truncated + "……"


async def fetch_article_content(url: str) -> str:
    """从归档站抓取文章正文"""
    # 猫笔刀用 maobidao.cn
    if "maobidao" in url:
        return await fetch_maobidao(url)
    # 刘备教授用 fugay.com
    if "fugay" in url:
        return await fetch_fugay(url)
    # 否则直接抓取
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            return clean_article_text(resp.text)
    except Exception as e:
        log(f"[ERROR] fetch_article_content failed: {e}")
        return ""


async def fetch_maobidao(url: str) -> str:
    """抓取猫笔刀文章"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
            
            # 提取 <p> 标签内容
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
            text_parts = []
            for p in paragraphs:
                t = clean_article_text(p)
                if len(t) > 15:
                    text_parts.append(t)
            
            if text_parts:
                return ' '.join(text_parts)
            
            # 备用：提取中文段落
            chinese = re.findall(r'[\u4e00-\u9fff][^\n<]{10,}', html)
            text_parts = [clean_article_text(c) for c in chinese if len(c) > 15][:30]
            return ' '.join(text_parts)
    except Exception as e:
        log(f"[ERROR] maobidao fetch failed: {e}")
        return ""


async def fetch_fugay(url: str) -> str:
    """抓取刘备教授文章（fugay.com）"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
            
            # 提取 <p> 标签
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
            text_parts = []
            for p in paragraphs:
                t = clean_article_text(p)
                if len(t) > 15:
                    text_parts.append(t)
            
            if text_parts:
                return ' '.join(text_parts)
            
            chinese = re.findall(r'[\u4e00-\u9fff][^\n<]{10,}', html)
            text_parts = [clean_article_text(c) for c in chinese if len(c) > 15][:30]
            return ' '.join(text_parts)
    except Exception as e:
        log(f"[ERROR] fugay fetch failed: {e}")
        return ""


async def text_to_speech(text: str, output_path: str, source_name: str, article_title: str) -> bool:
    """将文本转为MP3"""
    if not text or len(text) < 50:
        log(f"[WARN] {source_name} - {article_title}: 文章内容过短，跳过TTS")
        return False
    
    text = truncate_for_tts(text)
    
    try:
        communicate = edge_tts.Communicate(
            text,
            voice=VOICE,
            rate=VOICE_RATE,
            pitch=VOICE_PITCH,
        )
        await communicate.save(output_path)
        file_size = os.path.getsize(output_path)
        # 128kbps MP3: duration = size / (128*1024/8)
        duration_sec = int(file_size * 8 / (128 * 1024))
        log(f"[OK] {source_name}《{article_title}》: 已生成 {os.path.basename(output_path)} ({file_size//1024}KB, ~{duration_sec}秒)")
        return True
    except Exception as e:
        log(f"[ERROR] {source_name} - {article_title}: TTS失败 - {e}")
        return False


async def get_maobidao_latest() -> dict:
    """直接解析 maobidao.cn 主页获取最新文章"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://maobidao.cn/",
                                   headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            html = resp.text
            # Pattern: <a href="https://maobidao.cn/maobidao/...">文章标题</a>
            # Filter out #respond links and non-article links
            matches = re.findall(r'<a href="(https://maobidao\.cn/maobidao/[^"#]+)"[^>]*>\s*([^<\n]{3,60})\s*</a>', html)
            for url, title in matches:
                title = title.strip()
                # Skip navigation and meta links
                if any(kw in title for kw in ["发表评论", "上页", "下页", "目录", "下载", "导航", "搜索"]):
                    continue
                if title and len(title) > 4:
                    return {"title": title, "url": url}
            log("[WARN] maobidao: 主页解析未找到文章")
            return {}
    except Exception as e:
        log(f"[ERROR] maobidao homepage failed: {e}")
        return {}


async def get_fugay_latest() -> dict:
    """尝试抓取刘备教授最近7天的文章，找到有内容的那篇"""
    from datetime import datetime, timedelta
    today = datetime.now()
    
    for days_ago in range(8):  # 0-7天前
        date = today - timedelta(days=days_ago)
        url = date.strftime(f"https://www.fugay.com/%Y/%m/%d-lbjs/")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.text) > 5000:
                    html = resp.text
                    # 从 <title> 标签提取标题
                    m = re.search(r'<title>([^<]+)\s*\|\s*刘备教授', html)
                    if m:
                        title = m.group(1).strip()
                    else:
                        title = f"刘备教授·{date.strftime('%Y-%m-%d')}"
                    return {
                        "title": title,
                        "url": url,
                        "datetime": date.strftime("%Y-%m-%d"),
                    }
        except Exception:
            pass
    return {}


async def process_source(source: dict) -> dict:
    """处理单个文章来源"""
    name = source["name"]
    log(f"[INFO] === 正在抓取 {name} 的最新文章 ===")
    
    article_info = {}
    
    # 猫笔刀：直接解析主页
    if name == "猫笔刀":
        article_info = await get_maobidao_latest()
    # 刘备教授：主页+搜索脚本
    elif name == "刘备教授":
        # 先尝试直接抓取最近文章（最可靠）
        article_info = await get_fugay_latest()
        log(f"[INFO] {name}: 从存档找到《{article_info.get('title','')}》")
        # 搜索脚本结果暂时不用（返回旧文章）
    
    if not article_info or not article_info.get("url"):
        # 备用已知URL
        fallbacks = {
            "猫笔刀": {"title": "一个潜在的雷", "url": "https://maobidao.cn/maobidao/tech-comparison-housing-stock-risk/"},
            "刘备教授": {"title": "新版股王登场", "url": "https://www.fugay.com/2026/05/18-lbjs/"},
        }
        article_info = fallbacks.get(name, {})
        if article_info:
            log(f"[INFO] {name}: 使用备用URL《{article_info['title']}》")
    
    if not article_info:
        return {"name": name, "success": False, "reason": "获取文章失败"}
    
    article_title = article_info.get("title", "未知标题")
    article_url = article_info.get("url", "")
    article_date = article_info.get("datetime", "")
    
    log(f"[INFO] {name}: 最新文章《{article_title}》{article_date}")
    log(f"[INFO] {name}: URL = {article_url}")
    
    # Step 2: 抓取正文
    log(f"[INFO] {name}: 正在提取文章正文...")
    article_text = await fetch_article_content(article_url)
    
    if not article_text or len(article_text) < 100:
        log(f"[WARN] {name}: 文章正文提取失败，使用摘要代替")
        article_text = f"{article_info.get('summary', '')} {article_title}。这是来自{name}公众号的文章。"
    
    log(f"[INFO] {name}: 正文长度 {len(article_text)} 字")
    
    # Step 3: 生成MP3
    today = datetime.now().strftime("%Y%m%d")
    safe_title = re.sub(r'[\\/:*?"<>|]', '', article_title)[:25]
    filename = f"{today}_{name}_{safe_title}.mp3"
    output_path = os.path.join(AUDIO_DIR, filename)
    
    success = await text_to_speech(article_text, output_path, name, article_title)
    
    return {
        "name": name,
        "title": article_title,
        "date": article_date,
        "url": article_url,
        "mp3_path": output_path if success else None,
        "success": success,
    }


def copy_to_workspace(mp3_path: str) -> str:
    """复制MP3到工作区，以便同步到微信小程序"""
    if not mp3_path or not os.path.exists(mp3_path):
        return None
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        filename = os.path.basename(mp3_path)
        dest = os.path.join(WORKSPACE_DIR, filename)
        import shutil
        shutil.copy2(mp3_path, dest)
        return dest
    except Exception as e:
        log(f"[WARN] 复制到工作区失败: {e}")
        return None


def create_notification(results: list) -> str:
    """生成微信通知摘要文件"""
    today = datetime.now().strftime("%Y年%m月%d日")
    lines = [
        f"# 早报推送 · {today}",
        "",
        "今日公众号文章已转为语音，可直接在小程序中播放：",
        "",
    ]
    
    for r in results:
        if r["success"]:
            lines.append(f"## {r['name']}《{r['title']}》")
            lines.append(f"- 日期: {r['date']}")
            lines.append(f"- 文章链接: {r['url']}")
            lines.append(f"- 语音文件: {os.path.basename(r['mp3_path'])}")
            lines.append("")
        else:
            lines.append(f"## {r['name']} ❌ 抓取失败")
            lines.append("")
    
    lines.append("---")
    lines.append(f"生成时间: {datetime.now().strftime('%H:%M:%S')}")
    lines.append("MP3文件已同步到小程序，请打开 WorkBuddy 小程序查看")
    
    content = "\n".join(lines)
    try:
        with open(NOTIFICATION_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return content
    except Exception as e:
        log(f"[WARN] 创建通知文件失败: {e}")
        return content


def save_articles_json(results: list):
    """保存文章元数据到 articles.json，供网页应用使用"""
    try:
        os.makedirs(os.path.dirname(ARTICLES_JSON), exist_ok=True)
        
        # 读取已有数据
        existing = []
        if os.path.exists(ARTICLES_JSON):
            with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
        
        # 用 set 去重（按日期+来源）
        existing_keys = {(a["date"], a["source"]) for a in existing}
        
        for r in results:
            if not r["success"]:
                continue
            key = (r["date"], r["name"])
            if key in existing_keys:
                continue  # 已存在，跳过
            
            today_str = datetime.now().strftime("%Y-%m-%d")
            article = {
                "date": r["date"] or today_str,
                "source": r["name"],
                "title": r["title"],
                "url": r["url"],
                "audio": os.path.basename(r["mp3_path"]) if r.get("mp3_path") else "",
                "created_at": datetime.now().isoformat(),
            }
            existing.append(article)
        
        # 按日期倒序
        existing.sort(key=lambda x: x["date"], reverse=True)
        
        with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        log(f"[OK] articles.json 已更新，共 {len(existing)} 条记录")
    except Exception as e:
        log(f"[WARN] 更新 articles.json 失败: {e}")


async def send_wechat_notification(summary: str, results: list):
    """通过调用subprocess执行 deliver 命令推送微信"""
    try:
        articles = [r for r in results if r["success"]]
        if not articles:
            log("[INFO] 没有成功文章，跳过推送")
            return

        # 构建 deliver 命令参数
        today = datetime.now().strftime("%m月%d日")
        mp3_files = [r["mp3_path"] for r in articles if r.get("mp3_path")]

        # 构造通知内容
        titles = "\n".join([f"• {a['name']}《{a['title']}》" for a in articles])
        notification_content = f"📰 {today}早报\n\n{titles}\n\n语音已生成，点击播放！"

        log(f"[INFO] 准备推送微信通知，包含 {len(mp3_files)} 个音频文件")

        # 通过 cmd 工具调用 deliver（注意：自动化任务中由WorkBuddy系统处理）
        # 这里只记录信息，实际推送由 WorkBuddy 自动化系统完成
        log(f"[INFO] 通知内容: {notification_content}")
        for mp3 in mp3_files:
            log(f"[INFO] 待推送文件: {os.path.basename(mp3)}")

        log("[OK] 推送信息已记录，请确保 WorkBuddy 小程序在线以接收推送")
    except Exception as e:
        log(f"[INFO] 微信推送处理异常: {e}")


async def main():
    parse_args()
    log("=" * 60)
    mode_str = "Serverless" if SERVERLESS else "本地"
    log(f"公众号文章TTS自动化 开始运行 [{mode_str}模式]")

    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    results = []

    for source in SOURCES:
        result = await process_source(source)
        results.append(result)
        await asyncio.sleep(5)  # 避免TTS频率限制

    # 汇总
    success_count = sum(1 for r in results if r["success"])
    log(f"[SUMMARY] 共处理 {len(results)} 个来源，成功生成 {success_count} 个MP3")

    for r in results:
        if r["success"]:
            log(f"  [OK] {r['name']}《{r['title']}》")
        else:
            log(f"  [FAIL] {r['name']}: {r.get('reason', '未知原因')}")

    if success_count > 0:
        # Serverless模式：仅保存 articles.json，不做本地同步
        if SERVERLESS:
            save_articles_json(results)
            log(f"[INFO] Serverless模式: articles.json -> {ARTICLES_JSON}")
            log(f"[INFO] MP3文件目录: {AUDIO_DIR}")
        else:
            # 本地模式：复制到工作区 & 生成通知 & 微信推送
            for r in results:
                if r["success"] and r.get("mp3_path"):
                    workspace_path = copy_to_workspace(r["mp3_path"])
                    if workspace_path:
                        log(f"[INFO] 已同步到工作区: {os.path.basename(workspace_path)}")

            save_articles_json(results)
            summary = create_notification(results)
            log(f"[INFO] 通知文件已生成: {NOTIFICATION_FILE}")
            await send_wechat_notification(summary, results)
            log(f"[INFO] MP3文件目录: {AUDIO_DIR}")
            log(f"[INFO] 已同步到小程序，请打开 WorkBuddy 小程序查看")

    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
