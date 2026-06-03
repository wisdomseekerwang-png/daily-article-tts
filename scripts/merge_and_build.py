"""Merge new articles with existing gh-pages data and build dist/."""
import json
import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DIST_DIR = os.path.join(BASE_DIR, "dist")


def main():
    os.makedirs(os.path.join(DIST_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "audio"), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "css"), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "js"), exist_ok=True)

    existing_path = os.path.join(OUTPUT_DIR, "data", "articles.json")
    new_path = os.path.join(OUTPUT_DIR, "articles.json")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    dist_audio = os.path.join(DIST_DIR, "audio")

    # Load existing articles from gh-pages
    existing = []
    if os.path.exists(existing_path):
        try:
            with open(existing_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    # Load new articles from fetch script
    new_articles = []
    if os.path.exists(new_path):
        try:
            with open(new_path, "r", encoding="utf-8") as f:
                new_articles = json.load(f)
        except Exception:
            pass

    # Merge: 3-level dedup
    existing_keys = {(a["date"], a["source"]) for a in existing}
    existing_urls = {a.get("url", "") for a in existing if a.get("url")}
    existing_titles = {(a["source"], a["title"]) for a in existing}
    added = 0
    skipped = 0
    for a in new_articles:
        key = (a["date"], a["source"])
        title_key = (a["source"], a["title"])
        url = a.get("url", "")
        if key in existing_keys:
            skipped += 1
            continue
        if url and url in existing_urls:
            skipped += 1
            continue
        if title_key in existing_titles:
            skipped += 1
            continue
        existing.append(a)
        existing_keys.add(key)
        if url:
            existing_urls.add(url)
        existing_titles.add(title_key)
        added += 1

    # Sort by date descending
    existing.sort(key=lambda x: x["date"], reverse=True)

    print(f"Articles: {len(existing)} total, {added} new, {skipped} skipped (dedup)")

    # Write merged articles.json
    merged_path = os.path.join(DIST_DIR, "data", "articles.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # Copy MP3 files to dist
    if os.path.isdir(audio_dir):
        count = 0
        for fname in os.listdir(audio_dir):
            if fname.endswith(".mp3"):
                src = os.path.join(audio_dir, fname)
                dst = os.path.join(dist_audio, fname)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    count += 1
        print(f"Audio: {count} new files copied")

    # Copy web assets
    web_dir = os.path.join(BASE_DIR, "web")
    shutil.copy2(os.path.join(web_dir, "index.html"), os.path.join(DIST_DIR, "index.html"))
    shutil.copy2(os.path.join(web_dir, "css", "style.css"), os.path.join(DIST_DIR, "css", "style.css"))
    shutil.copy2(os.path.join(web_dir, "js", "app.js"), os.path.join(DIST_DIR, "js", "app.js"))

    print("Build complete!")


if __name__ == "__main__":
    main()
