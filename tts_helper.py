"""
TTS Helper - 供 WorkBuddy 自动化调用的辅助脚本
接收文章内容文件，生成 TTS MP3 并更新 web 播放器数据

使用方法:
  python tts_helper.py --content-file content.txt --title "文章标题" --source "公众号名"
  python tts_helper.py --content "直接传入的文章内容" --title "标题" --source "来源"
  python tts_helper.py --check-source "公众号名"  # 检查今天是否已有该来源的文章
"""

import asyncio
import edge_tts
import os
import sys
import json
import re
import argparse
from datetime import datetime

# ============== 配置区 ==============
WORKSPACE_DIR = r"C:\Users\yuhaoxiong\WorkBuddy\2026-05-19-task-2"
AUDIO_DIR = os.path.join(WORKSPACE_DIR, "audio")
ARTICLES_JSON = os.path.join(WORKSPACE_DIR, "web", "data", "articles.json")
LOG_FILE = os.path.join(WORKSPACE_DIR, "tts_helper_log.txt")

VOICE = "zh-CN-XiaoxiaoNeural"
VOICE_RATE = "+10%"
VOICE_PITCH = "+0Hz"
MAX_TTS_CHARS = 3500


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def clean_text(text):
    """Clean article text for TTS"""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\[.*?\]', '', text)
    # Remove common WeChat boilerplate
    for kw in ['点击蓝字', '来源', '作者', '关注', '分享', '请在', '阅读原文',
                '公众号', '微信', '扫码', '二维码', '转载', '声明', '版权归原作者',
                '如有侵权', '请联系', '删除', '责任编辑', '审核', '监制']:
        if f'{kw}' in text:
            text = re.sub(f'{kw}[^。！？]*[。！？]?', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\.{3,}', '...', text)
    return text.strip()


def truncate_text(text, max_chars=MAX_TTS_CHARS):
    """Truncate text for TTS length limit"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_punct = max(truncated.rfind('\u3002'), truncated.rfind('\uff01'), truncated.rfind('\uff1f'))
    if last_punct > max_chars * 0.6:
        return truncated[:last_punct + 1]
    return truncated + "..."


def check_source_today(source_name):
    """Check if an article from this source already exists for today"""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if os.path.exists(ARTICLES_JSON):
            with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
                articles = json.load(f)
            for a in articles:
                if a.get("source") == source_name and a.get("date") == today:
                    log(f"[SKIP] {source_name} today already has article: {a.get('title', '')[:30]}")
                    return True, a
    except Exception as e:
        log(f"[WARN] Check failed: {e}")
    return False, None


def save_article_to_json(title, source, url, mp3_filename, article_date=None, publish_time=None):
    """Append article entry to articles.json"""
    try:
        os.makedirs(os.path.dirname(ARTICLES_JSON), exist_ok=True)

        existing = []
        if os.path.exists(ARTICLES_JSON):
            with open(ARTICLES_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)

        # Dedup by (date, source)
        today = article_date or datetime.now().strftime("%Y-%m-%d")
        existing_keys = {(a.get("date", ""), a.get("source", "")) for a in existing}
        key = (today, source)

        if key in existing_keys:
            log(f"[SKIP] {source} @ {today} already in articles.json")
            return False

        article = {
            "date": today,
            "source": source,
            "title": title,
            "url": url,
            "audio": mp3_filename,
            "created_at": datetime.now().isoformat(),
        }
        if publish_time:
            article["publish_time"] = publish_time
        existing.append(article)
        existing.sort(key=lambda x: x.get("date", ""), reverse=True)

        with open(ARTICLES_JSON, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        log(f"[OK] articles.json updated: {source} - {title[:30]}")
        return True
    except Exception as e:
        log(f"[ERROR] Failed to update articles.json: {e}")
        return False


async def generate_tts(text, title, source):
    """Generate TTS MP3 and save to audio directory"""
    text = clean_text(text)
    text = truncate_text(text)

    if len(text) < 50:
        log(f"[WARN] Text too short ({len(text)} chars), skipping TTS")
        return None

    os.makedirs(AUDIO_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:25]
    filename = f"{today}_{source}_{safe_title}.mp3"
    output_path = os.path.join(AUDIO_DIR, filename)

    try:
        communicate = edge_tts.Communicate(
            text, voice=VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH
        )
        await communicate.save(output_path)
        file_size = os.path.getsize(output_path)
        duration_sec = int(file_size * 8 / (128 * 1024))
        log(f"[OK] TTS generated: {filename} ({file_size // 1024}KB, ~{duration_sec}s)")
        return filename
    except Exception as e:
        log(f"[ERROR] TTS failed: {e}")
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="TTS Helper for WorkBuddy automation")
    parser.add_argument("--content-file", type=str, help="Path to file containing article text")
    parser.add_argument("--content", type=str, help="Article text directly (use for short content)")
    parser.add_argument("--title", type=str, default="", help="Article title")
    parser.add_argument("--source", type=str, default="", help="Source name (e.g. 卢克文工作室)")
    parser.add_argument("--url", type=str, default="", help="Article URL")
    parser.add_argument("--date", type=str, default="", help="Article date (YYYY-MM-DD)")
    parser.add_argument("--publish-time", type=str, default="", help="Article publish time (YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--check-source", type=str, help="Check if source already has today's article")
    return parser.parse_args()


async def main():
    args = parse_args()

    # Check mode: just check if today's article exists (don't require title/source)
    if args.check_source:
        exists, article = check_source_today(args.check_source)
        if exists:
            print(f"EXISTS: {article.get('title', '')}")
            print(f"AUDIO: {article.get('audio', '')}")
        else:
            print("NOT_FOUND")
        return

    # Require content and title for generation mode
    if not args.title or not args.source:
        log("[ERROR] --title and --source are required")
        return

    # Check mode: just check if today's article exists
    if args.check_source:
        exists, article = check_source_today(args.check_source)
        if exists:
            print(f"EXISTS: {article.get('title', '')}")
            print(f"AUDIO: {article.get('audio', '')}")
        else:
            print("NOT_FOUND")
        return

    # Read content
    text = ""
    if args.content_file:
        try:
            with open(args.content_file, "r", encoding="utf-8") as f:
                text = f.read()
            log(f"[INFO] Read {len(text)} chars from {args.content_file}")
        except Exception as e:
            log(f"[ERROR] Failed to read content file: {e}")
            return
    elif args.content:
        text = args.content
        log(f"[INFO] Using inline content: {len(text)} chars")
    else:
        log("[ERROR] No content provided. Use --content-file or --content")
        return

    # Check for duplicates
    exists, _ = check_source_today(args.source)
    if exists:
        log(f"[SKIP] {args.source} already processed today")
        return

    # Generate TTS
    mp3_filename = await generate_tts(text, args.title, args.source)
    if not mp3_filename:
        log(f"[FAIL] TTS generation failed for {args.source}")
        return

    # Update articles.json
    save_article_to_json(args.title, args.source, args.url or "", mp3_filename, args.date or None, args.publish_time or None)
    log(f"[DONE] {args.source} processing complete")


if __name__ == "__main__":
    asyncio.run(main())
