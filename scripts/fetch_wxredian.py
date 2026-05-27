"""
fetch_wxredian.py - Fetch WeChat articles from wxredian.com for CI (async parallel).

Strategy:
  1. For each author, fetch a seed article page (1 request)
  2. Extract sidebar article IDs (~50 per author)
  3. Async parallel fetch all new article pages to get dates (fast)
  4. If any article is from today -> fetch content + generate TTS
  5. Update seed to the most recent article found

Usage:
  python fetch_wxredian.py --output-dir ./output
"""

import asyncio
import argparse
import edge_tts
import httpx
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============== TTS Config ==============
VOICE = "zh-CN-XiaoxiaoNeural"
VOICE_RATE = "+10%"
VOICE_PITCH = "+0Hz"
MAX_TTS_CHARS = 3500

# ============== wxredian Config ==============
BASE_URL = "https://wxredian.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

CN_TZ = timezone(timedelta(hours=8))


def get_today_cn() -> str:
    return datetime.now(CN_TZ).strftime("%Y-%m-%d")


def log(msg: str):
    ts = datetime.now(CN_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


async def fetch_article_meta(article_id: str, client: httpx.AsyncClient) -> dict:
    """Fetch article page and extract metadata (title, date, sidebar IDs, content)."""
    url = f"{BASE_URL}/art?id={article_id}"
    try:
        resp = await client.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text

        if len(html) < 1000:
            return {"id": article_id, "error": f"Page too small ({len(html)})"}

        # Title
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""

        # Date and time
        dt_m = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', html)
        date_str = dt_m.group(1)[:10] if dt_m else ""
        time_str = dt_m.group(1) if dt_m else ""

        # Sidebar IDs
        sidebar_ids = list(set(re.findall(r'/art\?id=([a-f0-9]{32})', html)))
        if article_id in sidebar_ids:
            sidebar_ids.remove(article_id)

        return {
            "id": article_id,
            "url": url,
            "title": title,
            "date": date_str,
            "publish_time": time_str.replace(' ', 'T') if time_str else "",
            "sidebar_ids": sidebar_ids,
            "html": html,  # Keep for content extraction if needed
        }
    except Exception as e:
        return {"id": article_id, "error": str(e)}


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
                                       '图片发自简书', '插入图片']):
            continue
        parts.append(text)
    return ' '.join(parts)


def truncate_for_tts(text: str) -> str:
    if len(text) <= MAX_TTS_CHARS:
        return text
    t = text[:MAX_TTS_CHARS]
    last = max(t.rfind('\u3002'), t.rfind('\uff01'), t.rfind('\uff1f'))
    if last > MAX_TTS_CHARS * 0.6:
        return t[:last + 1]
    return t + "\u2026\u2026"


async def generate_tts(text: str, output_path: str, source_name: str = "", title: str = "") -> bool:
    if not text or len(text) < 100:
        return False
    text = truncate_for_tts(text)
    # Build SSML: source name + 1s pause + article title + 1s pause + content
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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--articles-json", default=None)
    parser.add_argument("--config-file", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    state_file = args.state_file or str(output_dir / "wxredian_state.json")
    articles_file = args.articles_json or str(output_dir / "articles.json")
    config_file = args.config_file or str(Path(__file__).parent / "wxredian_config.json")

    if not os.path.exists(config_file):
        log(f"ERROR: Config not found: {config_file}")
        sys.exit(1)

    config = load_json(config_file)
    today = get_today_cn()
    log(f"Today (UTC+8): {today}")

    state = load_json(state_file, default={})
    existing_articles = load_json(articles_file, default=[])
    existing_keys = {(a.get("date", ""), a.get("source", "")) for a in existing_articles}
    new_articles = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:

        for author_name, author_cfg in config.get("authors", {}).items():
            seed_id = author_cfg["seed_id"]
            log(f"\n=== {author_name} (seed: {seed_id[:8]}...) ===")

            if author_name not in state:
                state[author_name] = {"known_ids": [], "latest_seed_id": seed_id}

            astate = state[author_name]

            # Step 1: Fetch seed article to get sidebar
            seed = await fetch_article_meta(seed_id, client)
            if seed.get("error"):
                log(f"  Seed error: {seed['error']}")
                continue

            log(f"  Seed: '{seed['title'][:40]}' ({seed['date']}) | Sidebar: {len(seed.get('sidebar_ids', []))} articles")

            # Step 2: Find new IDs
            known = set(astate.get("known_ids", []))
            all_ids = [seed_id] + seed.get("sidebar_ids", [])
            new_ids = [aid for aid in all_ids if aid not in known]

            if not new_ids:
                log(f"  No new articles")
                continue

            log(f"  Checking {len(new_ids)} new article(s)...")

            # Step 3: Parallel fetch all new articles (just metadata)
            tasks = [fetch_article_meta(aid, client) for aid in new_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            latest_date = seed.get("date", "")
            latest_id = seed_id

            for r in results:
                if isinstance(r, Exception):
                    continue
                if r.get("error"):
                    known.add(r["id"])
                    continue

                aid = r["id"]
                adate = r.get("date", "")
                atitle = r.get("title", "")

                # Update latest
                if adate and adate >= latest_date:
                    latest_date = adate
                    latest_id = aid

                # If today's article found
                if adate == today:
                    key = (adate, author_name)
                    if key in existing_keys:
                        log(f"  Already exists: '{atitle[:30]}'")
                        known.add(aid)
                        continue

                    # Extract content and generate TTS
                    content = extract_content(r.get("html", ""))
                    if len(content) < 100:
                        log(f"  Content too short: '{atitle[:30]}' ({len(content)} chars)")
                        known.add(aid)
                        continue

                    safe_title = re.sub(r'[\\/:*?"<>|\s]', '_', atitle)[:30]
                    mp3_name = f"{today}_{author_name}_{safe_title}.mp3"
                    mp3_path = str(audio_dir / mp3_name)

                    tts_ok = await generate_tts(content, mp3_path, author_name, atitle)

                    article_entry = {
                        "date": adate,
                        "source": author_name,
                        "title": atitle,
                        "url": r.get("url", ""),
                        "audio": mp3_name if tts_ok else "",
                        "publish_time": r.get("publish_time", ""),
                        "created_at": datetime.now(CN_TZ).isoformat(),
                    }
                    new_articles.append(article_entry)
                    existing_keys.add(key)
                    log(f"  [NEW] '{atitle[:40]}' ({adate})")

                known.add(aid)

            # Step 4: Update state
            astate["known_ids"] = list(known)
            if latest_date:
                astate["latest_seed_id"] = latest_id
                log(f"  Updated seed: {latest_id[:8]}... ({latest_date})")

    # Save state
    save_json(state, state_file)

    # Save articles
    if new_articles:
        existing_articles.extend(new_articles)
        existing_articles.sort(key=lambda x: x.get("date", ""), reverse=True)
        log(f"\n=== Added {len(new_articles)} new article(s) ===")
    else:
        log(f"\n=== No new articles today ({len(existing_articles)} total) ===")

    save_json(existing_articles, articles_file)

    # Also output a summary for the workflow
    summary = {
        "date": today,
        "new_count": len(new_articles),
        "total_count": len(existing_articles),
        "new_articles": [{"source": a["source"], "title": a["title"], "audio": a["audio"]} for a in new_articles],
    }
    save_json(summary, str(output_dir / "wxredian_summary.json"))
    log(f"Output: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
