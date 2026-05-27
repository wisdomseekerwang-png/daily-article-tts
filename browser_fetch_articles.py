"""
Browser-based WeChat article fetcher for TTS automation.

Uses agent-browser (real Chromium) to bypass sogou anti-spider blocking.
Searches sogou for article URLs, then navigates with browser to handle
JavaScript redirects and extract article content from rendered pages.

Usage:
  python browser_fetch_articles.py              # All 4 accounts
  python browser_fetch_articles.py --test       # Quick test on 1 account
  python browser_fetch_articles.py --account "孥孥的大树"  # Specific account
"""

import asyncio
import edge_tts
import httpx
import re
import os
import sys
import json
import subprocess
import time
import argparse
from datetime import datetime

# ============== Configuration ==============
VOICE = "zh-CN-XiaoxiaoNeural"
VOICE_RATE = "+10%"
VOICE_PITCH = "+0Hz"

# Local paths
WORKSPACE_DIR = r"C:\Users\yuhaoxiong\WorkBuddy\2026-05-19-task-2"
AUDIO_DIR = os.path.join(WORKSPACE_DIR, "audio")
LOG_FILE = os.path.join(WORKSPACE_DIR, "browser_tts_log.txt")
NOTIFICATION_FILE = os.path.join(WORKSPACE_DIR, "daily_article_notification.md")
ARTICLES_JSON = os.path.join(WORKSPACE_DIR, "web", "data", "articles.json")

# Full path to agent-browser (installed via npm global)
AGENT_BROWSER_CMD = r"C:\Users\yuhaoxiong\.workbuddy\binaries\node\versions\22.22.2\agent-browser.cmd"

# Accounts that need browser automation (sogou anti-spider blocks httpx)
BROWSER_ACCOUNTS = [
    {"name": "孥孥的大树", "search_query": "孥孥的大树"},
    {"name": "卢克文工作室", "search_query": "卢克文工作室"},
    {"name": "海里的小龙龙", "search_query": "海里的小龙龙"},
    {"name": "远方青木", "search_query": "远方青木"},
]

# Browser settings
BROWSER_TIMEOUT = 30  # seconds per operation
PAGE_LOAD_WAIT = 3    # seconds to wait after navigation


def log(msg):
    """Log to both stdout and log file"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run_browser_cmd(args, timeout=BROWSER_TIMEOUT):
    """Run an agent-browser command and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            [AGENT_BROWSER_CMD] + args,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            shell=True  # Required on Windows for .cmd files
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log(f"[WARN] Browser command timed out: agent-browser {' '.join(args)}")
        return -1, "", "timeout"
    except FileNotFoundError:
        log(f"[ERROR] agent-browser not found at: {AGENT_BROWSER_CMD}")
        return -1, "", "not found"
    except Exception as e:
        log(f"[ERROR] Browser command failed: {e}")
        return -1, "", str(e)


def browser_open(url):
    """Open URL in browser, return True on success"""
    rc, out, err = run_browser_cmd(["open", url], timeout=30)
    if rc != 0:
        log(f"[WARN] Browser open failed: {err[:200]}")
        return False
    return True


def browser_wait():
    """Wait for page to load"""
    # Try networkidle first, fallback to load event
    rc, out, err = run_browser_cmd(["wait", "--load", "networkidle"], timeout=20)
    if rc != 0:
        run_browser_cmd(["wait", "--load", "load"], timeout=15)
    # Extra wait for dynamic content
    time.sleep(PAGE_LOAD_WAIT)


def browser_snapshot():
    """Get page content as text"""
    rc, out, err = run_browser_cmd(["snapshot"], timeout=30)
    return out if rc == 0 else ""


def browser_close():
    """Close browser daemon"""
    run_browser_cmd(["close"], timeout=10)


