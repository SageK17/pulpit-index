#!/usr/bin/env python3
"""Collect chunk ids whose four translations passed an independent review (from workflow journals) into
data/translations/reviewed.json. The build only shows a sermon's translations when all its chunks are listed."""
import json, glob, os, sys
base = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/.claude/projects/-Users-sageacheampong-innovative-projects/607fbc2d-a1e0-40df-8536-eb68121c68ab/subagents/workflows")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "translations", "reviewed.json")
ok = set()
for j in glob.glob(os.path.join(base, "*", "journal.jsonl")):
    lab, st = {}, {}
    for line in open(j):
        x = json.loads(line)
        if x.get("type") == "started":
            lab[x["key"]] = x.get("label", "")
            kind, _, cid = x.get("label", "").partition(":")
            if kind in ("en", "nl", "review"):
                st.setdefault(cid, {}).setdefault(kind, False)
        elif x.get("type") == "result":
            kind, _, cid = lab.get(x.get("key"), "").partition(":")
            if kind in ("en", "nl", "review"):
                r = x["result"]; r = json.loads(r) if isinstance(r, str) else r
                st.setdefault(cid, {})[kind] = bool(r and r.get("ok"))
    for cid, k in st.items():
        # independent review: the translators both finished, or this was a review-only pass over existing files
        if k.get("review") and (("en" not in k and "nl" not in k) or (k.get("en") and k.get("nl"))):
            ok.add(cid)
json.dump(sorted(ok), open(out, "w"), indent=0)
print(len(ok), "independently reviewed chunks")
