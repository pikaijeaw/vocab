#!/usr/bin/env python3
"""HSK vocab sync (run every 2 weeks by vocab-sync.timer).

1. Download the HSK word list (drkameleon/complete-hsk-vocabulary, MIT).
2. Check every CSV row against it: word exists, traditional form, pinyin,
   HSK 2.0 / 3.0 / 3.0-2026 levels. Wrong values are fixed in place.
3. Add words of HSK level 1-6 (any list) that the CSV is missing.
   Thai for new words is machine-translated (Google) and flagged thai_auto=1.
4. Rebuild dashboard/data.js, commit and push if anything changed.

Usage: update_hsk.py [--dry-run] [--no-push] [--max-new N]
"""
import argparse, csv, datetime, io, json, os, re, subprocess, sys, time, unicodedata
import urllib.parse, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(REPO, "hsk_vocab_level1-6.csv")
DATA_JS = os.path.join(REPO, "dashboard", "data_hsk.js")
SRC_URL = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json"
TR_URL = "https://translate.googleapis.com/translate_a/single"
COLS = ["hsk2_old_level", "hsk3_new_level", "hanzi", "traditional", "pinyin",
        "thai", "pos", "meaning", "hsk3_2026_level", "thai_auto"]
UA = {"User-Agent": "vocab-hsk-updater/1.0"}


