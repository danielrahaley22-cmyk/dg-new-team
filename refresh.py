#!/usr/bin/env python3
"""Sales refresh for the DG New Team dashboard (Jan 2027 only).

    python3 refresh.py EXPORT.csv              # build data.js from a sheet export
    python3 refresh.py EXPORT.csv --as-of "2026-11-30 09:15"
    python3 refresh.py --check                 # privacy scan of the repo files

EXPORT.csv is a CSV download of either tab of "DG Discount Code Sales":
  * New Team tab  (preferred: its totals are checked against the sum), or
  * Data tab      (only rows whose Team starts with "New team" are kept).

Only code, state, first name, tickets, last 7 days, last sale (+ this
week's count) are written. Everything else in the export (orders, $,
status, notes, team, full names, handles) is dropped before it is written.
Sales are matched on code + state only.
"""
import csv, json, re, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
WEEKLY = ROOT / "weekly.json"
TZ = ZoneInfo("Australia/Melbourne")
WEEK1 = datetime(2026, 10, 19, tzinfo=TZ)  # Week 1 = w/c Mon 19 Oct 2026
STATES = {"Adelaide", "Brisbane", "Perth", "Melbourne", "Sydney"}

# ---------------------------------------------------------------- privacy
EMAIL = re.compile(r"[\w.+-]+\x40[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(\+?61[\s-]?|0)[2-478](?:[\s-]?\d){8}(?!\d)")
CSS_AT = {"media", "import", "font-face", "keyframes", "supports", "page", "charset", "layer", "container"}
HANDLE = re.compile(r"(?<![\w.])\x40([A-Za-z0-9_.]{2,})")
INSTA = re.compile(r"instagram\.com|instagr\.am", re.I)


def scan_text(name, text):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in EMAIL.finditer(line):
            if "users.noreply.github.com" not in m.group(0):
                hits.append((name, i, "email", m.group(0)))
        for m in PHONE.finditer(line):
            hits.append((name, i, "phone", m.group(0)))
        for m in HANDLE.finditer(line):
            if m.group(1).lower() not in CSS_AT:
                hits.append((name, i, "handle", m.group(0)))
        for m in INSTA.finditer(line):
            hits.append((name, i, "instagram link", m.group(0)))
    return hits


def repo_files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True).stdout.split()
    return [ROOT / f for f in out if not f.endswith((".png", ".ico", ".jpg"))]


def check(files=None):
    hits = []
    for p in files or repo_files():
        if p.is_file():
            hits += scan_text(p.name, p.read_text(errors="ignore"))
    for h in hits:
        print("  PRIVACY HIT %s:%d  %s  %s" % h)
    return not hits


# ---------------------------------------------------------------- export
def clean_name(promoter):
    """First name only. Blank if it looks like a handle or anything odd."""
    first = re.sub(r"\(.*?\)|\(.*", "", promoter or "").strip().split(" ")[0] if promoter else ""
    if not re.fullmatch(r"[^\W\d_][^\W\d_'-]{0,19}|[^\W\d_][^\W\d_]*['-][^\W\d_]+", first):
        return ""
    return first[0].upper() + first[1:]


def to_int(s):
    s = (s or "").replace(",", "").strip()
    return int(float(s)) if s else 0


def parse_sale(s):
    s = (s or "").strip()
    return datetime.strptime(s, "%d %b %Y %H:%M").replace(tzinfo=TZ) if s else None


