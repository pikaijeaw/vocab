#!/usr/bin/env python3
"""Build / check the TOEIC vocabulary CSV.

Sources (downloaded every run):
  * TOEIC Service List 1.2 (TSL, ~1250 words) and New General Service List 1.2
    (NGSL, ~2800 words) with easy-English definitions - Browne & Culligan,
    newgeneralservicelist.com, CC BY-SA 4.0. TSL + NGSL ~= 99% of TOEIC text.
  * Thai meanings: NECTEC LEXiTRON English-Thai dictionary (see README for the
    required acknowledgement). Words LEXiTRON lacks get a machine translation
    (Google) and thai_auto=1.
  * Pronunciation (IPA, US): CMU Pronouncing Dictionary.

What it does:
  * adds any TSL/NGSL word missing from the CSV
  * re-checks rank, band, IPA, English meaning, word forms of every row and
    fixes them in place (Thai you edited by hand is never overwritten; empty
    Thai is filled)
  * rebuilds dashboard/data.js, commits and pushes if anything changed

Usage: update_toeic.py [--dry-run] [--no-push]
"""
import argparse, csv, datetime, io, json, os, re, subprocess, sys, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(REPO, "toeic_vocab.csv")
DATA_JS = os.path.join(REPO, "dashboard", "data_toeic.js")
NG = "https://www.newgeneralservicelist.com/s/"
SRC = {
    "tsl_stats": NG + "TSL_12_stats.csv",
    "tsl_def": NG + "TSL_12_definitions.xlsx",
    "tsl_forms": NG + "TSL_12_lemmatized_for_teaching.csv",
    "ngsl_stats": NG + "NGSL_12_stats.csv",
    "ngsl_def": NG + "NGSL_12_with_English_definitions.xlsx",
    "ngsl_forms": NG + "NGSL_12_lemmatized_for_teaching.csv",
    "lexitron": "https://raw.githubusercontent.com/brianbv/lexitron-data/main/etlex.utf-8",
    "cmudict": "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
}
COLS = ["band", "list", "rank", "word", "ipa", "thai", "pos", "meaning", "forms", "thai_auto"]
# band: 1-3 = NGSL general words by frequency (1k/2k/3k), 4-6 = TOEIC-specific (TSL) by frequency
UA = {"User-Agent": "Mozilla/5.0 (vocab-toeic-updater)"}
POS_MAP = {"N": "n", "VT": "v", "VI": "v", "V": "v", "ADJ": "adj", "ADV": "adv", "PREP": "prep",
           "CONJ": "conj", "PRON": "pron", "DET": "det", "INT": "int", "AUX": "aux", "ABBR": "abbr", "ART": "art"}


def log(*a):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def fetch(url, timeout=120):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if attempt == 2:
                raise
            log(f"retry {url}: {e}"); time.sleep(5)


