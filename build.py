#!/usr/bin/env python3
"""Merge verified research into one dataset and bake it into the site.

Inputs (all optional except verified/):
  data/verified/<preacher>.json   sermons + profile (fact-checked)
  data/verified/gap-<cat>.json    extra sermons for thin subjects (fact-checked)
  data/life/<preacher>.json       life timeline: born, died, phases, events (fact-checked)
  data/lifectx/<preacher>.json    per-sermon life stage + life context
  data/texts/<sermon-id>.json     public-domain full texts {edition, source_label, source_url, chapters:[{title, blocks:[{t,x}]}]}

Outputs:
  data/sermons.json               merged dataset
  dist/index.html                 standalone page (texts inlined; opens from disk)
  dist/index.artifact.html        body for the Artifact publisher (texts fetched from texts/)
  dist/texts/<sermon-id>.json     copies of the texts for the artifact

Usage:
  python3 build.py
  python3 build.py --src data/sample --out dist/preview.html
"""
import argparse
import datetime
import difflib
import glob
import json
import os
import re
import shutil
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

GROUPS = [
    ("heart", "Matters of the heart"),
    ("way", "The way of salvation"),
    ("hard", "Hard seasons"),
    ("last", "Last things"),
    ("god", "God and Christ"),
    ("world", "Church and world"),
]

CATEGORIES = [
    ("love", "Love", "heart", "God's love, love for God and for one's neighbour, and Christian charity."),
    ("friendship", "Friendship", "heart", "Friendship between people and friendship with God: companionship, loyalty and fellowship."),
    ("hatred-enemies", "Hatred & Enemies", "heart", "Hatred, enmity, revenge and bitterness, and the command to love one's enemies."),
    ("forgiveness", "Forgiveness", "heart", "Forgiving others, and being forgiven by God."),
    ("joy", "Joy & Contentment", "heart", "Joy, happiness, contentment and gratitude."),
    ("sin-repentance", "Sin & Repentance", "way", "Sin, temptation and turning back to God."),
    ("new-birth", "Conversion & New Birth", "way", "Conversion, regeneration and the call to decide for Christ."),
    ("grace-salvation", "Grace & Salvation", "way", "Grace, justification and how a person is saved."),
    ("faith-doubt", "Faith & Doubt", "way", "Faith, belief, doubt and assurance."),
    ("prayer", "Prayer", "way", "Prayer, intercession and dependence on God."),
    ("holiness", "Holiness & Christian Living", "way", "Discipleship, conduct, self-denial and growth in holiness."),
    ("pride-humility", "Pride & Humility", "way", "Pride, ambition and humility."),
    ("suffering", "Suffering & Trials", "hard", "Suffering, affliction, grief, disaster and persecution."),
    ("fear-courage", "Fear & Courage", "hard", "Fear, anxiety and courage."),
    ("death", "Death & Dying", "hard", "Death, dying, funerals and mortality."),
    ("heaven-hope", "Heaven & Hope", "last", "Heaven, the resurrection hope and the life to come."),
    ("judgment", "Judgment & Hell", "last", "Judgment, hell and the wrath of God."),
    ("christ-cross", "Christ & the Cross", "god", "The person of Christ, the incarnation, the cross and the resurrection."),
    ("holy-spirit", "The Holy Spirit", "god", "The Holy Spirit, revival and spiritual power."),
    ("providence", "Providence & Trust", "god", "God's providence and provision, and trusting his care."),
    ("justice-society", "Justice, War & Society", "world", "Justice, race, war and peace, the nation, poverty and social duty."),
    ("money-work", "Money, Work & Generosity", "world", "Money, wealth, work, vocation, stewardship and giving."),
    ("church-unity", "Church & Unity", "world", "The church, the sacraments, ministry and unity among Christians."),
    ("reason-truth", "Reason, Truth & Scripture", "world", "Faith and reason, apologetics, truth, the Bible and learning."),
]
CAT_IDS = {c[0] for c in CATEGORIES}