def read_export(path):
    rows = list(csv.reader(open(path, newline="", encoding="utf-8-sig")))
    hi = next((i for i, r in enumerate(rows) if "Code" in r and "Last sale" in r), None)
    if hi is None:
        sys.exit("STOP: no header row with 'Code' and 'Last sale'. Is this the New Team or Data tab?")
    title = (Path(path).name + " " + " ".join(" ".join(r) for r in rows[:hi])).lower()
    if "july" in title or "2027 team" in title:
        sys.exit("STOP: this export looks like July 2027 team data. This dashboard is Jan 2027 only.")
    head = [h.strip() for h in rows[hi]]
    col = {h: head.index(h) for h in head}
    need = ["Code", "Event state", "Promoter", "Tickets", "Last 7 days tix", "Last sale"]
    miss = [n for n in need if n not in col]
    if miss:
        sys.exit("STOP: export is missing columns: " + ", ".join(miss))
    is_data_tab = "Team" in col

    expected = None
    if not is_data_tab:  # New Team tab has "Tickets:", N, "Last 7 days:", M above the header
        for r in rows[:hi]:
            if r and r[0].strip() == "Tickets:" and len(r) >= 4:
                expected = (to_int(r[1]), to_int(r[3]))

    out = {}
    for r in rows[hi + 1:]:
        if not r or not r[col["Code"]].strip():
            continue
        g = lambda k: r[col[k]].strip() if col[k] < len(r) else ""
        if is_data_tab and not g("Team").lower().startswith("new team"):
            continue
        code, state = g("Code").upper(), g("Event state")
        if state not in STATES:
            sys.exit(f"STOP: unknown state '{state}' for {code}")
        tickets = to_int(g("Tickets"))
        if tickets <= 0:
            continue
        key = f"{code}|{state}"
        if key in out:
            sys.exit(f"STOP: {code} appears twice for {state}")
        out[key] = {"code": code, "state": state, "name": clean_name(g("Promoter")),
                    "tickets": tickets, "last7": to_int(g("Last 7 days tix")),
                    "lastSale": g("Last sale")}
    return out, expected, ("Data tab" if is_data_tab else "New Team tab")


def roster_keys():
    html = (ROOT / "index.html").read_text()
    block = re.search(r"const ROSTER = (\[.*?\]);", html, re.S)
    return {f"{c}|{s}" for _, c, s in json.loads(block.group(1))} if block else set()


# ---------------------------------------------------------------- weeks
def monday_of(dt):
    d = dt.astimezone(TZ)
    return datetime(d.year, d.month, d.day, tzinfo=TZ) - timedelta(days=d.weekday())


def week_label(mon):
    n = (mon - WEEK1).days // 7 + 1
    sun = mon + timedelta(days=6)
    span = f"{mon.day}–{sun.day} {sun:%b}" if mon.month == sun.month else f"{mon.day} {mon:%b}–{sun.day} {sun:%b}"
    return f"Week {n} ({span})"


def update_weeks(sales, as_of):
    st = json.loads(WEEKLY.read_text())
    mon = monday_of(as_of)
    old_mon = datetime.fromisoformat(st["week_start"]).replace(tzinfo=TZ)
    last_at = datetime.fromisoformat(st["last_refresh"]["at"]).replace(tzinfo=TZ)
    if as_of < last_at:
        sys.exit(f"STOP: as-of {as_of:%d %b %H:%M} is older than the last refresh ({last_at:%d %b %H:%M}).")
    warn = []

    if mon > old_mon:  # a new team week has started: close the old one
        if mon - old_mon > timedelta(days=7):
            warn.append("More than one week since the last refresh: the finished week's counts include every week in between.")
        new_base = {}
        for k, r in sales.items():
            sold_before = parse_sale(r["lastSale"]) < mon
            if sold_before:
                new_base[k] = r["tickets"]
            else:
                new_base[k] = st["last_refresh"]["tickets"].get(k, 0)
                if last_at < mon - timedelta(hours=1):
                    warn.append(f"{r['code']} ({r['state']}): sold since Monday; any sales between the last refresh "
                                f"({last_at:%a %d %b %H:%M}) and Monday are counted in the new week, not the old one.")
        closed = {k: new_base.get(k, 0) - st["baseline"].get(k, 0) for k in new_base}
        closed = {k: v for k, v in closed.items() if v > 0}
        st["past_weeks"].insert(0, {"label": week_label(old_mon), "counts": closed})
        st["week_start"], st["baseline"] = mon.strftime("%Y-%m-%d"), new_base

    for k, r in sales.items():
        if parse_sale(r["lastSale"]) < mon:
            r["week"] = 0
            continue
        if k not in st["baseline"]:
            warn.append(f"{r['code']} ({r['state']}): no Monday baseline, week count capped at last 7 days.")
        r["week"] = max(0, min(r["tickets"] - st["baseline"].get(k, 0), r["last7"]))

    st["last_refresh"] = {"at": as_of.strftime("%Y-%m-%dT%H:%M"),
                          "tickets": {k: r["tickets"] for k, r in sales.items()}}
    return st, week_label(mon), warn