async def search_sogou(name: str, query: str) -> dict:
    """Search sogou WeChat for latest article URL (same logic as main script)"""
    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        ) as client:
            resp = await client.get("https://weixin.sogou.com/weixin",
                params={"type": "2", "query": query, "ie": "utf8"})
            html = resp.text

            if len(html) < 5000:
                log(f"[WARN] {name}: Sogou returned tiny page ({len(html)} chars), possibly blocked")
                return {}

            articles = []
            items = re.findall(
                r'<div[^>]*class="[^"]*txt-box[^"]*"[^>]*>(.*?)</div>\s*<!--\s*\.txt-box',
                html, re.DOTALL
            )
            if not items:
                news_section = re.search(
                    r'<ul[^>]*class="[^"]*news-list[^"]*"[^>]*>(.*?)</ul>',
                    html, re.DOTALL
                )
                if news_section:
                    items = re.findall(r'<li[^>]*>(.*?)</li>', news_section.group(1), re.DOTALL)

            for item in items:
                title_m = re.search(
                    r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h3>',
                    item, re.DOTALL
                )
                if not title_m:
                    continue
                url = title_m.group(1)
                title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()

                src = ""
                src_m = re.search(
                    r'(?:class="[^"]*(?:all-time-y2|account)[^"]*"[^>]*>|'
                    r'<a[^>]+class="[^"]*account[^"]*"[^>]*>)([^<]+)',
                    item
                )
                if src_m:
                    src = src_m.group(1).strip()

                ts_m = re.search(r'script.*?(\d{10})', item)
                date_info = ""
                if ts_m:
                    ts = int(ts_m.group(1))
                    days_ago = (int(time.time()) - ts) // 86400
                    date_info = f"{days_ago}d"

                articles.append({
                    "title": title, "url": url,
                    "source": src, "date_info": date_info
                })

            if articles:
                # Filter by source name match
                matched = [
                    a for a in articles
                    if any(kw in a["source"] for kw in [name, name[:2]])
                ]
                if matched:
                    matched.sort(
                        key=lambda x: (
                            int(re.search(r'(\d+)', x["date_info"]).group(1))
                            if re.search(r'(\d+)', x["date_info"]) else 9999
                        )
                    )
                    best = matched[0]
                    url = best["url"]
                    if url.startswith("/"):
                        url = "https://weixin.sogou.com" + url
                    log(f"[INFO] {name}: Found article \"{best['title'][:30]}\" ({best.get('date_info', '')})")
                    return {"title": best["title"], "url": url, "source": best["source"]}
                else:
                    log(f"[WARN] {name}: Found {len(articles)} articles but none matched source")
    except Exception as e:
        log(f"[WARN] {name}: Sogou search error - {e}")

    return {}