SHORT = {
    "lewis": ("Lewis", "CL"), "muller": ("Müller", "GM"), "spurgeon": ("Spurgeon", "CS"),
    "wesley": ("Wesley", "JW"), "whitefield": ("Whitefield", "GW"), "edwards": ("Edwards", "JE"),
    "moody": ("Moody", "DM"), "finney": ("Finney", "CF"), "graham": ("Graham", "BG"),
    "mlk": ("King", "MK"), "bonhoeffer": ("Bonhoeffer", "DB"), "lloyd-jones": ("Lloyd-Jones", "LJ"),
    "luther": ("Luther", "ML"), "augustine": ("Augustine", "Au"), "sunday": ("Sunday", "BS"),
}
TYPES = {"sermon", "homily", "address", "broadcast", "lecture", "sermon-series"}
DATE_ISO = re.compile(r"^\d{3,4}(-\d{2}(-\d{2})?)?$")


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def norm_title(s):
    return re.sub(r"^(the|a|an)-", "", slug(s))


def clean_url(u):
    u = (u or "").strip()
    return u if re.match(r"^https?://", u, re.I) else ""


def clean_links(links):
    out, seen = [], set()
    for l in links or []:
        url = clean_url(l.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"label": (l.get("label") or url).strip(), "url": url})
    return out


def birth_year(lifespan):
    m = re.search(r"(\d{3,4})", lifespan or "")
    return int(m.group(1)) if m else 9999


def parse_iso(s):
    """'1941-06-08' -> (1941, 6, 8); '1941' -> (1941, None, None); '' -> None"""
    m = re.match(r"^(\d{3,4})(?:-(\d{2}))?(?:-(\d{2}))?", (s or "").strip())
    if not m:
        return None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None), (int(m.group(3)) if m.group(3) else None)


def frac_year(d, default_mid=True):
    y, m, dd = d
    if m is None:
        return y + (0.5 if default_mid else 0)
    if dd is None:
        return y + (m - 0.5) / 12
    return y + (m - 1) / 12 + (dd - 0.5) / 365


def age_range(born, d):
    """Return (lo, hi) completed years of age at date d, given birth date."""
    by, bm, bd = born
    y, m, dd = d
    if bm and bd and m and dd:
        a = y - by - (1 if (m, dd) < (bm, bd) else 0)
        return a, a
    if bm and m:
        if m < bm:
            return y - by - 1, y - by - 1
        if m > bm:
            return y - by, y - by
    return y - by - 1, y - by


def clean_sermon(s, pid, warnings):
    t = {k: (v.strip() if isinstance(v, str) else v) for k, v in s.items()}
    t["preacher_id"] = pid
    if t.get("type") not in TYPES:
        warnings.append(f"{pid}: bad type {t.get('type')!r} on {t.get('title')!r} -> sermon")
        t["type"] = "sermon"
    if t.get("date_iso") and not DATE_ISO.match(t["date_iso"]):
        warnings.append(f"{pid}: bad date_iso {t['date_iso']!r} on {t['title']!r} -> blank")
        t["date_iso"] = ""
    if t.get("date_iso") and len(t["date_iso"].split("-")[0]) == 3:
        t["date_iso"] = "0" + t["date_iso"]
    cats = [c for c in (t.get("categories") or []) if c in CAT_IDS]
    prim = t.get("primary_category")
    if prim not in CAT_IDS:
        prim = cats[0] if cats else None
    if not prim:
        warnings.append(f"{pid}: no valid category on {t['title']!r} -> dropped")
        return None
    t["primary_category"] = prim
    t["categories"] = [prim] + [c for c in cats if c != prim][:2]
    for k in ("read_url", "listen_url"):
        t[k] = clean_url(t.get(k))
    t["sources"] = clean_links(t.get("sources"))
    if not t["sources"]:
        warnings.append(f"{pid}: no sources on {t['title']!r} -> dropped")
        return None
    if t.get("copyright") != "public-domain":
        t["copyright"] = "in-copyright"
        if t.get("key_line"):
            warnings.append(f"{pid}: key_line removed from in-copyright {t['title']!r}")
        t["key_line"] = ""
    if t.get("key_line") and len(t["key_line"].split()) > 32:
        warnings.append(f"{pid}: key_line too long on {t['title']!r} -> removed")
        t["key_line"] = ""
    t.setdefault("verification_status", "verified")
    t.setdefault("verification_note", "")
    for k in ("date_text", "place", "occasion", "scripture", "published_in", "summary", "context", "key_line", "unverified_notes"):
        t[k] = t.get(k) or ""
    if t["unverified_notes"].lower().strip(" .") in {"none", "n/a", "-", ""}:
        t["unverified_notes"] = ""
    if not t["summary"]:
        warnings.append(f"{pid}: empty summary on {t['title']!r} -> dropped")
        return None
    return t