def text(b):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def xlsx_rows(data):
    z = zipfile.ZipFile(io.BytesIO(data)); m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ss = [''.join(t.text or '' for t in si.iter(m + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(m + "si")] \
        if "xl/sharedStrings.xml" in z.namelist() else []
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    out = []
    for r in ET.fromstring(z.read(sheet)).iter(m + "row"):
        row = []
        for c in r.iter(m + "c"):
            v, t = c.find(m + "v"), c.get("t")
            if t == "inlineStr": row.append(''.join(x.text or '' for x in c.iter(m + "t")))
            elif v is None: row.append("")
            elif t == "s": row.append(ss[int(v.text)])
            else: row.append(v.text)
        out.append([x.strip() for x in row])
    return out


def ranks(b):
    rows = list(csv.reader(io.StringIO(text(b))))[1:]
    return {r[0].strip().lower(): int(float(r[1])) for r in rows if len(r) > 1 and r[0].strip() and r[1].strip()}


def forms(b):
    out = {}
    for line in text(b).splitlines():
        if not line.strip() or line.startswith("#"): continue
        p = [x.strip() for x in line.split(",") if x.strip()]
        out[p[0].lower()] = p[1:]
    return out


def defs(b):
    return {r[0].strip().lower(): (r[1].strip() if len(r) > 1 else "") for r in xlsx_rows(b)[1:] if r and r[0].strip()}


def lexitron(b):
    lex = {}
    for m in re.finditer(r"<Doc>(.*?)</Doc>", text(b), re.S):
        d = dict(re.findall(r"<(\w+)>(.*?)</\1>", m.group(1), re.S))
        k = d.get("esearch", "").strip().lower(); th = re.sub(r"\s+", " ", d.get("tentry", "")).strip()
        if k and th: lex.setdefault(k, []).append((d.get("ecat", "").strip(), th))
    return lex


ARPA = {"AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "B": "b", "CH": "tʃ", "D": "d", "DH": "ð",
        "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h", "IH": "ɪ", "IY": "i", "JH": "dʒ", "K": "k",
        "L": "l", "M": "m", "N": "n", "NG": "ŋ", "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "r", "S": "s", "SH": "ʃ",
        "T": "t", "TH": "θ", "UH": "ʊ", "UW": "u", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ"}


def cmu(b):
    d = {}
    for line in text(b).splitlines():
        p = line.split("#")[0].split()
        if p and p[0] not in d: d[p[0]] = p[1:]   # first (most common) pronunciation; "word(2)" variants ignored
    return d


ONSETS = {tuple(o.split()) for o in (
    "P R|P L|B R|B L|T R|D R|K R|K L|G R|G L|F R|F L|TH R|SH R|K W|T W|D W|G W|S W|TH W|"
    "P Y|B Y|K Y|F Y|M Y|V Y|HH Y|S P|S T|S K|S M|S N|S L|S P R|S P L|S T R|S K R|S K W|S K Y|S P Y"
).split("|")}


def to_ipa(ph):
    """ARPAbet -> IPA with the stress mark placed before the syllable onset (maximal legal onset)."""
    seg = [re.match(r"([A-Z]+)(\d?)", p).groups() for p in ph]
    out, run = [], []          # run = consonants seen since the last vowel
    first_vowel = True
    for base, st in seg:
        if not st:
            run.append(base); continue
        k = len(run)
        if first_vowel:
            k = 0                           # all leading consonants are the onset
        else:
            for n in range(min(3, len(run)), 0, -1):
                if n == 1 or tuple(run[-n:]) in ONSETS:
                    k = len(run) - n; break
            else:
                k = len(run)
        coda, onset = run[:k], run[k:]
        out += [ARPA[c] for c in coda]
        if st in "12": out.append("ˈ" if st == "1" else "ˌ")
        out += [ARPA[c] for c in onset]
        out.append({"AH0": "ə", "ER0": "ɚ"}.get(base + st, ARPA[base]))
        run, first_vowel = [], False
    out += [ARPA[c] for c in run]
    return "".join(out)


def ipa_of(word, cd):
    parts = re.split(r"[\s\-]+", word.lower())
    res = []
    for p in parts:
        ph = cd.get(p) or cd.get(p.replace("'", ""))
        if not ph: return ""
        res.append(to_ipa(ph))
    return "/" + " ".join(res) + "/"


def thai_from_lex(word, lex, primary="", max_senses=3):
    """Thai senses from LEXiTRON. LEXiTRON lists senses in dictionary order, not by
    frequency, so `primary` (the most common sense, from machine translation) is used
    to pick which sense goes first. Returns (thai, pos, machine_used)."""
    senses, pos = [], []
    for cat, th in lex.get(word.lower(), []):
        th = re.sub(r"\s*\((?:[^()]*)\)\s*$", "", th).strip() or th   # drop trailing explanatory note
        if th not in senses: senses.append(th)
        pc = POS_MAP.get(cat.upper(), cat.lower())
        if pc and pc not in pos: pos.append(pc)
    machine = False
    if primary:
        hit = next((x for x in senses if x == primary), None) or next((x for x in senses if primary in x or x in primary), None)
        if hit:
            senses.remove(hit); senses.insert(0, hit)
        else:
            senses.insert(0, primary); machine = True
    return "; ".join(senses[:max_senses]), "/".join(pos), machine


def machine_th(words):
    """English -> Thai (single most common sense). Tries two Google endpoints, then MyMemory."""
    def one(w):
        q = urllib.parse.quote(w)
        for url, parse in (
            (f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl=th&q={q}", lambda d: d[0] if isinstance(d[0], str) else d[0][0]),
            (f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=th&dt=t&q={q}", lambda d: "".join(s[0] for s in d[0] if s[0])),
            (f"https://api.mymemory.translated.net/get?q={q}&langpair=en|th", lambda d: d["responseData"]["translatedText"]),
        ):
            try:
                t = parse(json.loads(fetch(url, 30))).strip()
                if t and re.search(r"[\u0e00-\u0e7f]", t): return t
            except Exception:
                continue
        return ""
    out = {}
    for w in words:
        out[w] = one(w); time.sleep(0.15)
    return out


def git(*args):
    r = subprocess.run(["git", "-c", f"safe.directory={REPO}", "-c", "credential.helper=",
                        "-c", "credential.helper=!gh auth git-credential", *args], cwd=REPO, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def band_of(lst, rank):
    if lst == "NGSL": return 1 if rank <= 1000 else 2 if rank <= 2000 else 3
    return 4 if rank <= 400 else 5 if rank <= 800 else 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    log("downloading sources")
    raw = {k: fetch(u) for k, u in SRC.items()}
    tr, nr = ranks(raw["tsl_stats"]), ranks(raw["ngsl_stats"])
    td, nd = defs(raw["tsl_def"]), defs(raw["ngsl_def"])
    tf, nf = forms(raw["tsl_forms"]), forms(raw["ngsl_forms"])
    lex, cd = lexitron(raw["lexitron"]), cmu(raw["cmudict"])
    log(f"TSL {len(tr)} words, NGSL {len(nr)} words, LEXiTRON {len(lex)} headwords, CMUdict {len(cd)}")

    want = {}   # word -> canonical fields from sources (TSL wins if a word is in both)
    for lst, rk, df, fm in (("NGSL", nr, nd, nf), ("TSL", tr, td, tf)):
        for w, r in rk.items():
            want[w] = {"list": lst, "rank": str(r), "band": str(band_of(lst, r)), "word": w,
                       "ipa": ipa_of(w, cd), "meaning": df.get(w, ""),
                       # drop contraction fragments like "isn", "m", "re" that are not real words
                       "forms": ", ".join(f for f in fm.get(w, []) if len(f) > 2 and f.lower() in cd)}

    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            rows = [{c: (r.get(c) or "").strip() for c in COLS} for r in csv.DictReader(f)]
    by = {r["word"].lower(): r for r in rows}
    fixes, gone = [], [r["word"] for r in rows if r["word"].lower() not in want]
    added = []
    for w, src in want.items():
        r = by.get(w)
        if r is None:
            r = {c: "" for c in COLS}; r["word"] = w; rows.append(r); by[w] = r; added.append(w)
        for k, v in src.items():
            if k == "meaning" and not v: continue          # keep old meaning if source has none
            if r[k] != v:
                if w not in added: fixes.append((w, k, r[k], v))
                r[k] = v

    need_th = [r["word"] for r in rows if not r["thai"]]   # hand-edited / existing Thai is never touched
    log(f"{len(rows)} rows: {len(added)} added, {len(fixes)} fixes, {len(need_th)} need Thai, "
        f"{len(gone)} no longer in the lists (kept)")
    for w, k, o, n in fixes[:40]: log(f"  fix {w} {k}: {o!r} -> {n!r}")
    if a.dry_run:
        log("dry run, nothing written"); return 0
    if need_th:
        log(f"looking up Thai for {len(need_th)} words")
        mt = machine_th(need_th)
        nmt = 0
        for w in need_th:
            r = by[w]
            th, pos, machine = thai_from_lex(w, lex, mt.get(w, ""))
            r["thai"], r["thai_auto"] = th, ("1" if machine else "")
            nmt += machine
            if pos and not r["pos"]: r["pos"] = pos
        log(f"Thai filled: {sum(1 for w in need_th if by[w]['thai'])}/{len(need_th)}, "
            f"{nmt} include a machine-translated sense (thai_auto=1)")

    rows.sort(key=lambda r: (int(r["band"] or 9), int(r["rank"] or 99999), r["word"]))
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=COLS, quoting=csv.QUOTE_ALL, lineterminator="\n")
    wr.writeheader(); wr.writerows(rows)
    def put(path, s, enc):
        old = open(path, encoding=enc).read() if os.path.exists(path) else None
        if old != s:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding=enc, newline="") as f: f.write(s)
    put(CSV_PATH, buf.getvalue(), "utf-8-sig")
    put(DATA_JS, "window.TOEIC_DATA = " + json.dumps([[r[c] for c in COLS] for r in rows], ensure_ascii=False, separators=(",", ":")) + ";", "utf-8")

    if not os.path.isdir(os.path.join(REPO, ".git")):
        log("not a git repo, skipping commit"); return 0
    if not git("status", "--porcelain", "--", CSV_PATH, DATA_JS):
        log("no changes"); return 0
    git("add", CSV_PATH, DATA_JS)
    msg = f"toeic sync {datetime.date.today()}: +{len(added)} words, {len(fixes)} fixes"
    git("commit", "-m", msg); log(f"committed: {msg}")
    if not a.no_push:
        br = git("rev-parse", "--abbrev-ref", "HEAD"); git("pull", "--rebase", "--autostash", "origin", br); git("push", "origin", f"HEAD:{br}"); log("pushed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"ERROR: {e}"); sys.exit(1)
