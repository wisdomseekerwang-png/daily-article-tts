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

    # Merge: deduplicate by (date, source)
    existing_keys = {(a["date"], a["source"]) for a in existing}
    added = 0
    for a in new_articles:
        key = (a["date"], a["source"])
        if key not in existing_keys:
            existing.append(a)
            existing_keys.add(key)
            added += 1

    # Sort by date descending
    existing.sort(key=lambda x: x["date"], reverse=True)

    print(f"Articles: {len(existing)} total, {added} new")

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