def attach_life(p, life, warnings):
    """Normalise a life timeline and precompute bar positions."""
    born = parse_iso(life.get("born", {}).get("date_iso")) or (birth_year(p["lifespan"]), None, None)
    died_raw = parse_iso(life.get("died", {}).get("date_iso"))
    died = died_raw or (int(re.findall(r"\d{3,4}", p["lifespan"])[-1]), None, None)
    by, dy = frac_year(born), frac_year(died)
    span = max(1e-6, dy - by)

    def pos(d):
        return max(0.0, min(1.0, (frac_year(d) - by) / span))

    phases = sorted(life.get("phases", []), key=lambda ph: (ph["start_year"], ph["end_year"]))
    for i, ph in enumerate(phases):
        ph["sources"] = clean_links(ph.get("sources"))
        ph["a"] = 0.0 if i == 0 else max(0.0, min(1.0, (ph["start_year"] - by) / span))
    for i, ph in enumerate(phases):
        ph["b"] = phases[i + 1]["a"] if i + 1 < len(phases) else 1.0
        if ph["b"] < ph["a"]:
            warnings.append(f"{p['id']}: overlapping phases near {ph['label']!r}")
            ph["b"] = ph["a"]

    def phase_at(x):
        for i, ph in enumerate(phases):
            if ph["a"] <= x < ph["b"] or (i == len(phases) - 1 and x <= 1.0):
                return i
        return -1

    events = []
    for e in life.get("events", []):
        d = parse_iso(e.get("date_iso"))
        e["sources"] = clean_links(e.get("sources"))
        e["pos"] = pos(d) if d else None
        e["phase_idx"] = phase_at(e["pos"]) if d else -1
        events.append(e)
    events.sort(key=lambda e: (e["pos"] if e["pos"] is not None else 2))

    p["life"] = {
        "born": life.get("born", {}),
        "died": life.get("died", {}),
        "born_label": str(born[0]),
        "died_label": str(died[0]),
        "life_summary": life.get("life_summary", ""),
        "phases": phases,
        "events": events,
        "sources": clean_links(life.get("sources")),
    }
    return born, died, pos, phase_at


ABBR = set("""
mr mrs messrs dr st rev revd viz ver vv vs cf ch chap chaps vol vols no nos p pp sq ff ibid esq jun sen capt lt sr jr mt co
gen ex exod lev num deut josh judg sam kgs chron neh esth ps psa prov eccl eccles cant isa jer lam ezek dan hos obad mic nah
hab zeph hag zech mal matt mk lk jno jn rom cor gal eph phil col thess tim tit philem heb jas pet rev art sect sec fig ult inst
""".split())
BOUNDARY = re.compile(r"([.!?]+)([\"'”’)\]]*)(\s+)(?=[\"'“‘(\[]?[A-Z0-9])")