def extract_article_from_snapshot(snapshot_text: str, account_name: str) -> str:
    """Extract article body text from agent-browser snapshot output.

    The snapshot contains full page text. We need to filter out:
    - Navigation elements, menus, buttons
    - Footer content
    - Author/date metadata (keep some)
    - UI chrome (Share, Like, etc.)
    """
    if not snapshot_text:
        return ""

    lines = snapshot_text.split('\n')
    article_lines = []
    in_article = False
    article_started = False

    # Heuristic: article content starts after the title and before footer/UI elements
    skip_patterns = [
        r'^(微信|WeChat|公众号|扫码|关注|分享|收藏|赞|在看|Read more)',
        r'^\s*$',  # empty lines at start
        r'^(你正在|此内容为|来源|原文链接|阅读原文)',
        r'^(举报|投诉|删除|编辑|设为)',
        r'^\d+$',  # standalone numbers
        r'^(搜狗|Sogou|baidu|百度)',
        r'^\s*[\W_]+\s*$',  # standalone symbols
    ]

    # Keep lines that are likely article body content
    keep_pattern = re.compile(r'[\u4e00-\u9fff]')  # contains Chinese chars

    for line in lines:
        line = line.strip()
        if not line:
            if article_started:
                article_lines.append("")  # preserve paragraph breaks
            continue

        # Skip navigation/UI elements
        skip = False
        for pat in skip_patterns:
            if re.match(pat, line):
                skip = True
                break
        if skip:
            continue

        # Skip very short lines that are likely UI elements
        if len(line) < 3:
            continue

        # Lines with Chinese text are likely article content
        if keep_pattern.search(line) and len(line) > 5:
            article_started = True
            article_lines.append(line)

    text = '\n'.join(article_lines)

    # Clean up
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def clean_for_tts(text: str) -> str:
    """Clean article text for TTS output"""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'点击蓝字.*', '', text)
    text = re.sub(r'来源[:：].*', '', text)
    text = re.sub(r'作者[:：].*', '', text)
    text = re.sub(r'关注.*公众号.*', '', text)
    text = re.sub(r'分享.*收藏.*赞.*', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\.{3,}', '……', text)
    text = re.sub(r'\n{2,}', '\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def truncate_for_tts(text: str, max_chars: int = 3500) -> str:
    """Truncate text at a sentence boundary"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_punct = max(truncated.rfind('。'), truncated.rfind('！'), truncated.rfind('？'))
    if last_punct > max_chars * 0.6:
        return truncated[:last_punct + 1]
    return truncated + "……"


async def text_to_speech(text: str, output_path: str, source_name: str, article_title: str) -> bool:
    """Convert text to MP3 via edge_tts"""
    if not text or len(text) < 50:
        log(f"[WARN] {source_name}: Content too short ({len(text)} chars), skipping TTS")
        return False

    text = truncate_for_tts(text)

    try:
        communicate = edge_tts.Communicate(
            text, voice=VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH,
        )
        await communicate.save(output_path)
        file_size = os.path.getsize(output_path)
        duration_sec = int(file_size * 8 / (128 * 1024))
        log(f"[OK] {source_name} \"{article_title[:30]}\": {os.path.basename(output_path)} ({file_size//1024}KB, ~{duration_sec}s)")
        return True
    except Exception as e:
        log(f"[ERROR] TTS failed for {source_name}: {e}")
        return False


async def process_browser_source(source: dict, test_mode: bool = False) -> dict:
    """Process a single source using browser automation"""
    name = source["name"]
    log(f"[INFO] === {name} (Browser Mode) ===")

    # Step 1: Search sogou for article URL (httpx works for search)
    article_info = await search_sogou(name, source["search_query"])
    if not article_info or not article_info.get("url"):
        log(f"[WARN] {name}: No article found via sogou search")
        return {"name": name, "success": False, "reason": "Sogou search found no article"}

    article_url = article_info["url"]
    article_title = article_info["title"]
    log(f"[INFO] {name}: Article: \"{article_title[:40]}\"")
    log(f"[INFO] {name}: URL: {article_url}")

    # Step 2: Fetch content via browser
    log(f"[INFO] {name}: Opening browser...")

    if not browser_open(article_url):
        return {"name": name, "success": False, "reason": "Failed to open browser"}

    browser_wait()
    time.sleep(2)  # Extra wait for WeChat page rendering

    snapshot_text = browser_snapshot()
    if not snapshot_text or len(snapshot_text) < 200:
        log(f"[WARN] {name}: Snapshot too short ({len(snapshot_text)} chars)")
        if test_mode:
            browser_close()
        return {"name": name, "success": False, "reason": "Browser snapshot empty"}

    log(f"[INFO] {name}: Snapshot captured ({len(snapshot_text)} chars)")

    # Save raw snapshot for debugging
    try:
        debug_dir = os.path.join(WORKSPACE_DIR, "debug_snapshots")
        os.makedirs(debug_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|]', '', name)
        debug_file = os.path.join(debug_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.txt")
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(f"URL: {article_url}\n\n")
            f.write(snapshot_text)
        log(f"[DEBUG] Snapshot saved: {debug_file}")
    except Exception:
        pass

    # Step 3: Extract article content from snapshot
    article_text = extract_article_from_snapshot(snapshot_text, name)
    article_text = clean_for_tts(article_text)

    if not article_text or len(article_text) < 100:
        log(f"[WARN] {name}: Extracted text too short ({len(article_text)} chars)")
        if test_mode:
            browser_close()
        return {"name": name, "success": False, "reason": "Article content extraction failed"}

    log(f"[INFO] {name}: Article content: {len(article_text)} chars")

    if test_mode:
        log(f"[TEST] {name}: Content preview: {article_text[:200]}...")
        browser_close()
        return {"name": name, "success": True, "title": article_title,
                "url": article_url, "content_len": len(article_text)}

    # Step 4: Generate TTS MP3
    today = datetime.now().strftime("%Y%m%d")
    safe_title = re.sub(r'[\\/:*?"<>|]', '', article_title)[:25]
    filename = f"{today}_{name}_{safe_title}.mp3"
    output_path = os.path.join(AUDIO_DIR, filename)

    success = await text_to_speech(article_text, output_path, name, article_title)

    # Copy to workspace
    if success:
        try:
            workspace_dest = os.path.join(WORKSPACE_DIR, filename)
            import shutil
            shutil.copy2(output_path, workspace_dest)
            log(f"[INFO] {name}: Copied to workspace: {filename}")
        except Exception as e:
            log(f"[WARN] Copy to workspace failed: {e}")

    return {
        "name": name,
        "title": article_title,
        "url": article_url,
        "mp3_path": output_path if success else None,
        "success": success,
    }


def save_articles_json(results: list):
    """Save article metadata to articles.json (merge with existing)"""
    try:
        os.makedirs(os.path.dirname(ARTICLES_JSON), exist_ok=True)

        existing = []
        if os.path.exists(ARTICLES_JSON):
            with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)

        existing_keys = {(a["date"], a["source"]) for a in existing}

        for r in results:
            if not r.get("success"):
                continue
            key = (datetime.now().strftime("%Y-%m-%d"), r["name"])
            if key in existing_keys:
                continue

            article = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source": r["name"],
                "title": r["title"],
                "url": r["url"],
                "audio": os.path.basename(r["mp3_path"]) if r.get("mp3_path") else "",
                "created_at": datetime.now().isoformat(),
            }
            existing.append(article)

        existing.sort(key=lambda x: x["date"], reverse=True)

        with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        log(f"[OK] articles.json updated ({len(existing)} total records)")
    except Exception as e:
        log(f"[WARN] Failed to update articles.json: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Browser-based WeChat article TTS")
    parser.add_argument("--test", action="store_true", help="Test mode: fetch content but skip TTS")
    parser.add_argument("--account", type=str, default="", help="Process specific account only")
    args = parser.parse_args()

    # Select accounts to process
    if args.account:
        accounts = [a for a in BROWSER_ACCOUNTS if args.account in a["name"]]
        if not accounts:
            log(f"[ERROR] Account \"{args.account}\" not found in {BROWSER_ACCOUNTS}")
            return
    else:
        accounts = BROWSER_ACCOUNTS

    os.makedirs(AUDIO_DIR, exist_ok=True)
    log("=" * 60)
    mode_str = "TEST" if args.test else "PRODUCTION"
    log(f"Browser Article TTS [{mode_str}] — {len(accounts)} account(s)")

    results = []
    try:
        for source in accounts:
            result = await process_browser_source(source, test_mode=args.test)
            results.append(result)
            if not args.test:
                await asyncio.sleep(3)  # Brief pause between accounts
    finally:
        browser_close()

    # Summary
    success_count = sum(1 for r in results if r.get("success"))
    log(f"[SUMMARY] {success_count}/{len(results)} succeeded")
    for r in results:
        status = "OK" if r.get("success") else "FAIL"
        detail = r.get("title", r.get("reason", ""))
        log(f"  [{status}] {r['name']}: {detail[:50]}")

    # Save metadata (skip in test mode)
    if not args.test and success_count > 0:
        save_articles_json(results)

    log("=" * 60)

    # Print results as JSON for automation consumption
    print("\n__RESULTS__")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
