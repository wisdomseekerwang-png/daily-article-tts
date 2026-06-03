"""
fetch_maobidao.py - Fetch 猫笔刀 articles from RSS feed for CI.

Strategy:
  1. Fetch RSS feed from maobidao.cn/feed/
  2. Parse article titles, links, dates
  3. For today's articles, fetch full content from article page
  4. Generate TTS and output articles JSON

Usage:
  python fetch_maobidao.py --output-dir ./output
"""

import argparse
import edge_tts
import httpx
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============== TTS Config ==============
VOICE = "zh-CN-XiaoxiaoNeural"
VOICE_RATE = "+10%"
VOICE_PITCH = "+0Hz"
MAX_TTS_CHARS = 3500

# ============== maobidao Config ==============
WP_API_URL = "https://maobidao.cn/wp-json/wp/v2/posts"
RSS_URL = "https://maobidao.cn/feed/"
RSS2JSON_URL = "https://api.rss2json.com/v1/api.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SOURCE_NAME = "猫笔刀"

CN_TZ = timezone(timedelta(hours=8))


def get_today_cn() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def log(msg: str):
    ts = datetime.now(CN_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def truncate_for_tts(text: str) -> str:
    if len(text) <= MAX_TTS_CHARS:
        return text
    t = text[:MAX_TTS_CHARS]
    last = max(t.rfind('\u3002'), t.rfind('\uff01'), t.rfind('\uff1f'))
    if last > MAX_TTS_CHARS * 0.6:
        return t[:last + 1]
    return t + "\u2026\u2026"


def extract_content(html: str) -> str:
    """Extract article content from HTML."""
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
    parts = []
    for p in paragraphs:
        text = re.sub(r'<[^>]+>', '', p).strip()
        if len(text) < 20:
            continue
        if any(kw in text for kw in ['扫码关注', '微信扫一扫', '阅读原文', '分享到',
                                       '更多精彩', '关注公众号', '责任编辑', '收听语音',
                                       '图片发自简书', '插入图片', '原创不易', '请点击',
                                       '点赞', '在看', '转发']):
            continue
        parts.append(text)
    return ' '.join(parts)


async def generate_tts(text: str, output_path: str, source_name: str = "", title: str = "") -> bool:
    if not text or len(text) < 100:
        return False
    text = truncate_for_tts(text)
    tts_text = f"<speak>{source_name}。<break time='1000ms'/>{title}。<break time='1000ms'/>{text}</speak>"
    try:
        comm = edge_tts.Communicate(tts_text, voice=VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
        await comm.save(output_path)
        kb = os.path.getsize(output_path) // 1024
        log(f"  TTS: {os.path.basename(output_path)} ({kb}KB)")
        return True
    except Exception as e:
        log(f"  TTS error: {e}")
        return False


def load_json(path: str, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(data, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_rss(xml_text: str) -> list:
    """Parse RSS feed and return list of articles."""
    root = ET.fromstring(xml_text)
    ns = {'content': 'http://purl.org/rss/1.0/modules/content/',
          'dc': 'http://purl.org/dc/elements/1.1/'}

    items = []
    for item in root.findall('.//item'):
        title = item.find('title').text or ""
        link = item.find('link').text or ""
        pub_date = item.find('pubDate').text or ""

        # Parse date: "Mon, 02 Jun 2026 08:30:00 +0000"
        try:
            dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
            date_str = dt.astimezone(CN_TZ).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_str = ""

        # Get content:encoded
        content_el = item.find('content:encoded', ns)
        content_html = content_el.text if content_el is not None and content_el.text else ""

        items.append({
            "title": title,
            "link": link,
            "date": date_str,
            "content_html": content_html,
        })

    return items


def parse_rss_json(data: dict) -> list:
    """Parse RSS2JSON API response and return list of articles."""
    items = []
    for item in data.get("items", []):
        pub_date = item.get("pubDate", "")
        try:
            dt = datetime.strptime(pub_date, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            try:
                dt = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%S%z")
                date_str = dt.astimezone(CN_TZ).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_str = ""

        content_html = item.get("content", "") or item.get("description", "")
        items.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "date": date_str,
            "content_html": content_html,
        })
    return items


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--articles-json", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    articles_file = args.articles_json or str(output_dir / "articles_maobidao.json")
    today = get_today_cn()
    log(f"Today (UTC+8): {today}")

    # Load existing articles for dedup
    existing_articles = load_json(articles_file, default=[])

    # Step 1: Fetch articles (try WP REST API, then RSS direct, then RSS2JSON)
    items = []
    
    # Method 1: WordPress REST API (bypasses Cloudflare, returns full content)
    log(f"Fetching WP REST API: {WP_API_URL}")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(f"{WP_API_URL}?per_page=10")
            if resp.status_code == 200:
                posts = json.loads(resp.text)
                if isinstance(posts, list):
                    for p in posts:
                        title_html = p.get("title", {}).get("rendered", "")
                        title = re.sub(r'<[^>]+>', '', title_html).strip()
                        content_html = p.get("content", {}).get("rendered", "")
                        link = p.get("link", "")
                        date_str = p.get("date", "")[:10]
                        items.append({
                            "title": title,
                            "link": link,
                            "date": date_str,
                            "content_html": content_html,
                        })
                    log(f"WP REST API: {len(items)} items fetched")
    except Exception as e:
        log(f"WP REST API error: {e}")

    # Method 2: RSS direct (works locally, may be CF-blocked in CI)
    if not items:
        log(f"Trying direct RSS: {RSS_URL}")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                          headers={"User-Agent": USER_AGENT}) as client:
                resp = await client.get(RSS_URL)
                if resp.status_code == 200 and 'Just a moment' not in resp.text:
                    items = parse_rss(resp.text)
                    log(f"RSS direct: {len(items)} items fetched")
                else:
                    log(f"RSS direct failed: HTTP {resp.status_code}")
        except Exception as e:
            log(f"RSS direct error: {e}")

    # Method 3: RSS2JSON fallback (bypasses CF, but only returns summaries)
    if not items:
        rss2json_url = f"{RSS2JSON_URL}?rss_url={RSS_URL}"
        log(f"Trying RSS2JSON fallback")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                          headers={"User-Agent": USER_AGENT}) as client:
                resp = await client.get(rss2json_url)
                if resp.status_code == 200:
                    data = json.loads(resp.text)
                    if data.get("status") == "ok":
                        items = parse_rss_json(data)
                        log(f"RSS2JSON: {len(items)} items fetched (summaries only)")
                    else:
                        log(f"RSS2JSON error: {data.get('message', 'unknown')}")
        except Exception as e:
            log(f"RSS2JSON error: {e}")

    if not items:
        log("All fetch methods failed, exiting")
        save_json(existing_articles, articles_file)
        return

    # Step 3: Find today's articles
    today_items = [i for i in items if i["date"] == today]
    log(f"Today's articles: {len(today_items)}")

    if not today_items:
        log("No articles published today")
        save_json(existing_articles, articles_file)
        return

    # Step 4: Fetch content & generate TTS
    new_articles = []
    existing_keys = {(a.get("date", ""), a.get("source", "")) for a in existing_articles}
    existing_urls = {a.get("url", "") for a in existing_articles if a.get("url")}
    existing_titles = {(a.get("source", ""), a.get("title", "")) for a in existing_articles}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                  headers={"User-Agent": USER_AGENT}) as client:
        for item in today_items:
            key = (item["date"], SOURCE_NAME)
            if key in existing_keys:
                log(f"  Skip (date+source exists): {item['title'][:40]}")
                continue
            if item["link"] and item["link"] in existing_urls:
                log(f"  Skip (URL exists): {item['title'][:40]}")
                continue
            title_key = (SOURCE_NAME, item["title"])
            if title_key in existing_titles:
                log(f"  Skip (title exists): {item['title'][:40]}")
                continue

            # Try to get content from RSS first, then from article page
            content = ""
            if item["content_html"]:
                content = extract_content(item["content_html"])

            # If RSS content is too short, fetch article page (may also be CF-blocked)
            if len(content) < 200 and item["link"]:
                log(f"  Fetching article page: {item['link'][:60]}")
                try:
                    resp = await client.get(item["link"])
                    if resp.status_code == 200 and len(resp.text) > 5000:
                        content = extract_content(resp.text)
                    else:
                        log(f"  Article page: HTTP {resp.status_code} (skipping)")
                except Exception as e:
                    log(f"  Article page error: {e}")

            if len(content) < 100:
                log(f"  Content too short: '{item['title'][:30]}' ({len(content)} chars)")
                continue

            # Generate TTS
            safe_title = re.sub(r'[\\/:*?"<>|\s]', '_', item['title'])[:30]
            mp3_name = f"{today}_{SOURCE_NAME}_{safe_title}.mp3"
            mp3_path = str(audio_dir / mp3_name)

            tts_ok = await generate_tts(content, mp3_path, SOURCE_NAME, item["title"])

            article_entry = {
                "date": item["date"],
                "source": SOURCE_NAME,
                "title": item["title"],
                "url": item["link"],
                "audio": mp3_name if tts_ok else "",
                "created_at": datetime.now(CN_TZ).isoformat(),
            }
            new_articles.append(article_entry)
            existing_keys.add(key)
            if item["link"]:
                existing_urls.add(item["link"])
            existing_titles.add(title_key)
            log(f"  [NEW] '{item['title'][:40]}' ({item['date']})")

    # Save articles
    existing_articles.extend(new_articles)
    existing_articles.sort(key=lambda x: x.get("date", ""), reverse=True)
    save_json(existing_articles, articles_file)

    if new_articles:
        log(f"\n=== Added {len(new_articles)} new article(s) ===")
    else:
        log(f"\n=== No new articles today ({len(existing_articles)} total) ===")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
