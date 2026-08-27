#!/usr/bin/env python3
"""Audit a prototype's hardcoded CSS values against the app's design tokens.

Splits every colour / font-size / radius in the page into three buckets:
  EXACT  already a token, just needs the var() swap
  NEAR   within tolerance of a token -- almost certainly meant to be that token
  NEW    no token comes close -- a real design decision that needs a DS answer

Usage:
    python3 tools/audit_tokens.py edeka-dankenbring.html
    python3 tools/audit_tokens.py edeka-dankenbring.html --new-only
"""

import argparse
import collections
import json
import math
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
NEAR_RGB = 12.0   # euclidean RGB distance still considered "meant to be this token"
NEAR_PX = 1.0


def load_tokens():
    p = REPO / "assets" / "ff-tokens.json"
    if not p.exists():
        sys.exit("run tools/gen_ff_tokens.py first")
    return json.loads(p.read_text(encoding="utf-8"))


def to_rgb(css):
    css = css.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3})", css)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"#([0-9a-f]{6})", css)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return None


def dist(a, b):
    # weighted euclidean -- cheap approximation of perceptual distance
    rm = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt((2 + rm / 256) * dr ** 2 + 4 * dg ** 2 + (2 + (255 - rm) / 256) * db ** 2)


def nearest_color(rgb, table):
    best, bestd = None, 1e9
    for var, css in table.items():
        t = to_rgb(css)
        if t is None:
            continue
        d = dist(rgb, t)
        if d < bestd:
            best, bestd = (var, css), d
    return best, bestd


def nearest_num(px, table):
    best, bestd = None, 1e9
    for var, val in table.items():
        d = abs(px - float(val))
        if d < bestd:
            best, bestd = (var, val), d
    return best, bestd


def bucket(d, near):
    return "EXACT" if d < 0.5 else ("NEAR" if d <= near else "NEW")


def report(title, rows, new_only):
    print("\n=== %s ===" % title)
    order = {"EXACT": 0, "NEAR": 1, "NEW": 2}
    rows.sort(key=lambda r: (order[r[0]], -r[1]))
    shown = [r for r in rows if not new_only or r[0] == "NEW"]
    for kind, count, value, tok, d in shown:
        if tok is None:
            print("  %-5s  %-22s  x%-3d  --" % (kind, value, count))
        else:
            print("  %-5s  %-22s  x%-3d  %s  (%s, d=%.1f)"
                  % (kind, value, count, tok[0], tok[1], d))
    tally = collections.Counter(r[0] for r in rows)
    print("  -> %d exact, %d near, %d new  (of %d distinct)"
          % (tally["EXACT"], tally["NEAR"], tally["NEW"], len(rows)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=pathlib.Path)
    ap.add_argument("--new-only", action="store_true")
    args = ap.parse_args()

    tokens = load_tokens()
    colors = dict(tokens["colors"]); colors.update(tokens["swatches"])
    src = args.html.read_text(encoding="utf-8")

    hexes = collections.Counter(
        m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", src)
    )
    rows = []
    for value, count in hexes.items():
        rgb = to_rgb(value)
        if rgb is None:
            continue
        tok, d = nearest_color(rgb, colors)
        rows.append((bucket(d, NEAR_RGB), count, value, tok, d))
    report("colours", rows, args.new_only)

    sizes = collections.Counter(
        float(m) for m in re.findall(r"font-size:\s*([\d.]+)px", src)
    )
    rows = []
    for value, count in sizes.items():
        tok, d = nearest_num(value, tokens["text"])
        rows.append((bucket(d, NEAR_PX), count, "%gpx" % value, tok, d))
    report("font sizes", rows, args.new_only)

    radii = collections.Counter(
        float(m) for m in re.findall(r"border-radius:\s*([\d.]+)px", src)
    )
    rows = []
    for value, count in radii.items():
        tok, d = nearest_num(value, tokens["radii"])
        rows.append((bucket(d, NEAR_PX), count, "%gpx" % value, tok, d))
    report("radii", rows, args.new_only)


if __name__ == "__main__":
    main()
