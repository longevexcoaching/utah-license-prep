#!/usr/bin/env python3
"""
Golden-set checker for the Utah license prep app.

index.html embeds five sub-apps as base64 blobs. That makes the git diff unreadable
by design, which is how PR #1 silently deleted the entire "Snap & Solve" sub-app and
nothing caught it but a human decoding the payload by hand.

This decodes every sub-app, parses the question banks, and compares the result to a
committed baseline. Any regression fails loudly.

    python check-bank.py            # check against bank-baseline.json  (exit 1 on fail)
    python check-bank.py --update   # re-baseline AFTER you've reviewed the change
    python check-bank.py --verbose  # per-domain breakdown

Note on parsing: the original 108 questions use bare keys ({d:"...",q:"..."}) and the
11 added 2026-07-30 use quoted keys ({"d": "...", "q": "..."}). Both are valid JS and
both are live. A checker that only matches one syntax reports a phantom regression --
that happened on the first run of this script. Hence the object walker below.
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
INDEX = HERE / "index.html"
BASELINE = HERE / "bank-baseline.json"


# ---------------------------------------------------------------- extraction

def extract_apps(html):
    """Pull the APPS map out of index.html. Returns {name: base64}."""
    m = re.search(r"const APPS\s*=\s*\{(.*?)\n?\};", html, re.S)
    if not m:
        die("could not find `const APPS={...}` in index.html")
    apps = dict(re.findall(r"(\w+)\s*:\s*\"([A-Za-z0-9+/=]+)\"", m.group(1)))
    if not apps:
        die("APPS block found but no base64 entries parsed out of it")
    return apps


def decode_app(name, b64):
    try:
        return base64.b64decode(b64).decode("utf-8", errors="replace")
    except Exception as exc:
        die(f"sub-app '{name}' failed to base64-decode: {exc}")


def scan_objects(s):
    """Yield every top-level {...} literal, respecting strings and escapes."""
    out, i, n = [], 0, len(s)
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        depth, j, instr, quote, esc = 0, i, False, "", False
        while j < n:
            c = s[j]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == quote:
                    instr = False
            elif c in "\"'":
                instr, quote = True, c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append(s[i:j + 1])
                    break
            j += 1
        i = j + 1
    return out


def field(obj, key):
    """Read a string field, bare or quoted key."""
    m = re.search(r'[{,]\s*"?%s"?\s*:\s*"((?:[^"\\]|\\.)*)"' % key, obj)
    return m.group(1) if m else None


def answer_index(obj):
    m = re.search(r'[{,]\s*"?a"?\s*:\s*(\d+)', obj)
    return int(m.group(1)) if m else None


def option_count(obj):
    m = re.search(r'[{,]\s*"?o"?\s*:\s*\[', obj)
    if not m:
        return None
    i = m.end() - 1
    depth, instr, quote, esc, items = 0, False, "", False, 0
    seen_content = False
    while i < len(obj):
        c = obj[i]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                instr = False
        elif c in "\"'":
            instr, quote = True, c
            seen_content = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return items + 1 if seen_content else 0
        elif c == "," and depth == 1:
            items += 1
        i += 1
    return None


def parse_questions(js):
    """Every object carrying a domain + options + answer is a question."""
    qs = []
    for obj in scan_objects(js):
        d, q = field(obj, "d"), field(obj, "q")
        a, o = answer_index(obj), option_count(obj)
        if d is None or q is None or a is None or o is None:
            continue
        qs.append({
            "d": d, "q": q, "a": a, "o": o,
            "e": field(obj, "e") or "",
            "r": field(obj, "r") or "",
        })
    return qs


def parse_weights(js):
    m = re.search(r"WEIGHTS\s*=\s*\{([^}]*)\}", js)
    if not m:
        return []
    return re.findall(r'"([^"]+)"\s*:', m.group(1))


def braces_balanced(js):
    depth, instr, quote, esc = 0, False, "", False
    for c in js:
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                instr = False
        elif c in "\"'":
            instr, quote = True, c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


# ---------------------------------------------------------------- survey

def survey():
    if not INDEX.exists():
        die(f"{INDEX} not found")
    html = INDEX.read_text(encoding="utf-8")
    names = dict(re.findall(r'(\w+):"([^"]+)"',
                            (re.search(r"const NAMES=\{([^}]*)\}", html) or
                             re.Match).group(1))) if re.search(r"const NAMES=\{", html) else {}
    apps = extract_apps(html)

    report = {}
    for name, b64 in apps.items():
        js = decode_app(name, b64)
        qs = parse_questions(js)
        weights = parse_weights(js)
        domains = {}
        for q in qs:
            domains[q["d"]] = domains.get(q["d"], 0) + 1
        report[name] = {
            "title": names.get(name, name),
            "decoded_bytes": len(js),
            "questions": len(qs),
            "domains": domains,
            "weights": sorted(weights),
            "braces_balanced": braces_balanced(js),
            "orphan_domains": sorted(set(domains) - set(weights)) if weights else [],
            "bad_answer_index": sum(1 for q in qs if not (0 <= q["a"] < q["o"])),
            "too_few_options": sum(1 for q in qs if q["o"] < 2),
            "empty_explanation": sum(1 for q in qs if not q["e"].strip()),
            "empty_reference": sum(1 for q in qs if not q["r"].strip()),
            "duplicate_questions": len(qs) - len({q["q"].strip().lower() for q in qs}),
        }
    return report


# ---------------------------------------------------------------- compare

def compare(now, base):
    fails, warns = [], []

    missing = set(base) - set(now)
    if missing:
        fails.append(f"SUB-APP DELETED: {', '.join(sorted(missing))} "
                     f"-- this is exactly the PR #1 regression")
    for name in sorted(set(now) - set(base)):
        warns.append(f"new sub-app not in baseline: {name}")

    for name in sorted(set(now) & set(base)):
        n, b = now[name], base[name]
        tag = f"[{name}]"

        if not n["braces_balanced"]:
            fails.append(f"{tag} braces are UNBALANCED in the decoded sub-app")

        if n["questions"] < b["questions"]:
            fails.append(f"{tag} questions DROPPED {b['questions']} -> {n['questions']}")
        elif n["questions"] > b["questions"]:
            warns.append(f"{tag} questions grew {b['questions']} -> {n['questions']} "
                         f"(run --update once you've reviewed them)")

        gone = set(b["domains"]) - set(n["domains"])
        if gone:
            fails.append(f"{tag} domain disappeared: {', '.join(sorted(gone))}")

        if n["orphan_domains"]:
            fails.append(f"{tag} question domains missing from WEIGHTS "
                         f"(they will never be drawn): {', '.join(n['orphan_domains'])}")

        for key, label in [
            ("bad_answer_index", "answer index out of range"),
            ("too_few_options", "fewer than 2 options"),
            ("duplicate_questions", "duplicate question text"),
            ("empty_explanation", "missing explanation"),
            ("empty_reference", "missing NEC/code reference"),
        ]:
            if n[key] > b.get(key, 0):
                fails.append(f"{tag} {label}: {b.get(key, 0)} -> {n[key]}")
            elif n[key] > 0:
                warns.append(f"{tag} {label}: {n[key]} (unchanged from baseline)")

    return fails, warns


# ---------------------------------------------------------------- cli

def die(msg):
    print(f"FAIL  {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="rewrite the baseline from the current file")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="per-domain question counts")
    args = ap.parse_args()

    now = survey()
    total = sum(a["questions"] for a in now.values())

    print(f"{'sub-app':10} {'questions':>9}  {'domains':>7}  {'weights':>7}  decoded")
    print("-" * 58)
    for name in sorted(now):
        a = now[name]
        print(f"{name:10} {a['questions']:>9}  {len(a['domains']):>7}  "
              f"{len(a['weights']):>7}  {a['decoded_bytes']:,} B")
    print("-" * 58)
    print(f"{'TOTAL':10} {total:>9}   across {len(now)} sub-apps")

    if args.verbose:
        for name in sorted(now):
            if now[name]["domains"]:
                print(f"\n{name} ({now[name]['title']}):")
                for d, c in sorted(now[name]["domains"].items()):
                    print(f"   {c:>4}  {d}")

    if args.update:
        BASELINE.write_text(json.dumps(now, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"\nbaseline written -> {BASELINE.name} ({total} questions, "
              f"{len(now)} sub-apps)")
        return 0

    if not BASELINE.exists():
        print(f"\nNo baseline yet. Review the numbers above, then:\n"
              f"    python check-bank.py --update")
        return 1

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    fails, warns = compare(now, base)

    print()
    for w in warns:
        print(f"WARN  {w}")
    for f in fails:
        print(f"FAIL  {f}")

    if fails:
        print(f"\n{len(fails)} regression(s). The bank is NOT safe to ship.")
        return 1
    print("PASS  no regressions against the baseline."
          + (f"  ({len(warns)} warning(s))" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
