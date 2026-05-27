"""
早报电台 - 构建脚本
扫描 MP3 文件，生成 articles.json，复制到 dist/ 目录
"""

import os
import re
import json
import shutil
from datetime import datetime

# ============== 配置 ==============
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_SOURCE_DIR = r"C:\Users\yuhaoxiong\WorkBuddy\articles_tts"
WEB_DIR = os.path.join(PROJECT_DIR, "web")
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
ARTICLES_JSON_SRC = os.path.join(WEB_DIR, "data", "articles.json")
ARTICLES_JSON_DST = os.path.join(DIST_DIR, "data", "articles.json")


def parse_mp3_filename(filename: str) -> dict:
    """从 MP3 文件名解析元数据
    格式: 20260519_猫笔刀_一个潜在的雷.mp3
    """
    base = filename.replace('.mp3', '')
    parts = base.split('_', 2)
    if len(parts) < 3:
        return None

    date_str = parts[0]  # 20260519
    source = parts[1]    # 猫笔刀
    title = parts[2]     # 一个潜在的雷

    try:
        date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        datetime.strptime(date_formatted, "%Y-%m-%d")
    except ValueError:
        return None

    return {
        "date": date_formatted,
        "source": source,
        "title": title,
        "audio": filename,
    }


def scan_mp3_files():
    """扫描 articles_tts 目录中的所有 MP3"""
    articles = []

    # 先读取已有的 articles.json（保留 URL 等额外信息）
    existing = {}
    if os.path.exists(ARTICLES_JSON_SRC):
        try:
            with open(ARTICLES_JSON_SRC, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for a in existing_data:
                    key = f"{a['date']}_{a['source']}"
                    existing[key] = a
        except Exception:
            pass

    # 扫描 MP3
    if not os.path.exists(AUDIO_SOURCE_DIR):
        print(f"[WARN] 音频目录不存在: {AUDIO_SOURCE_DIR}")
        return articles

    for filename in os.listdir(AUDIO_SOURCE_DIR):
        if not filename.endswith('.mp3'):
            continue

        parsed = parse_mp3_filename(filename)
        if not parsed:
            continue

        key = f"{parsed['date']}_{parsed['source']}"
        # 合并已有信息（如 URL）
        if key in existing:
            article = existing[key]
            article["audio"] = filename
        else:
            article = parsed

        articles.append(article)

    # 去重并按日期倒序
    seen = set()
    unique = []
    for a in articles:
        key = f"{a['date']}_{a['source']}"
        if key not in seen:
            seen.add(key)
            unique.append(a)

    unique.sort(key=lambda x: x["date"], reverse=True)
    return unique


def build():
    """执行构建"""
    print("=" * 50)
    print("早报电台 - 构建开始")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 扫描 MP3
    print("\n[1/3] 扫描 MP3 文件...")
    articles = scan_mp3_files()
    print(f"  找到 {len(articles)} 篇文章")

    if not articles:
        print("[WARN] 没有找到文章，构建中断")
        return

    for a in articles[:5]:
        print(f"  {a['date']} {a['source']}《{a['title']}》")
    if len(articles) > 5:
        print(f"  ... 还有 {len(articles) - 5} 篇")

    # 2. 生成 articles.json
    print("\n[2/3] 生成 articles.json...")
    os.makedirs(os.path.join(DIST_DIR, "data"), exist_ok=True)
    with open(ARTICLES_JSON_DST, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"  -> {ARTICLES_JSON_DST}")

    # 3. 复制静态文件
    print("\n[3/3] 复制文件到 dist/...")

    # 复制 HTML
    for name in ["index.html"]:
        src = os.path.join(WEB_DIR, name)
        dst = os.path.join(DIST_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  -> {name}")

    # 复制 CSS
    os.makedirs(os.path.join(DIST_DIR, "css"), exist_ok=True)
    for name in os.listdir(os.path.join(WEB_DIR, "css")):
        src = os.path.join(WEB_DIR, "css", name)
        dst = os.path.join(DIST_DIR, "css", name)
        shutil.copy2(src, dst)
        print(f"  -> css/{name}")

    # 复制 JS
    os.makedirs(os.path.join(DIST_DIR, "js"), exist_ok=True)
    for name in os.listdir(os.path.join(WEB_DIR, "js")):
        src = os.path.join(WEB_DIR, "js", name)
        dst = os.path.join(DIST_DIR, "js", name)
        shutil.copy2(src, dst)
        print(f"  -> js/{name}")

    # 复制 MP3 到 dist/audio/
    os.makedirs(os.path.join(DIST_DIR, "audio"), exist_ok=True)
    mp3_count = 0
    for a in articles:
        src = os.path.join(AUDIO_SOURCE_DIR, a["audio"])
        dst = os.path.join(DIST_DIR, "audio", a["audio"])
        if os.path.exists(src):
            shutil.copy2(src, dst)
            mp3_count += 1
    print(f"  -> audio/ ({mp3_count} 个 MP3)")

    total_size = 0
    for root, dirs, files in os.walk(DIST_DIR):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))

    print(f"\n构建完成! dist/ 大小: {total_size // 1024}KB")
    print("=" * 50)


if __name__ == "__main__":
    build()
