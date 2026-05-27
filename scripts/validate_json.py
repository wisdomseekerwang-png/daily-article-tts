"""Validate a JSON file, replace with [] if invalid."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "articles.json"
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected array")
    print(f"Valid JSON: {len(data)} records")
except Exception:
    print(f"Invalid JSON, resetting to []")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([], f)