def log(*a):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def fetch(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def norm_py(p):
    return re.sub(r"[\s'’·\-]", "", unicodedata.normalize("NFC", p)).lower()


def clean_py(p):
    p = re.sub(r"r5\b", "r", p)          # erhua: "yīhuǐr5" -> "yīhuǐr"
    p = re.sub(r"(?<=[a-zü])5\b", "", p)  # neutral-tone marker
    return re.sub(r"\s+", " ", p).strip()


def min_level(levels, prefix, maxlv=6):
    v = [int(l.split("-")[1]) for l in levels if l.startswith(prefix + "-")]
    v = [x for x in v if x <= maxlv]
    return str(min(v)) if v else ""


def translate_th(words):
    """zh-CN -> th, batched by newline; falls back to one-by-one if counts disagree."""
    out = {}
    def one(text):
        q = urllib.parse.urlencode({"client": "gtx", "sl": "zh-CN", "tl": "th", "dt": "t", "q": text})
        for attempt in range(4):
            try:
                d = json.loads(fetch(f"{TR_URL}?{q}", 30))
                return "".join(seg[0] for seg in d[0] if seg and seg[0])
            except Exception as e:
                log(f"translate retry {attempt+1}: {e}")
                time.sleep(3 * (attempt + 1))
        return ""
    for i in range(0, len(words), 40):
        chunk = words[i:i + 40]
        res = one("\n".join(chunk)).split("\n")
        if len(res) == len(chunk):
            out.update({w: t.strip() for w, t in zip(chunk, res)})
        else:
            for w in chunk:
                out[w] = one(w).strip(); time.sleep(0.4)
        time.sleep(1)
    return out


def git(*args, check=True):
    cmd = ["git", "-c", f"safe.directory={REPO}", "-c", "credential.helper=",
           "-c", "credential.helper=!gh auth git-credential", *args]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--no-push", action="store_true", help="write + commit, but do not push")
    ap.add_argument("--max-new", type=int, default=0, help="cap new words per run (0 = no cap)")
    a = ap.parse_args()

    log("downloading word list")
    src = json.loads(fetch(SRC_URL))
    up = {x["simplified"]: x for x in src}
    log(f"source has {len(up)} entries")

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        rows = list(rd)
        added_cols = [c for c in COLS if c not in (rd.fieldnames or [])]
    if added_cols:
        log(f"adding new column(s): {', '.join(added_cols)}")
    for r in rows:
        for c in COLS:
            r[c] = (r.get(c) or "").strip()

    fixes, unknown = [], []
    for r in rows:
        u = up.get(r["hanzi"])
        if not u:
            unknown.append(r["hanzi"]); continue
        forms = u["forms"]
        want = {
            "hsk2_old_level": min_level(u["level"], "old"),
            "hsk3_new_level": min_level(u["level"], "new"),
            "hsk3_2026_level": min_level(u["level"], "newest"),
        }
        trads = [f["traditional"] for f in forms]
        if r["traditional"] not in trads:
            want["traditional"] = trads[0]
        pys = [clean_py(f["transcriptions"]["pinyin"]) for f in forms]
        cur = clean_py(r["pinyin"])
        if norm_py(cur) not in {norm_py(p) for p in pys}:
            # keep the reading whose traditional form matches, else the first
            want["pinyin"] = next((p for f, p in zip(forms, pys) if f["traditional"] == r["traditional"]), pys[0])
        elif cur != r["pinyin"]:
            want["pinyin"] = cur
        for k, v in want.items():
            if r[k] != v:
                if k not in added_cols:
                    fixes.append((r["hanzi"], k, r[k], v))
                r[k] = v

    have = {r["hanzi"] for r in rows}
    new = [x for x in src if x["simplified"] not in have and any(
        re.fullmatch(r"(old|new|newest)-[1-6]", l) for l in x["level"])]
    new.sort(key=lambda x: (int(min_level(x["level"], "newest") or min_level(x["level"], "new") or min_level(x["level"], "old") or 9), x.get("frequency", 1e9)))
    if a.max_new:
        new = new[:a.max_new]

    log(f"checked {len(rows)} rows: {len(fixes)} fixes, {len(unknown)} not in source, {len(new)} new words")
    for h, k, o, n in fixes[:50]:
        log(f"  fix {h} {k}: {o!r} -> {n!r}")
    if unknown:
        log(f"  not in source (kept as-is): {' '.join(unknown[:30])}")

    if new and not a.dry_run:
        log(f"translating {len(new)} words to Thai")
        th = translate_th([x["simplified"] for x in new])
    else:
        th = {}
    for x in new:
        f0 = x["forms"][0]
        rows.append({
            "hsk2_old_level": min_level(x["level"], "old"),
            "hsk3_new_level": min_level(x["level"], "new"),
            "hanzi": x["simplified"], "traditional": f0["traditional"],
            "pinyin": clean_py(f0["transcriptions"]["pinyin"]),
            "thai": th.get(x["simplified"], ""), "pos": "/".join(x.get("pos", [])),
            "meaning": "; ".join(f0["meanings"]),
            "hsk3_2026_level": min_level(x["level"], "newest"),
            "thai_auto": "1",
        })
    if new:
        log("  new: " + " ".join(x["simplified"] for x in new[:60]) + (" ..." if len(new) > 60 else ""))

    if a.dry_run:
        log("dry run, nothing written"); return 0

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writeheader(); w.writerows({c: r[c] for c in COLS} for r in rows)
    new_csv = buf.getvalue()
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        old_csv = f.read()
    if new_csv != old_csv:
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            f.write(new_csv)
    js = "window.HSK_DATA = " + json.dumps([[r[c] for c in COLS] for r in rows], ensure_ascii=False, separators=(",", ":")) + ";"
    with open(DATA_JS, encoding="utf-8") as f:
        old_js = f.read()
    if js != old_js:
        with open(DATA_JS, "w", encoding="utf-8") as f:
            f.write(js)

    if not git("status", "--porcelain", "--", CSV_PATH, DATA_JS):
        log("no changes"); return 0
    git("add", CSV_PATH, DATA_JS)
    msg = f"hsk sync {datetime.date.today()}: +{len(new)} words, {len(fixes)} fixes"
    git("commit", "-m", msg)
    log(f"committed: {msg}")
    if not a.no_push:
        br = git("rev-parse", "--abbrev-ref", "HEAD"); git("pull", "--rebase", "--autostash", "origin", br)
        git("push", "origin", f"HEAD:{br}")
        log("pushed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"ERROR: {e}"); sys.exit(1)
