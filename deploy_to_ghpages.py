"""
deploy_to_ghpages.py - Deploy local TTS files to GitHub gh-pages branch.

Usage:
    python deploy_to_ghpages.py [--token GITHUB_PAT]

What it does:
    1. Clones gh-pages branch to a temp directory (or updates if exists)
    2. Copies articles.json from web/data/ to gh-pages/data/
    3. Copies new MP3 files from audio/ to gh-pages/audio/
    4. Commits and pushes to gh-pages
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/wisdomseekerwang-png/daily-article-tts.git"
PROJECT_DIR = Path(__file__).parent
TEMP_CLONE_DIR = PROJECT_DIR / ".gh-pages-deploy"
TOKEN_FILE = PROJECT_DIR / ".github_token"

# Source dirs (local)
LOCAL_DATA_DIR = PROJECT_DIR / "web" / "data"
LOCAL_AUDIO_DIR = PROJECT_DIR / "audio"

# Target dirs (gh-pages)
REMOTE_DATA_DIR = TEMP_CLONE_DIR / "data"
REMOTE_AUDIO_DIR = TEMP_CLONE_DIR / "audio"


def get_token(args_token: str | None) -> str | None:
    """Get GitHub token from args, env, or file."""
    if args_token:
        return args_token
    env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
    if env_token:
        return env_token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def make_auth_url(token: str | None) -> str:
    """Return repo URL with optional token auth."""
    if token:
        return f"https://wisdomseekerwang-png:{token}@github.com/wisdomseekerwang-png/daily-article-tts.git"
    return REPO_URL


def run_git(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Git error: {result.stderr.strip()}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Deploy TTS files to gh-pages")
    parser.add_argument("--token", default=None, help="GitHub PAT token")
    args = parser.parse_args()

    token = get_token(args.token)
    auth_url = make_auth_url(token)

    # Step 1: Clone or update gh-pages
    print(">>> Cloning/updating gh-pages branch...")
    if TEMP_CLONE_DIR.exists():
        # Update existing clone
        result = run_git(["git", "fetch", "origin", "gh-pages"], cwd=TEMP_CLONE_DIR)
        if result.returncode == 0:
            run_git(["git", "reset", "--hard", "origin/gh-pages"], cwd=TEMP_CLONE_DIR)
        else:
            # Branch might not exist yet, re-clone
            shutil.rmtree(TEMP_CLONE_DIR)
            TEMP_CLONE_DIR.mkdir(parents=True, exist_ok=True)
            run_git(["git", "clone", "--branch", "gh-pages", "--single-branch", auth_url, "."],
                    cwd=TEMP_CLONE_DIR)
    else:
        TEMP_CLONE_DIR.mkdir(parents=True, exist_ok=True)
        result = run_git(["git", "clone", "--branch", "gh-pages", "--single-branch", auth_url, "."],
                         cwd=TEMP_CLONE_DIR, check=False)
        if result.returncode != 0:
            print("gh-pages branch does not exist yet. Creating initial commit...")
            run_git(["git", "init"], cwd=TEMP_CLONE_DIR)
            run_git(["git", "checkout", "-b", "gh-pages"], cwd=TEMP_CLONE_DIR)
            run_git(["git", "remote", "add", "origin", auth_url], cwd=TEMP_CLONE_DIR)

    # Step 2: Copy articles.json
    local_articles = LOCAL_DATA_DIR / "articles.json"
    remote_articles = REMOTE_DATA_DIR / "articles.json"
    changes = False

    if local_articles.exists():
        REMOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_articles, remote_articles)
        run_git(["git", "add", "data/articles.json"], cwd=TEMP_CLONE_DIR)
        result = run_git(["git", "diff", "--cached", "--quiet"], cwd=TEMP_CLONE_DIR, check=False)
        if result.returncode != 0:
            changes = True
            print("  Updated: data/articles.json")
        else:
            run_git(["git", "reset", "HEAD", "data/articles.json"], cwd=TEMP_CLONE_DIR)
            print("  No changes: data/articles.json")
    else:
        print("  Skip: articles.json not found locally")

    # Step 3: Copy new MP3 files
    if LOCAL_AUDIO_DIR.exists():
        REMOTE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        existing_remote = set(f.name for f in REMOTE_AUDIO_DIR.glob("*.mp3"))
        new_files = 0
        for mp3 in LOCAL_AUDIO_DIR.glob("*.mp3"):
            if mp3.name not in existing_remote:
                shutil.copy2(mp3, REMOTE_AUDIO_DIR / mp3.name)
                run_git(["git", "add", f"audio/{mp3.name}"], cwd=TEMP_CLONE_DIR)
                new_files += 1
                changes = True
                print(f"  New audio: audio/{mp3.name}")
        if new_files == 0:
            print("  No new audio files")
    else:
        print("  Skip: no local audio/ directory")

    # Step 4: Commit and push
    if not changes:
        print(">>> No changes to deploy.")
        return

    # Configure git user if needed
    run_git(["git", "config", "user.email", "wisdomseekerwang-png@users.noreply.github.com"],
            cwd=TEMP_CLONE_DIR)
    run_git(["git", "config", "user.name", "wisdomseekerwang-png"], cwd=TEMP_CLONE_DIR)

    # Commit
    run_git(["git", "commit", "-m", "deploy: update articles and audio from WorkBuddy automation"],
            cwd=TEMP_CLONE_DIR, check=False)

    # Push
    push_url = auth_url if token else REPO_URL
    print(">>> Pushing to gh-pages...")
    result = run_git(["git", "push", push_url, "gh-pages"], cwd=TEMP_CLONE_DIR, check=False)
    if result.returncode == 0:
        print(">>> Deployed successfully!")
    else:
        print(f">>> Push failed: {result.stderr.strip()}")
        print(">>> Files are committed locally. Push manually if needed.")


if __name__ == "__main__":
    main()
