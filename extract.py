#!/usr/bin/env python3
"""Copy fact-checked agent results out of a workflow journal into data/.

  python3 extract.py <path/to/journal.jsonl> [<journal2> ...]

Label prefix -> destination:
  verify:<preacher>          data/verified/<preacher>.json
  gap-verify:<subject>       data/verified/gap-<subject>.json
  life-verify:<preacher>     data/life/<preacher>.json
  lifectx-verify:<group>     data/lifectx/<preacher>.json   (split by preacher_id)
"""
import json
import os
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def save(sub, name, obj):
    d = os.path.join(DATA, sub)
    os.makedirs(d, exist_ok=True)
    json.dump(obj, open(os.path.join(d, name + ".json"), "w"), ensure_ascii=False, indent=1)


for journal in sys.argv[1:]:
    labels = {}
    for line in open(journal):
        x = json.loads(line)
        if x.get("type") == "started":
            labels[x["key"]] = x.get("label", "")
            continue
        if x.get("type") != "result":
            continue
        label = labels.get(x.get("key"), "")
        r = x.get("result")
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except Exception:
                continue
        if not isinstance(r, dict):
            print("skip (no object):", label)
            continue
        kind, _, name = label.partition(":")
        if kind == "verify":
            save("verified", name, r)
            print(f"verified/{name}: {len(r['sermons'])} kept, {len(r.get('removed', []))} removed, {len(r.get('corrections', []))} corrections")
        elif kind == "gap-verify":
            save("verified", "gap-" + name, r)
            print(f"verified/gap-{name}: {len(r['sermons'])} kept, {len(r.get('removed', []))} removed")
        elif kind == "life-verify":
            save("life", name, r)
            print(f"life/{name}: {len(r['phases'])} phases, {len(r['events'])} events, {len(r.get('corrections', []))} corrections")
        elif kind == "audio":
            save("audio", name, r)
            print(f"audio/{name}: {sum(1 for x in r.get('rows', []) if x.get('listen_url'))} of {len(r.get('rows', []))} with recordings")
        elif kind == "lifectx-verify":
            by = {}
            for s in r.get("sermons", []):
                by.setdefault(s.get("preacher_id"), []).append(s)
            for pid, items in by.items():
                save("lifectx", pid, {"sermons": items})
                print(f"lifectx/{pid}: {len(items)} sermons")