# ---------------------------------------------------------------- output
def js(v):
    return json.dumps(v, ensure_ascii=False)


def data_js_text(sales, as_of, label, past):
    rows = sorted(sales.values(), key=lambda r: (-r["tickets"], -r["last7"], r["code"]))
    lines = ["/* Generated by refresh.py from the New Team sales export. Do not edit by hand. */",
             f"const AS_OF = {js(as_of.strftime('%-d %b %Y, %-I:%M%p').replace('AM', 'am').replace('PM', 'pm'))};",
             f"const WEEK_LABEL = {js(label)};",
             "/* code, state, first name, tickets, last 7 days, last sale, week = tickets this team week (Mon–Sun) */",
             "const SALES = ["]
    lines += [f"  {{code:{js(r['code'])}, state:{js(r['state'])}, name:{js(r['name'])}, tickets:{r['tickets']}, "
              f"last7:{r['last7']}, lastSale:{js(r['lastSale'])}, week:{r['week']}}}," for r in rows]
    lines += ["];", "/* Finished weekly cash bonus weeks: tickets per code|state that week */", "const PAST_WEEKS = ["]
    lines += [f"  {{label:{js(w['label'])}, counts:{js(w['counts'])}}}," for w in past]
    lines += ["];", ""]
    return "\n".join(lines)


def main(argv):
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=ROOT)
    if argv[:1] == ["--check"]:
        ok = check()
        print("Privacy check: " + ("clean" if ok else "FAILED"))
        return 0 if ok else 1
    if not argv:
        print(__doc__)
        return 2
    path = Path(argv[0])
    as_of = datetime.now(TZ)
    if "--as-of" in argv:
        as_of = datetime.strptime(argv[argv.index("--as-of") + 1], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)

    sales, expected, kind = read_export(path)
    tot, tot7 = sum(r["tickets"] for r in sales.values()), sum(r["last7"] for r in sales.values())
    print(f"Read {kind}: {len(sales)} codes with sales, {tot} tickets, {tot7} in last 7 days")
    if expected and expected != (tot, tot7):
        sys.exit(f"STOP: tab says {expected[0]} tickets / {expected[1]} last 7 days, rows add up to {tot} / {tot7}.")
    if expected:
        print("  matches the tab's own totals")

    roster = roster_keys()
    for k in sorted(set(sales) - roster):
        print(f"  NOTE {k.replace('|', ' / ')} has sales but is not in the Links & codes roster")

    st, label, warn = update_weeks(sales, as_of)
    for w in warn:
        print("  WEEK " + w)
    text = data_js_text(sales, as_of, label, st["past_weeks"])
    weekly = json.dumps(st, indent=1, sort_keys=True) + "\n"
    hits = scan_text("data.js", text) + scan_text("weekly.json", weekly)
    for h in hits:
        print("  PRIVACY HIT %s:%d  %s  %s" % h)
    if hits:
        sys.exit("STOP: privacy check failed. Nothing was written.")
    DATA_JS.write_text(text)
    WEEKLY.write_text(weekly)
    wk = sorted(((r["week"], r["code"]) for r in sales.values() if r["week"]), reverse=True)
    print(f"{label}: {sum(w for w, _ in wk)} tickets" + ("  (" + ", ".join(f"{c} {w}" for w, c in wk) + ")" if wk else ""))
    print("Wrote data.js. Check the page (open index.html), then commit and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