def split_sentences(text):
    """Split verbatim text into sentence 'verses'. ' '.join(result) == whitespace-normalised text."""
    text = re.sub(r"\s+", " ", text).strip()
    out, start = [], 0
    for m in BOUNDARY.finditer(text):
        before = text[start:m.start()]
        word = re.findall(r"([A-Za-z]+)$", before)
        w = word[0] if word else ""
        if m.group(1) == "." and (w.lower() in ABBR or (len(w) == 1 and w.isupper())):
            continue
        out.append(text[start:m.end(2)])
        start = m.end()
    if start < len(text):
        out.append(text[start:])
    merged = []
    for s in out:
        if merged and len(merged[-1].split()) < 4:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    if len(merged) > 1 and len(merged[-1].split()) < 3:
        last = merged.pop()
        merged[-1] = merged[-1] + " " + last
    return merged


def prepare_text(tx):
    """Turn {t:'p', x:'...'} blocks into {t:'p', s:[sentences]} for verse-level marking."""
    chapters = []
    for ch in tx.get("chapters", []):
        blocks = []
        for b in ch.get("blocks", []):
            x = (b.get("x") or "").strip()
            if not x:
                continue
            t = b.get("t", "p")
            if t in ("p", "q"):
                s = split_sentences(x)
                assert " ".join(s) == re.sub(r"\s+", " ", x).strip()
                blocks.append({"t": t, "s": s})
            elif t == "v":
                blocks.append({"t": "v", "x": x})
            else:
                blocks.append({"t": "h", "x": x})
        if blocks:
            chapters.append({"title": ch.get("title", ""), "blocks": blocks})
    out = {k: tx.get(k, "") for k in ("edition", "source_label", "source_url", "note")}
    out["chapters"] = chapters
    return out


VERSIONS = ["en-modern", "en-plain", "nl-formal", "nl-easy"]


