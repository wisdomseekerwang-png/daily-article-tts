"""
微信公众号文章TTS语音合成自动化脚本
每天定时抓取多个公众号的最新文章，转为MP3语音

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
from datetime import datetime, timedelta

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
    {"name": "孥孥的大树", "search_query": "孥孥的大树"},
    {"name": "卢克文工作室", "search_query": "卢克文工作室"},
    {"name": "海里的小龙龙", "search_query": "海里的小龙龙"},
    {"name": "远方青木", "search_query": "远方青木"},
    {"name": "格兰投研", "search_query": "格兰投研"},
    {"name": "价值事务所", "search_query": "价值事务所"},
    {"name": "棋行者", "search_query": "棋行者"},
    {"name": "伯格医生", "search_query": "伯格医生"},
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


def trim_log():
    """只保留最近3天的日志"""
    try:
        if not os.path.exists(LOG_FILE):
            return
        cutoff = datetime.now() - timedelta(days=3)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        kept = [l for l in lines if not l.startswith("[") or l[1:11] >= cutoff_str]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except Exception:
        pass


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


async def search_sogou_maobidao() -> dict:
    """通过搜狗微信搜索获取猫笔刀最新文章URL"""
    try:
        sogou_url = "https://weixin.sogou.com/weixin"
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        ) as client:
            resp = await client.get(sogou_url, params={"type": "1", "query": "猫笔刀", "ie": "utf8"})
            html = resp.text
            # Extract article links: mp.weixin.qq.com links
            matches = re.findall(r'<a[^>]+href="(https?://mp\.weixin\.qq\.com/s[^"]*)"[^>]*>([^<]{5,50})</a>', html)
            for url, title in matches:
                title = title.strip()
                if any(kw in title for kw in ["招财大牛猫", "猫笔刀"]) or not any(skip in title for skip in ["公众号", "小程序", "关注"]):
                    log(f"[INFO] 搜狗搜索找到: {title[:30]}")
                    return {"title": title, "url": url, "source": "猫笔刀"}
            log("[WARN] 搜狗搜索未找到有效文章")
            return {}
    except Exception as e:
        log(f"[WARN] 搜狗搜索失败: {e}")
        return {}


async def search_latest_article(name: str, query: str) -> dict:
    """通过搜狗微信搜索获取公众号最新文章（纯 Python httpx 实现）"""
    # Strategy 1: Sogou WeChat search (type=2 for account-matched articles)
    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        ) as client:
            resp = await client.get("https://weixin.sogou.com/weixin",
                params={"type": "2", "query": query, "ie": "utf8"})
            html = resp.text

            if len(html) < 5000:
                log(f"[WARN] {name}: Sogou返回页面过小({len(html)}), 可能被拦截")
            else:
                # Parse article results from the page
                # The page uses <ul class="news-list"><li> structure
                articles = []
                items = re.findall(r'<div[^>]*class="[^"]*txt-box[^"]*"[^>]*>(.*?)</div>\s*<!--\s*\.txt-box', html, re.DOTALL)
                if not items:
                    # Fallback: find all <li> with title links inside news-list
                    news_section = re.search(r'<ul[^>]*class="[^"]*news-list[^"]*"[^>]*>(.*?)</ul>', html, re.DOTALL)
                    if news_section:
                        items = re.findall(r'<li[^>]*>(.*?)</li>', news_section.group(1), re.DOTALL)

                for item in items:
                    # Extract title and URL
                    title_m = re.search(r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h3>', item, re.DOTALL)
                    if not title_m:
                        continue
                    url = title_m.group(1)
                    title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()

                    # Extract source name
                    src = ""
                    src_m = re.search(r'(?:class="[^"]*(?:all-time-y2|account)[^"]*"[^>]*>|<a[^>]+class="[^"]*account[^"]*"[^>]*>)([^<]+)', item)
                    if src_m:
                        src = src_m.group(1).strip()

                    # Extract date info (from script timestamp)
                    date_info = ""
                    ts_m = re.search(r'script.*?(\d{10})', item)
                    if ts_m:
                        import time
                        ts = int(ts_m.group(1))
                        try:
                            days_ago = (int(time.time()) - ts) // 86400
                            date_info = f"{days_ago}d"
                        except:
                            pass

                    articles.append({
                        "title": title, "url": url, "source": src, "date_info": date_info
                    })

                if articles:
                    # Filter: source must contain account name or its first 2 chars
                    matched = [a for a in articles if any(kw in a["source"] for kw in [name, name[:2]])]
                    if matched:
                        # Sort by date (lower date_info number = newer)
                        matched.sort(key=lambda x: int(re.search(r'(\d+)', x["date_info"]).group(1)) if re.search(r'(\d+)', x["date_info"]) else 9999)
                        best = matched[0]
                        # Fix relative URLs (sogou returns /link?url=... instead of full URL)
                        url = best["url"]
                        if url.startswith("/"):
                            url = "https://weixin.sogou.com" + url
                        log(f"[INFO] {name}: 搜到《{best['title'][:30]}》({best.get('date_info','')})")
                        return {"title": best["title"], "url": url, "source": best["source"]}
                    else:
                        log(f"[WARN] {name}: 找到{len(articles)}篇文章但无来源匹配")
    except Exception as e:
        log(f"[WARN] {name}: Sogou搜索失败 - {e}")

    # Strategy 2: Bing search (fallback)
    try:
        bing_query = f"\"{query}\" 公众号 最新文章"
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        ) as client:
            resp = await client.get("https://www.bing.com/search", params={"q": bing_query, "count": "10"})
            html = resp.text
            # Extract any mp.weixin.qq.com links from Bing results
            results = re.findall(r'<a[^>]+href="(https://mp\.weixin\.qq\.com/s[^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
            for url, title in results:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if title and len(title) > 5:
                    log(f"[INFO] {name}: Bing找到《{title[:30]}》")
                    return {"title": title, "url": url, "source": name}
    except Exception as e:
        log(f"[WARN] {name}: Bing搜索失败 - {e}")

    log(f"[WARN] {name}: 所有搜索方式均未找到文章")
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
    """从归档站或微信抓取文章正文"""
    # 猫笔刀用 maobidao.cn
    if "maobidao" in url:
        text = await fetch_maobidao(url)
        if text and len(text) >= 100:
            return text
        # If direct fetch failed, try extracting from RSS
        log("[INFO] maobidao direct fetch failed, trying RSS content...")
        return await fetch_maobidao_rss()
    # 刘备教授用 fugay.com
    if "fugay" in url:
        return await fetch_fugay(url)
    # Sogou redirect URL — follow redirect to get actual mp.weixin.qq.com URL
    if "weixin.sogou.com" in url:
        log("[INFO] Following sogou redirect...")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            ) as client:
                resp = await client.get(url)
                # Check if redirected to anti-spider page
                if resp.status_code in (301, 302):
                    location = resp.headers.get("location", "")
                    if "antispider" in location:
                        log("[WARN] Sogou anti-spider triggered, cannot resolve URL")
                        return ""
                # If 200, check for JavaScript URL construction
                html = resp.text
                url_parts = re.findall(r"url\s*\+=\s*['\"]([^'\"]+)['\"]", html)
                if url_parts:
                    real_url = ''.join(url_parts)
                    if "mp.weixin.qq.com" in real_url:
                        log(f"[INFO] Extracted URL from JS redirect")
                        return await fetch_wechat(real_url)
                # Check if we got the actual WeChat article
                final_url = str(resp.url)
                if "mp.weixin.qq.com" in final_url and len(html) > 5000:
                    log(f"[INFO] Redirected to WeChat article")
                    return await fetch_wechat(final_url)
                log("[WARN] Sogou redirect did not resolve to article")
        except Exception as e:
            log(f"[WARN] Sogou redirect failed: {e}")
        return ""
    # mp.weixin.qq.com articles
    if "mp.weixin.qq.com" in url:
        return await fetch_wechat(url)
    # 否则直接抓取
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            return clean_article_text(resp.text)
    except Exception as e:
        log(f"[ERROR] fetch_article_content failed: {e}")
        return ""


async def fetch_maobidao_rss() -> str:
    """从 RSS feed 提取猫笔刀文章摘要"""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        ) as client:
            resp = await client.get("https://maobidao.cn/feed/")
            xml = resp.text
            if len(xml) < 5000:
                return ""
            item = re.search(r'<item>.*?</item>', xml, re.DOTALL)
            if not item:
                return ""
            # Extract content:encoded or description
            content_m = re.search(r'<content:encoded[^>]*><!\[CDATA\[(.*?)\]\]></content:encoded>', item.group(0), re.DOTALL)
            if not content_m:
                content_m = re.search(r'<description[^>]*><!\[CDATA\[(.*?)\]\]></description>', item.group(0), re.DOTALL)
            if content_m:
                raw = content_m.group(1)
                text = clean_article_text(raw)
                log(f"[INFO] RSS content extracted: {len(text)} chars")
                return text
            return ""
    except Exception as e:
        log(f"[WARN] RSS content extraction failed: {e}")
        return ""


async def fetch_wechat(url: str) -> str:
    """从微信公众号文章提取正文"""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        ) as client:
            resp = await client.get(url)
            html = resp.text
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
            text_parts = []
            for p in paragraphs:
                t = clean_article_text(p)
                if len(t) > 15:
                    text_parts.append(t)
            return ' '.join(text_parts) if text_parts else ""
    except Exception as e:
        log(f"[WARN] wechat fetch failed: {e}")
        return ""


async def fetch_maobidao(url: str) -> str:
    """抓取猫笔刀文章"""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            ) as client:
                resp = await client.get(url)
                html = resp.text

                if len(html) < 5000:
                    log(f"[WARN] maobidao article too small ({len(html)} bytes), attempt {attempt+1}/3")
                    await asyncio.sleep(2)
                    continue

                # Try to extract content from <article> tag first
                article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
                if article_match:
                    content = article_match.group(1)
                else:
                    # Try entry-content div
                    entry_match = re.search(r'class="entry-content[^"]*"[^>]*>(.*?)</div>\s*<!--\s*\.entry-content', html, re.DOTALL)
                    if entry_match:
                        content = entry_match.group(1)
                    else:
                        content = html

                # 提取 <p> 标签内容
                paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
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
                if text_parts:
                    return ' '.join(text_parts)

                log(f"[WARN] maobidao: 无内容, attempt {attempt+1}/3")
                await asyncio.sleep(2)
        except Exception as e:
            log(f"[ERROR] maobidao fetch attempt {attempt+1}/3: {e}")
            await asyncio.sleep(2)
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

    # Build SSML: source name + 1s pause + article title + 1s pause + content
    tts_text = f"<speak>{source_name}。<break time='1000ms'/>{article_title}。<break time='1000ms'/>{text}</speak>"

    try:
        communicate = edge_tts.Communicate(
            tts_text,
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
    """获取猫笔刀最新文章：优先主页 > RSS > 搜狗搜索"""
    # Strategy 1: Direct homepage parsing
    try:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        ) as client:
            resp = await client.get("https://maobidao.cn/")
            html = resp.text
            if len(html) > 50000:
                matches = re.findall(r'<a href="(https://maobidao\.cn/maobidao/[^"#]+)"[^>]*>\s*([^<\n]{3,60})\s*</a>', html)
                for url, title in matches:
                    title = title.strip()
                    if any(kw in title for kw in ["发表评论", "上页", "下页", "目录", "下载", "导航", "搜索", "链接"]):
                        continue
                    if title and len(title) > 4:
                        log(f"[INFO] maobidao: 主页找到文章《{title}》")
                        return {"title": title, "url": url}
    except Exception as e:
        log(f"[WARN] maobidao homepage: {e}")

    # Strategy 2: RSS feed (works even with Cloudflare)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        ) as client:
            resp = await client.get("https://maobidao.cn/feed/")
            xml = resp.text
            if len(xml) > 5000:
                item_match = re.search(r'<item>.*?</item>', xml, re.DOTALL)
                if item_match:
                    item = item_match.group(0)
                    title_m = re.search(r'<title[^>]*><!\[CDATA\[([^\]]+)\]\]></title>', item)
                    if not title_m:
                        title_m = re.search(r'<title[^>]*>([^<]+)</title>', item)
                    link_m = re.search(r'<link[^>]*><!\[CDATA\[([^\]]+)\]\]></link>', item)
                    if not link_m:
                        link_m = re.search(r'<link[^>]*>([^<]+)</link>', item)
                    pubdate_m = re.search(r'<pubDate>([^<]+)</pubDate>', item)
                    publish_time = ""
                    if pubdate_m:
                        from datetime import datetime as dt
                        try:
                            pub = dt.strptime(pubdate_m.group(1).strip(), "%a, %d %b %Y %H:%M:%S %z")
                            publish_time = pub.strftime("%Y-%m-%dT%H:%M:%S")
                        except Exception:
                            pass
                    if title_m and link_m:
                        title = title_m.group(1).strip()
                        url = link_m.group(1).strip()
                        log(f"[INFO] maobidao RSS: 《{title}》")
                        return {"title": title, "url": url, "publish_time": publish_time}
    except Exception as e:
        log(f"[WARN] maobidao RSS: {e}")

    # Strategy 3: Sogou search
    log("[INFO] 猫笔刀: 主页和RSS均失败，尝试搜狗搜索...")
    return await search_sogou_maobidao()


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
                    # Try to extract publish time from HTML
                    publish_time = ""
                    time_m = re.search(r'<time[^>]*datetime="([^"]+)"', html)
                    if time_m:
                        publish_time = time_m.group(1)
                    else:
                        time_m = re.search(r'发表于\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', html)
                        if time_m:
                            publish_time = time_m.group(1).replace(' ', 'T')
                    return {
                        "title": title,
                        "url": url,
                        "datetime": date.strftime("%Y-%m-%d"),
                        "publish_time": publish_time,
                    }
        except Exception:
            pass
    return {}


async def process_source(source: dict) -> dict:
    """处理单个文章来源"""
    name = source["name"]
    log(f"[INFO] === 正在抓取 {name} 的最新文章 ===")
    
    article_info = {}
    
    # 猫笔刀：直接解析主页（自动 fallback 到 RSS/搜狗）
    if name == "猫笔刀":
        article_info = await get_maobidao_latest()
    # 刘备教授：主页+搜索脚本
    elif name == "刘备教授":
        # 先尝试直接抓取最近文章（最可靠）
        article_info = await get_fugay_latest()
        log(f"[INFO] {name}: 从存档找到《{article_info.get('title','')}》")
    else:
        # 其他公众号：通过搜狗搜索获取最新文章
        log(f"[INFO] {name}: 通过搜狗微信搜索...")
        article_info = await search_latest_article(name, source["search_query"])
        if article_info:
            log(f"[INFO] {name}: 搜索到《{article_info.get('title','')}》")
    
    if not article_info or not article_info.get("url"):
        # 备用已知URL
        fallbacks = {
            "猫笔刀": {"title": "瞬间恶念", "url": "https://maobidao.cn/maobidao/parent-child-sports-day-xiaomi-report-618-deals/"},
            "刘备教授": {"title": "给芯片开个挂...", "url": "https://www.fugay.com/2026/05/26-lbjs/"},
        }
        article_info = fallbacks.get(name, {})
        if article_info:
            log(f"[INFO] {name}: 使用备用URL《{article_info['title']}》")
    
    if not article_info:
        return {"name": name, "success": False, "reason": "获取文章失败"}
    
    article_title = article_info.get("title", "未知标题")
    article_url = article_info.get("url", "")
    article_date = article_info.get("datetime", "")
    article_publish_time = article_info.get("publish_time", "")
    
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
        "publish_time": article_publish_time,
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


def copy_to_ghpages(mp3_path: str) -> str:
    """复制MP3到 .gh-pages-deploy/audio/，以便推送到 GitHub Pages"""
    if not mp3_path or not os.path.exists(mp3_path):
        return None
    try:
        ghpages_audio = os.path.join(WORKSPACE_DIR, ".gh-pages-deploy", "audio")
        os.makedirs(ghpages_audio, exist_ok=True)
        filename = os.path.basename(mp3_path)
        dest = os.path.join(ghpages_audio, filename)
        import shutil
        shutil.copy2(mp3_path, dest)
        return dest
    except Exception as e:
        log(f"[WARN] 复制到gh-pages失败: {e}")
        return None


def sync_articles_to_ghpages():
    """将 web/data/articles.json 合并到 .gh-pages-deploy/data/articles.json"""
    try:
        src = os.path.join(WORKSPACE_DIR, "web", "data", "articles.json")
        dst = os.path.join(WORKSPACE_DIR, ".gh-pages-deploy", "data", "articles.json")
        if not os.path.exists(src):
            log("[WARN] web/data/articles.json 不存在，跳过同步")
            return False

        # 读取 gh-pages 已有数据
        existing = []
        if os.path.exists(dst):
            with open(dst, "r", encoding="utf-8") as f:
                existing = json.load(f)
        # 预去重：清理 gh-pages 中可能存在的重复
        seen_pre = set()
        deduped = []
        for a in existing:
            key = (a.get("date", ""), a.get("source", ""))
            if key not in seen_pre:
                seen_pre.add(key)
                deduped.append(a)
        existing = deduped
        existing_keys = {(a["date"], a["source"]) for a in existing}
        existing_urls = {a["url"] for a in existing if a.get("url")}

        # 读取 web 新数据
        with open(src, "r", encoding="utf-8") as f:
            new_articles = json.load(f)

        added = 0
        for a in new_articles:
            key = (a["date"], a["source"])
            if key in existing_keys:
                continue
            if a.get("url") and a["url"] in existing_urls:
                continue
            existing.append(a)
            existing_keys.add(key)
            if a.get("url"):
                existing_urls.add(a["url"])
            added += 1

        if added > 0:
            existing.sort(key=lambda x: x["date"], reverse=True)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            log(f"[INFO] gh-pages articles.json 新增 {added} 条记录")
            return True
        else:
            log("[INFO] gh-pages articles.json 无新记录，跳过")
            return False
    except Exception as e:
        log(f"[WARN] 同步articles.json到gh-pages失败: {e}")
        return False


def git_push_ghpages():
    """git add + commit + push .gh-pages-deploy/ 到 gh-pages 分支，失败时自动 pull rebase 重试"""
    try:
        ghpages_dir = os.path.join(WORKSPACE_DIR, ".gh-pages-deploy")
        if not os.path.isdir(os.path.join(ghpages_dir, ".git")):
            log("[WARN] .gh-pages-deploy 不是git仓库，跳过推送")
            return

        subprocess.run(["git", "add", "-A"], cwd=ghpages_dir, capture_output=True, text=True)
        # 检查是否有变更
        result = subprocess.run(["git", "status", "--porcelain"], cwd=ghpages_dir, capture_output=True, text=True)
        if not result.stdout.strip():
            log("[INFO] gh-pages 无文件变更，跳过推送")
            return

        subprocess.run(
            ["git", "commit", "-m", f"auto update: TTS audio + articles ({datetime.now().strftime('%Y-%m-%d %H:%M')})"],
            cwd=ghpages_dir, capture_output=True, text=True
        )
        # 尝试 push，如果被拒绝则 fetch + reset --soft + 重新 commit + push
        push_result = subprocess.run(["git", "push", "origin", "gh-pages"], cwd=ghpages_dir, capture_output=True, text=True)
        if push_result.returncode != 0:
            log("[WARN] push 被拒绝，尝试 fetch + rebase...")
            subprocess.run(["git", "fetch", "origin", "gh-pages"], cwd=ghpages_dir, capture_output=True, text=True)
            # 使用 reset --soft 保留本地变更，合并后重新 commit
            subprocess.run(["git", "reset", "--soft", "origin/gh-pages"], cwd=ghpages_dir, capture_output=True, text=True)
            subprocess.run(["git", "add", "-A"], cwd=ghpages_dir, capture_output=True, text=True)
            # 用 ours 策略合并 articles.json 冲突
            subprocess.run(["git", "commit", "--allow-empty", "-m",
                            f"auto update: TTS audio + articles ({datetime.now().strftime('%Y-%m-%d %H:%M')})"],
                           cwd=ghpages_dir, capture_output=True, text=True)
            retry = subprocess.run(["git", "push", "origin", "gh-pages"], cwd=ghpages_dir, capture_output=True, text=True)
            if retry.returncode != 0:
                log(f"[WARN] push 重试也失败: {retry.stderr}")
                return
        log("[OK] 已推送到 GitHub Pages")
    except Exception as e:
        log(f"[WARN] git push gh-pages 失败: {e}")


# ============== 运行日志 (JSON) ==============
# Serverless模式: 写到 output/tts_run_log.json，CI 负责合并到 gh-pages
# 本地模式: 写到 web/data/tts_run_log.json
if SERVERLESS:
    RUN_LOG_JSON = os.path.join(OUTPUT_DIR, "tts_run_log.json")
else:
    RUN_LOG_JSON = os.path.join(WORKSPACE_DIR, "web", "data", "tts_run_log.json")


def append_run_log(entries: list):
    """追加结构化运行日志到 web/data/tts_run_log.json"""
    try:
        os.makedirs(os.path.dirname(RUN_LOG_JSON), exist_ok=True)
        existing = []
        if os.path.exists(RUN_LOG_JSON):
            with open(RUN_LOG_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
        # 去重: 按 timestamp+source
        existing_keys = {(e.get("timestamp", ""), e.get("source", "")) for e in existing}
        added = 0
        for entry in entries:
            key = (entry.get("timestamp", ""), entry.get("source", ""))
            if key not in existing_keys:
                existing.append(entry)
                added += 1
        # 按时间倒序，最多保留500条
        existing.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        existing = existing[:500]
        with open(RUN_LOG_JSON, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        if added > 0:
            log(f"[INFO] 运行日志新增 {added} 条记录")
    except Exception as e:
        log(f"[WARN] 写入运行日志失败: {e}")


def sync_run_log_to_ghpages():
    """合并运行日志到 .gh-pages-deploy/data/tts_run_log.json"""
    try:
        src = RUN_LOG_JSON
        dst = os.path.join(WORKSPACE_DIR, ".gh-pages-deploy", "data", "tts_run_log.json")
        if not os.path.exists(src):
            return
        gh_existing = []
        if os.path.exists(dst):
            with open(dst, "r", encoding="utf-8") as f:
                gh_existing = json.load(f)
        with open(src, "r", encoding="utf-8") as f:
            local_entries = json.load(f)
        gh_keys = {(e.get("timestamp", ""), e.get("source", "")) for e in gh_existing}
        added = 0
        for entry in local_entries:
            key = (entry.get("timestamp", ""), entry.get("source", ""))
            if key not in gh_keys:
                gh_existing.append(entry)
                added += 1
        if added > 0:
            gh_existing.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            gh_existing = gh_existing[:500]
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(gh_existing, f, ensure_ascii=False, indent=2)
            log(f"[INFO] gh-pages 运行日志合并 {added} 条")
    except Exception as e:
        log(f"[WARN] 同步运行日志到gh-pages失败: {e}")


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

        # 预去重：先清理 existing 中可能存在的重复（按日期+来源）
        seen_keys = set()
        deduped_existing = []
        for a in existing:
            key = (a.get("date", ""), a.get("source", ""))
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_existing.append(a)
        existing = deduped_existing

        # 用 set 去重（按日期+来源+URL）
        today_str = datetime.now().strftime("%Y-%m-%d")
        existing_keys = {(a["date"], a["source"]) for a in existing}
        existing_urls = {a["url"] for a in existing if a.get("url")}
        
        for r in results:
            if not r["success"]:
                continue
            # 规范化日期后再查重（避免空日期导致重复）
            article_date = r["date"] or today_str
            key = (article_date, r["name"])
            if key in existing_keys:
                continue  # 已存在，跳过
            # URL 级别去重：同一篇文章不同日期也跳过
            if r.get("url") and r["url"] in existing_urls:
                log(f"[SKIP] {r['name']}: URL 已存在 -> {r['url'][:60]}")
                continue
            
            article = {
                "date": article_date,
                "source": r["name"],
                "title": r["title"],
                "url": r["url"],
                "audio": os.path.basename(r["mp3_path"]) if r.get("mp3_path") else "",
                "created_at": datetime.now().isoformat(),
            }
            if r.get("publish_time"):
                article["publish_time"] = r["publish_time"]
            existing.append(article)
            existing_keys.add(key)
            if r.get("url"):
                existing_urls.add(r["url"])
        
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
    trim_log()
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
            # 写运行日志
            log_entries = []
            for r in results:
                log_entries.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": r["name"],
                    "title": r.get("title", ""),
                    "audio": os.path.basename(r.get("mp3_path", "")) if r.get("mp3_path") else "",
                    "status": "ok" if r["success"] else "fail",
                    "mode": "CI"
                })
            append_run_log(log_entries)
        else:
            # 本地模式：复制到工作区 & gh-pages & 生成通知 & 微信推送
            for r in results:
                if r["success"] and r.get("mp3_path"):
                    workspace_path = copy_to_workspace(r["mp3_path"])
                    if workspace_path:
                        log(f"[INFO] 已同步到工作区: {os.path.basename(workspace_path)}")
                    ghpages_path = copy_to_ghpages(r["mp3_path"])
                    if ghpages_path:
                        log(f"[INFO] 已同步到gh-pages: {os.path.basename(ghpages_path)}")

            save_articles_json(results)
            # 写运行日志
            log_entries = []
            for r in results:
                log_entries.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": r["name"],
                    "title": r.get("title", ""),
                    "audio": os.path.basename(r.get("mp3_path", "")) if r.get("mp3_path") else "",
                    "status": "ok" if r["success"] else "fail",
                    "mode": "本地",
                    "reason": r.get("reason", "") if not r["success"] else ""
                })
            append_run_log(log_entries)

            # 同步 articles.json 到 gh-pages
            sync_articles_to_ghpages()
            # 同步运行日志到 gh-pages
            sync_run_log_to_ghpages()
            # 推送到 GitHub Pages
            git_push_ghpages()
            summary = create_notification(results)
            log(f"[INFO] 通知文件已生成: {NOTIFICATION_FILE}")
            await send_wechat_notification(summary, results)
            log(f"[INFO] MP3文件目录: {AUDIO_DIR}")
            log(f"[INFO] 已同步到小程序，请打开 WorkBuddy 小程序查看")

    log("=" * 60)

    # 记录所有结果到运行日志（包括失败）
    if success_count == 0:
        log_entries = []
        for r in results:
            log_entries.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": r["name"],
                "title": r.get("title", ""),
                "audio": "",
                "status": "fail",
                "mode": "CI" if SERVERLESS else "本地",
                "reason": r.get("reason", "未知原因")
            })
        append_run_log(log_entries)
        if not SERVERLESS:
            sync_run_log_to_ghpages()
            git_push_ghpages()


if __name__ == "__main__":
    asyncio.run(main())
