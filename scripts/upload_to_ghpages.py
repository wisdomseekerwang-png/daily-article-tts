"""Upload files to GitHub Pages (gh-pages branch) via API."""
import base64
import json
import os
import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed")
    sys.exit(1)

TOKEN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN", "")
REPO = "wisdomseekerwang-png/daily-article-tts"
BRANCH = "gh-pages"
BASE_URL = f"https://api.github.com/repos/{REPO}/contents"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dist")

def get_sha(path: str) -> str:
    """Get current file SHA on gh-pages."""
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{BASE_URL}/{path}", params={"ref": BRANCH}, headers=HEADERS)
            if r.status_code == 200:
                return r.json().get("sha", "")
    except Exception:
        pass
    return ""


def upload_file(path: str, content: bytes, message: str = None):
    """Upload or update a file on gh-pages."""
    b64 = base64.b64encode(content).decode()
    sha = get_sha(path)
    data = {
        "message": message or f"Update {path}",
        "content": b64,
        "branch": BRANCH,
    }
    if sha:
        data["sha"] = sha

    with httpx.Client(timeout=30) as client:
        if sha:
            r = client.put(f"{BASE_URL}/{path}", json=data, headers=HEADERS)
        else:
            r = client.post(f"{BASE_URL}/{path}", json=data, headers=HEADERS)

    if r.status_code in (200, 201):
        print(f"  OK   {path}")
    else:
        print(f"  FAIL {path}: {r.status_code} {r.text[:100]}")


def main():
    if not TOKEN:
        print("ERROR: No GitHub token provided")
        sys.exit(1)

    files = []

    # articles.json
    aj = os.path.join(DIST_DIR, "data", "articles.json")
    if os.path.exists(aj):
        with open(aj, "rb") as f:
            files.append(("data/articles.json", f.read()))

    # MP3 files
    audio_dir = os.path.join(DIST_DIR, "audio")
    if os.path.isdir(audio_dir):
        for fname in os.listdir(audio_dir):
            if fname.endswith(".mp3"):
                with open(os.path.join(audio_dir, fname), "rb") as f:
                    files.append((f"audio/{fname}", f.read()))

    # Web assets
    for asset in ["index.html", "css/style.css", "js/app.js"]:
        p = os.path.join(DIST_DIR, asset)
        if os.path.exists(p):
            with open(p, "rb") as f:
                files.append((asset, f.read()))

    print(f"Uploading {len(files)} files to gh-pages...")
    for path, content in files:
        upload_file(path, content)
    print("Done!")


if __name__ == "__main__":
    main()