def read_keyed(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if "\t" in line:
            k, v = line.split("\t", 1)
            out[k.strip()] = v.strip()
    return out


def paragraph_starts(tx):
    starts, first = {}, None
    for ci, ch in enumerate(tx["chapters"]):
        vn = 0
        for b in ch["blocks"]:
            if b["t"] == "h":
                continue
            n = len(b.get("s") or [1])
            starts[f"{ci}.{vn + 1}"] = True
            vn += n
    return starts


def verse_keys(tx):
    keys = []
    for ci, ch in enumerate(tx["chapters"]):
        vn = 0
        for b in ch["blocks"]:
            if b["t"] == "h":
                continue
            for _ in (b.get("s") or [1]):
                vn += 1
                keys.append(f"{ci}.{vn}")
    return keys


def apply_translation(tx, tr):
    """Rebuild tx's chapters with translated text; returns None if any unit is missing."""
    chapters = []
    multi = len(tx["chapters"]) > 1
    for ci, ch in enumerate(tx["chapters"]):
        title = ch.get("title", "")
        if multi and title:
            title = tr.get(f"T:{ci}")
            if not title:
                return None
        vn, blocks = 0, []
        for bi, b in enumerate(ch["blocks"]):
            if b["t"] == "h":
                x = tr.get(f"H:{ci}.{bi}")
                if not x:
                    return None
                blocks.append({"t": "h", "x": x})
                continue
            if b["t"] == "v":
                vn += 1
                x = tr.get(f"{ci}.{vn}")
                if not x:
                    return None
                blocks.append({"t": "v", "x": x.replace(" / ", "\n")})
                continue
            ss = []
            for _ in b["s"]:
                vn += 1
                x = tr.get(f"{ci}.{vn}")
                if not x:
                    return None
                ss.append(x)
            blocks.append({"t": b["t"], "s": ss})
        chapters.append({"title": title, "blocks": blocks})
    return chapters


ERAS = [(500, "4th–5th century"), (1600, "16th century"), (1800, "18th century"), (1900, "19th century"), (2100, "20th century")]


def era_of(p):
    floruit = p["sort_year"] + 35
    for i, (limit, label) in enumerate(ERAS):
        if floruit < limit:
            return i, label
    return len(ERAS) - 1, ERAS[-1][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "data", "verified"))
    ap.add_argument("--out", default=os.path.join(HERE, "dist", "index.html"))
    ap.add_argument("--json", default=os.path.join(HERE, "data", "sermons.json"))
    args = ap.parse_args()
    data_dir = os.path.dirname(args.src.rstrip("/"))
    is_sample = "sample" in args.src

    warnings = []
    preachers, sermons, keys = {}, [], set()

    files = sorted(glob.glob(os.path.join(args.src, "*.json")))
    main_files = [f for f in files if not os.path.basename(f).startswith(("gap-", "_"))]
    gap_files = [f for f in files if os.path.basename(f).startswith("gap-")]

    for f in main_files:
        d = json.load(open(f))
        pid = os.path.splitext(os.path.basename(f))[0]
        p = dict(d["preacher"])
        p["id"] = pid
        p["short"], p["monogram"] = SHORT.get(pid, (p["name"].split()[-1], p["name"][0]))
        p["sort_year"] = birth_year(p.get("lifespan"))
        p["era"], p["era_label"] = era_of(p)
        p["archive_links"] = clean_links(p.get("archive_links"))
        p["sources"] = clean_links(p.get("sources"))
        preachers[pid] = p
        for s in d["sermons"]:
            t = clean_sermon(s, pid, warnings)
            if not t:
                continue
            key = (pid, norm_title(t["title"]))
            if key in keys:
                warnings.append(f"{pid}: duplicate {t['title']!r} -> skipped")
                continue
            keys.add(key)
            sermons.append(t)

    for f in gap_files:
        d = json.load(open(f))
        for s in d["sermons"]:
            pid = s.get("preacher_id")
            if pid not in preachers:
                warnings.append(f"gap: unknown preacher {pid!r} on {s.get('title')!r} -> dropped")
                continue
            t = clean_sermon(s, pid, warnings)
            if not t:
                continue
            key = (pid, norm_title(t["title"]))
            if key in keys:
                warnings.append(f"gap: duplicate {t['title']!r} ({pid}) -> skipped")
                continue
            keys.add(key)
            sermons.append(t)

    # stable ids
    used = set()
    for t in sermons:
        base = f"{t['preacher_id']}-{slug(t['title'])}"
        sid, n = base, 2
        while sid in used:
            sid, n = f"{base}-{n}", n + 1
        used.add(sid)
        t["id"] = sid

    # life timelines + where each sermon falls
    life_dir = os.path.join(data_dir, "life")
    ctx_dir = os.path.join(data_dir, "lifectx")
    for pid, p in preachers.items():
        lf = os.path.join(life_dir, pid + ".json")
        if not os.path.exists(lf):
            continue
        born, died, pos, phase_at = attach_life(p, json.load(open(lf)), warnings)
        ctx = {}
        cf = os.path.join(ctx_dir, pid + ".json")
        if os.path.exists(cf):
            for c in json.load(open(cf)).get("sermons", []):
                ctx[c.get("id") or norm_title(c.get("title", ""))] = c
        labels = [ph["label"] for ph in p["life"]["phases"]]
        for t in (x for x in sermons if x["preacher_id"] == pid):
            d = parse_iso(t["date_iso"])
            t["life_pos"], t["phase_idx"], t["age_text"] = None, -1, ""
            if d:
                t["life_pos"] = pos(d)
                t["phase_idx"] = phase_at(t["life_pos"])
                lo, hi = age_range(born, d)
                end = re.search(r"\b(\d{3,4})\s*[–—-]\s*(\d{2,4})\b", t["date_text"])
                if end and t["type"] == "sermon-series":
                    ey = end.group(2)
                    ey = int(ey if len(ey) >= 3 else end.group(1)[: 4 - len(ey)] + ey)
                    hi = age_range(born, (ey, None, None))[1]
                if 0 <= lo <= 120:
                    t["age_text"] = f"Aged {lo}" if lo == hi else f"Aged {lo}–{hi}"
            c = ctx.get(t["id"]) or ctx.get(norm_title(t["title"]))
            if c:
                if c.get("life_phase") in labels:
                    t["phase_idx"] = labels.index(c["life_phase"])
                if c.get("life_context"):
                    t["life_context"] = c["life_context"].strip()
            if d is None and t["phase_idx"] < 0 and c and c.get("life_phase") in labels:
                t["phase_idx"] = labels.index(c["life_phase"])

    # legitimate recordings found by the audio pass (confirmed against the source page)
    for f in glob.glob(os.path.join(data_dir, "audio", "*.json")):
        rows = {r.get("id"): r for r in json.load(open(f)).get("rows", [])}
        for t in sermons:
            r = rows.get(t["id"])
            if not r:
                continue
            url = clean_url(r.get("listen_url"))
            if url and r.get("kind") != "none":
                t["listen_url"], t["listen_label"], t["listen_kind"] = url, (r.get("listen_label") or "Recording").strip(), r.get("kind")
            elif r.get("kind") == "none" and t.get("listen_url"):
                warnings.append(f"audio pass cleared listen_url on {t['id']}: {r.get('evidence', '')[:80]}")
                t["listen_url"] = ""

    # full texts: data/texts/<id>.json, or data/texts-raw/<preacher>/<slug>.json matched by title
    text_dir = os.path.join(data_dir, "texts")
    raw = {}
    for f in glob.glob(os.path.join(data_dir, "texts-raw", "*", "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            warnings.append(f"unreadable text file {f}")
            continue
        pid = os.path.basename(os.path.dirname(f))
        raw.setdefault(pid, []).append((norm_title(d.get("title") or ""), os.path.splitext(os.path.basename(f))[0], f))
    texts = {}
    for t in sermons:
        tf = os.path.join(text_dir, t["id"] + ".json")
        t["has_text"], t["words"] = False, 0
        if not os.path.exists(tf):
            cands = raw.get(t["preacher_id"], [])
            nt, sl = norm_title(t["title"]), slug(t["title"])
            hit = next((c for c in cands if c[0] == nt or c[1] == sl), None)
            if not hit and cands:
                best = max(cands, key=lambda c: difflib.SequenceMatcher(None, c[0], nt).ratio())
                if difflib.SequenceMatcher(None, best[0], nt).ratio() >= 0.86:
                    hit = best
                    warnings.append(f"text matched loosely: {t['id']} <- {os.path.basename(best[2])}")
            if not hit:
                continue
            tf = hit[2]
        if t["copyright"] != "public-domain":
            warnings.append(f"text present for in-copyright {t['id']} -> ignored")
            continue
        tx = prepare_text(json.load(open(tf)))
        words = sum(len(" ".join(b.get("s", [])).split()) + len(b.get("x", "").split())
                    for ch in tx["chapters"] for b in ch["blocks"] if b["t"] != "h")
        if words < 150:
            warnings.append(f"text for {t['id']} too short ({words} words) -> ignored")
            continue
        t["has_text"], t["words"] = True, words
        texts[t["id"]] = tx

    # translations (data/translations/<version>/<sermon>__<n>.txt) and added section headings
    chunk_list = {}
    rf = os.path.join(data_dir, "translations", "reviewed.json")
    reviewed = set(json.load(open(rf))) if os.path.exists(rf) else None
    cf = os.path.join(data_dir, "translations", "chunks.json")
    if os.path.exists(cf):
        for c in json.load(open(cf)):
            chunk_list.setdefault(c["sid"], []).append(c["id"])
    versions = {}
    for t in sermons:
        t["versions"] = []
        tx = texts.get(t["id"])
        if not tx or t["id"] not in chunk_list:
            continue
        for ver in VERSIONS:
            if reviewed is not None and not all(cid in reviewed for cid in chunk_list[t["id"]]):
                continue
            files = [os.path.join(data_dir, "translations", ver, cid + ".txt") for cid in chunk_list[t["id"]]]
            if not all(os.path.exists(f) for f in files):
                continue
            tr = {}
            for f in files:
                tr.update(read_keyed(f))
            chs = apply_translation(tx, tr)
            if chs is None:
                warnings.append(f"translation {ver} incomplete for {t['id']}")
                continue
            versions.setdefault(ver, {})[t["id"]] = {"chapters": chs}
            t["versions"].append(ver)
        sec_files = [os.path.join(data_dir, "sections", cid + ".json") for cid in chunk_list[t["id"]]
                     if reviewed is None or cid in reviewed]
        secs, valid, starts = [], set(verse_keys(tx)), paragraph_starts(tx)
        order = {k: i for i, k in enumerate(verse_keys(tx))}
        for f in sec_files:
            if not os.path.exists(f):
                continue
            try:
                items = json.load(open(f))
            except Exception:
                warnings.append(f"bad sections file {os.path.basename(f)}")
                continue
            for it in items if isinstance(items, list) else []:
                at, en, nl = str(it.get("at", "")), str(it.get("en", "")).strip(), str(it.get("nl", "")).strip()
                if at not in valid or not en:
                    continue
                if at not in starts:  # snap to the start of its paragraph
                    i = order[at]
                    while i > 0 and verse_keys(tx)[i] not in starts:
                        i -= 1
                    at = verse_keys(tx)[i]
                secs.append({"at": at, "en": en[:80], "nl": (nl or en)[:80]})
        if secs:
            seen, uniq_secs = set(), []
            for sc in sorted(secs, key=lambda x: order[x["at"]]):
                if sc["at"] not in seen:
                    seen.add(sc["at"])
                    uniq_secs.append(sc)
            tx["sections"] = uniq_secs

    plist = sorted(preachers.values(), key=lambda p: p["sort_year"])
    data = {
        "generated": datetime.date.today().strftime("%-d %B %Y"),
        "groups": [{"id": g, "label": l} for g, l in GROUPS],
        "categories": [{"id": c, "label": l, "group": g, "desc": d} for c, l, g, d in CATEGORIES],
        "preachers": plist,
        "sermons": sermons,
    }

    if not is_sample:
        json.dump(data, open(args.json, "w"), ensure_ascii=False, indent=1)

    tpl = open(os.path.join(HERE, "template.html")).read()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = tpl.replace("/*__DATA__*/", blob)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    root, ext = os.path.splitext(args.out)
    open(root + ".artifact" + ext, "w").write(page.replace("/*__TEXTS__*/", "null"))
    tdist = os.path.join(os.path.dirname(args.out), "texts")
    if os.path.isdir(tdist):
        shutil.rmtree(tdist)
    os.makedirs(tdist, exist_ok=True)
    bundles = {}
    for t in sermons:
        if t["id"] in texts:
            bundles.setdefault(t["preacher_id"], {})[t["id"]] = texts[t["id"]]
    for pid, b in bundles.items():
        json.dump(b, open(os.path.join(tdist, pid + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))
    vbundles = {}
    for ver, by in versions.items():
        for sid, v in by.items():
            pid = next(t["preacher_id"] for t in sermons if t["id"] == sid)
            vbundles.setdefault((pid, ver), {})[sid] = v
    for (pid, ver), b in vbundles.items():
        json.dump(b, open(os.path.join(tdist, f"{pid}.{ver}.json"), "w"), ensure_ascii=False, separators=(",", ":"))

    inline_obj = {"__versions": {ver: by for ver, by in versions.items()}}
    inline_obj.update(texts)
    inline = json.dumps(inline_obj, ensure_ascii=False).replace("</", "<\\/")
    standalone = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n"
        "</head>\n<body>\n" + page.replace("/*__TEXTS__*/", inline) + "\n</body>\n</html>\n"
    )
    open(args.out, "w").write(standalone)

    # GitHub Pages build (docs/): same app, Friends backed by Firebase instead of claude.ai capabilities
    fb_cfg = os.path.join(HERE, "firebase-config.json")
    if not is_sample:
        cfg = json.load(open(fb_cfg)) if os.path.exists(fb_cfg) else None
        adapter = open(os.path.join(HERE, "firebase-adapter.js")).read()
        docs = os.path.join(HERE, "docs")
        if os.path.isdir(os.path.join(docs, "texts")):
            shutil.rmtree(os.path.join(docs, "texts"))
        os.makedirs(os.path.join(docs, "texts"), exist_ok=True)
        for f in glob.glob(os.path.join(tdist, "*.json")):
            shutil.copy(f, os.path.join(docs, "texts", os.path.basename(f)))
        desc = ("Sermons of 15 great preachers, from Augustine to Billy Graham, sorted by subject, with sourced context, "
                "where the preacher was in life, and full public-domain texts to read, mark and listen to.")
        head = (
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f'<meta name="description" content="{desc}">\n'
            '<meta property="og:title" content="The Pulpit Index">\n'
            f'<meta property="og:description" content="{desc}">\n'
            '<link rel="manifest" href="manifest.webmanifest">\n<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">\n'
            '<link rel="icon" type="image/png" href="icons/icon-192.png">\n'
            '<meta name="theme-color" content="#f5f5f2" media="(prefers-color-scheme: light)">\n'
            '<meta name="theme-color" content="#0b0b0d" media="(prefers-color-scheme: dark)">\n'
            '<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="mobile-web-app-capable" content="yes">\n'
            '<meta name="apple-mobile-web-app-title" content="Pulpit">\n<meta name="apple-mobile-web-app-status-bar-style" content="default">\n'
            "<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n"
            + ("<script>window.PULPIT_PAGES=true;window.PULPIT_FIREBASE=" + json.dumps(cfg) + ";"
               "window.PULPIT_BACKEND_READY=new Promise(function(res,rej){window.PULPIT_BACKEND_RESOLVE=res;window.PULPIT_BACKEND_REJECT=rej;"
               "setTimeout(function(){rej(new Error('timeout'))},15000);});</script>\n"
               '<script type="module">\n' + adapter + "\n</script>\n" if cfg else "<script>window.PULPIT_PAGES=true;</script>\n")
            + "</head>\n<body>\n"
        )
        open(os.path.join(docs, "index.html"), "w").write(head + page.replace("/*__TEXTS__*/", "null") + "\n</body>\n</html>\n")
        open(os.path.join(docs, ".nojekyll"), "w").write("")
        # installable web app: manifest, icons, offline service worker (cache name changes with each build)
        manifest = {"name": "The Pulpit Index", "short_name": "Pulpit", "description": desc, "start_url": "./", "scope": "./",
                    "display": "standalone", "background_color": "#0b0b0d", "theme_color": "#141417",
                    "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                              {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                              {"src": "icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
        json.dump(manifest, open(os.path.join(docs, "manifest.webmanifest"), "w"), indent=1)
        if os.path.isdir(os.path.join(docs, "icons")):
            shutil.rmtree(os.path.join(docs, "icons"))
        shutil.copytree(os.path.join(HERE, "icons"), os.path.join(docs, "icons"))
        import hashlib
        stamp = hashlib.sha1(open(os.path.join(docs, "index.html"), "rb").read()).hexdigest()[:10]
        open(os.path.join(docs, "sw.js"), "w").write(open(os.path.join(HERE, "sw.js")).read().replace("__BUILD__", stamp))
        print(f"GitHub Pages build -> docs/index.html (+{len(bundles)} text bundles, friends {'on' if cfg else 'off until firebase-config.json exists'})")

    counts = {c: 0 for c in CAT_IDS}
    for t in sermons:
        for c in t["categories"]:
            counts[c] += 1
    print("translations:", {ver: len(by) for ver, by in versions.items()}, "| with sections:", sum(1 for x in texts.values() if x.get("sections")))
    print(f"preachers={len(plist)} sermons={len(sermons)} texts={len(texts)} "
          f"lives={sum(1 for p in plist if p.get('life'))} -> {args.out} ({len(standalone)//1024} KB standalone, {len(page)//1024} KB artifact)")
    print("by preacher:", {p["id"]: sum(1 for t in sermons if t["preacher_id"] == p["id"]) for p in plist})
    print("by subject:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))
    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings:
            print("  -", w)


if __name__ == "__main__":
    sys.exit(main())
