"""Shared JSON formatting so every writer (migration, issue generator) produces identical diffs."""
import json


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps(obj))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
