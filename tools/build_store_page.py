#!/usr/bin/env python3
"""build_store_page.py -- one command, any store, either ordering algorithm, any day.

    python3 build_store_page.py --store rewe_peeters_flueren --algo scenario --page rewe-peeters.html
    python3 build_store_page.py --store edeka_center_stroetmann_coesfeld --algo classic \
            --page ecenter-coesfeld.html --date 2026-08-21

--date defaults to TODAY, resolved fresh from the clock on every run. Never pass a date you
copied from earlier in a conversation: on 2026-08-21 exactly that produced two store pages built
on the previous day's guide, and it was only caught because Avik read a number off his phone.

WHAT IT GUARANTEES
  Bestand and Bestellvorschlag on the page equal what the store's app shows, item for item,
  because both are taken from prod_orders_output unchanged rather than recomputed. The RANGES
  are ours and come from the store's own ordering algorithm.

THE TWO ALGORITHMS
  classic   order = floor(p/cs) + (frac > r),  p = A - stock,  r = co/(co+cu),
            co = purchase_price/shelf_life_llm,  cu = sales_price - 0.7*purchase_price.
            A is NOT reconstructed: A = recommended_order_quantity_before_rounding + the stock
            production itself used. That puts the ladder on production's arithmetic, not on a
            reimplementation, and removes the ~9% reproduction gap a reconstruction carries.
  scenario  no closed form: the stock enters the cost function in three places, so the ladder
            comes from sweeping the stock through the SHIPPED policy and bisecting each step.
            Requires RP_theta6.py and the policy package; this script calls it.
"""
from __future__ import annotations
import argparse, json, math, os, re, subprocess, sys
from datetime import date

PROJECT = "freshflow-prod"

DE_REASON = {
    "multiple_skus_in_a_group": "mehrere Artikel auf einer PLU", "rolling_recount": "turnusmässige Zählung",
    "missing_intake": "Wareneingang fehlt", "not_yet_counted": "noch nie gezählt",
    "not_balanced": "nicht ausgeglichen", "missing_sales": "Abverkauf fehlt", "in_promotion": "Aktion",
    "missing_recent_sales": "zuletzt kein Abverkauf", "new_item": "neuer Artikel",
    "suppressed_warning_due_to_lack_of_history": "zu wenig Historie",
    "item_with_display_size_but_no_data": "keine Daten"}
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# The newer pages carry the date in German, the way the app itself writes it: "Mi., 26. Aug.".
WD_DE = ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."]
MON_DE = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.",
          "Nov.", "Dez."]


class Refusal(Exception):
    """Raised instead of writing a page that could be wrong in front of a store owner."""


def bq(sql: str):
    r = subprocess.run(["bq", f"--project_id={PROJECT}", "query", "--use_legacy_sql=false",
                        "--format=json", "--max_rows=5000", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Refusal("bq failed:\n" + r.stderr[-1500:])
    out = r.stdout.strip()
    i = out.find("[")
    return json.loads(out[i:]) if i >= 0 else []


def F(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def de(x, n=1):
    return ("%.*f" % (n, x)).replace(".", ",")


def note(js):
    try:
        xs = json.loads(js) if isinstance(js, str) else (js or [])
    except Exception:
        xs = []
    out = [DE_REASON.get(str(p).strip(), str(p).strip()) for p in xs if str(p).strip()]
    return " · ".join(out) or None


# --------------------------------------------------------------------- data
def pull(store: str, day: str):
    """Everything the page needs, from the ONLY table that carries the current order day.

    ⛔ core_orders_agreement and global.prod_orders_evaluation_report BOTH lag by a day at these
    stores and read as zero all morning. Checking them for today is the single most expensive
    mistake on this job; it cost a full morning once.
    """
    rows = bq(f"""
      WITH o AS (
        SELECT CAST(item_id AS STRING) iid, CAST(plu_item_id AS STRING) plu,
               `case`.system.quantity cs, display.system.quantity disp,
               simulated_inventory_quantity sim_u, `order`.system.quantity ord_sys,
               CAST(recommended_order_quantity_before_rounding AS FLOAT64) rqb,
               purchase_price ek, sales_price_suggestion vk, shelf_life_llm sl,
               TO_JSON_STRING(needs_attention_reason) ord_r,
               TO_JSON_STRING(inventory_needs_attention_reason) inv_r
        FROM `{PROJECT}.{store}.prod_orders_output`
        WHERE DATE(order_deadline_at,'Europe/Berlin') = DATE '{day}'
          AND display.system.quantity > 0 AND NOT hidden_state.system.is_hidden),
      n AS (
        SELECT CAST(item_id AS STRING) iid, ANY_VALUE(orderset_item_name) nm,
               ANY_VALUE(original_index) oi, ANY_VALUE(CAST(is_organic AS STRING)) bio,
               ANY_VALUE(CAST(is_in_promotion AS STRING)) promo,
               ANY_VALUE(case_content_unit) unit, ANY_VALUE(item_categories) cat
        FROM `{PROJECT}.{store}.core_orderset`
        WHERE DATE(order_deadline_at,'Europe/Berlin') = DATE '{day}' GROUP BY iid)
      SELECT o.*, n.nm, n.oi, n.bio, n.promo, n.unit, n.cat FROM o LEFT JOIN n USING(iid)""")
    if not rows:
        raise Refusal(f"no active order-guide rows for {store} on {day}. The pipeline writes "
                      f"between 05:20 and 07:40; if it is earlier than that, wait, and do NOT "
                      f"fall back to yesterday.")
    return rows


def store_config(store: str):
    r = bq(f"""SELECT JSON_VALUE(data,'$.ordering_policy') pol,
                      JSON_VALUE(data,'$.scenario_ordering_config.theta_default') theta,
                      JSON_VALUE(data,'$.scenario_ordering_config.min_gain_fraction') mg,
                      JSON_VALUE(data,'$.scenario_ordering_config.shelf_life_floor') fl
               FROM `{PROJECT}.firestore_export.store_configs_raw_latest`
               WHERE document_id = '{store}'""")
    return r[0] if r else {}


# --------------------------------------------------------------------- ladders
def classic_ladder(cs, T, rqb, ek, vk, sl):
    cu, co = vk - 0.7 * ek, ek / sl
    if cu + co <= 0:
        return None
    r = co / (co + cu)
    A = rqb + T                       # production's own target, never reconstructed

    def order_at(x):
        p = max(0.0, A - x)
        q = p / cs
        n = math.floor(q)
        return n + (1 if (q - n) > r + 1e-12 else 0)

    qmax = order_at(0.0)
    out = []
    for q in range(qmax, -1, -1):
        lo = max(A - cs * (q + r), 0.0) / cs
        hi = None if q == 0 else (A - cs * (q - 1 + r)) / cs
        out.append((lo, hi, q))
    return out, order_at(T)


def dec(x):
    """One decimal, the signed-off style, unless that would print a real edge as 0,0. A rung can
    open at 0,0121 cases: rounded to one decimal it reads as zero, the rung above it also reads as
    starting at zero, and the two both claim the same piece."""
    for n in (1, 2, 3):
        t = de(x, n)
        if t.strip("0,") or x == 0:
            return t
    return de(x, 3)


def label(lo, hi, cs):
    """Case range, piece range, and the shape. Both edges use ceil so the PIECE ranges stay a
    partition: the last piece of one rung is exactly one below the first of the next.

    ⛔ The shape is decided on the PIECE bound, not on the case bound. Treating any lower edge
    under 0,05 cases as zero put two rungs on piece 0 for 6 of 176 items at Nahkauf
    Heidenoldendorf, one of them printing "egal wie viel · ab 0 St. -> 0 Kisten" directly under
    "0 St. -> 1 Kiste". The piece ranges are what the owner types, so they decide."""
    lo_p = 0 if lo <= 0 else int(math.ceil(lo * cs - 1e-9))
    hi_p = None if hi is None else int(math.ceil(hi * cs - 1e-9)) - 1
    if hi is None:
        kind = "any" if lo_p <= 0 else "atleast"
        expr = "egal wie viel" if lo_p <= 0 else "≥ %s" % dec(lo)
        pcs = "ab 0 St." if lo_p <= 0 else "ab %d St." % lo_p
    elif lo_p <= 0:
        kind, expr = "lessthan", "&lt; %s" % dec(hi)
        pcs = "%d St." % hi_p if hi_p <= 0 else "0 bis %d St." % hi_p
    else:
        kind, expr = "between", "≥ %s &nbsp; &lt; %s" % (dec(lo), dec(hi))
        pcs = "%d St." % lo_p if hi_p <= lo_p else "%d bis %d St." % (lo_p, hi_p)
    return kind, expr, pcs, lo_p, hi_p


def build_items(rows, ladders):
    """ladders: iid -> (list of (lo, hi, q), plan_index_order). Missing iid means no ladder."""
    items, no_ladder = [], []
    for o in rows:
        iid = o["iid"]
        cs, T = F(o["cs"]), F(o["sim_u"])
        ord_sys = F(o["ord_sys"])
        if cs is None or cs <= 0 or T is None:
            no_ladder.append(o.get("nm") or iid)
            continue
        lad = ladders.get(iid)
        rungs = []
        if lad:
            rr, qA = lad
            for lo, hi, q in rr:
                kind, expr, pcs, lo_p, hi_p = label(lo, hi, cs)
                rungs.append(dict(kind=kind, lo=lo, hi=hi, plo=lo_p, phi=hi_p, order=q,
                                  plan=(q == qA), unconf=False, expr=expr, pcs=pcs))
            # ⛔ What the owner sees wins. Pin plan A to the published order and shift the WHOLE
            # ladder by the same step, so one tap still moves exactly one case.
            if ord_sys is not None and int(ord_sys) != qA:
                d = int(ord_sys) - qA
                for x in rungs:
                    x["order"] = max(0, x["order"] + d)
        else:
            no_ladder.append(o.get("nm") or iid)
            rungs = [dict(kind="none", lo=None, hi=None, plo=None, phi=None,
                          order=int(ord_sys) if ord_sys is not None else 0,
                          plan=True, unconf=True, expr="keine Spanne", pcs=None)]
        cat = o.get("cat") or []
        items.append(dict(
            id=0, plu=int(iid), bio=(str(o.get("bio")).lower() == "true"),
            promo=(o.get("nm") if str(o.get("promo")).lower() == "true" else None),
            name=o.get("nm") or iid, case=cs, ek=F(o.get("ek")), vk=F(o.get("vk")),
            # ⛔ NO invented flags. is_inventory_count_mandatory is NOT shown by the app, and
            # using it forced a mandatory number on rows the owner sees as ordinary.
            flags=([] if lad else ["KEINE LEITER"]),
            rungs=rungs, app=round(T / cs, 3),
            invNote=note(o.get("inv_r")), ordNote=note(o.get("ord_r")),
            unit=("kg" if str(o.get("unit", "")).upper() == "KG" else "piece"),
            category=(cat[0] if isinstance(cat, list) and cat else None),
            prevOrder=int(ord_sys) if ord_sys is not None else 0,
            # ⛔ Pull real display size / hidden state, never default them (the pull() query
            # already filters to display>0 AND NOT hidden, so hidden is always False here --
            # but auslage must come from the real value, not a silent 1-for-everyone fallback.
            auslage=F(o.get("disp")), hidden=False,
            _oi=int(F(o.get("oi")) or 10 ** 9)))
    items.sort(key=lambda x: (x["_oi"], x["name"]))
    for i, x in enumerate(items):
        x["id"] = i
        x.pop("_oi")
    return items, no_ladder


# --------------------------------------------------------------------- checks
def self_check(items):
    """Refuse rather than publish. Every one of these fired for real at least once."""
    bad = []
    for x in items:
        pl = [q for q in x["rungs"] if q["plan"]]
        if len(pl) != 1:
            bad.append(f"{x['name']}: {len(pl)} Plan-A-Sprossen")
        if x["rungs"][0]["kind"] != "none":
            if any(r.get("expr") is None for r in x["rungs"]):
                bad.append(f"{x['name']}: Sprosse ohne Text")   # this shipped once, page looked empty
            if any(r.get("plo") is None for r in x["rungs"]):
                bad.append(f"{x['name']}: Sprosse ohne Stückgrenze")
        if pl and int(pl[0]["order"]) != int(x["prevOrder"]):
            bad.append(f"{x['name']}: Plan A {pl[0]['order']} != App {x['prevOrder']}")
        if any(r["order"] is not None and r["order"] < 0 for r in x["rungs"]):
            bad.append(f"{x['name']}: negative Bestellmenge")
        if x["app"] is None:
            bad.append(f"{x['name']}: kein Bestand")
    if bad:
        raise Refusal("%d Prüfung(en) fehlgeschlagen:\n  " % len(bad) + "\n  ".join(bad[:12]))


def inject(page, items, day, store_label=None):
    s = open(page, encoding="utf-8").read()
    m = re.search(r'const ITEMS = (\[.*?\]);\n', s, re.S)
    if not m:
        raise Refusal(f"{page} carries no `const ITEMS = [...]` block. Do not reimplement the "
                      f"page; fix the splice.")
    s = s[:m.start(1)] + json.dumps(items, ensure_ascii=False) + s[m.end(1):]
    y, mo, d = (int(v) for v in day.split("-"))
    wi = date(y, mo, d).weekday()
    # ⛔ Match BOTH labels AND both date spellings. The header was renamed to the app's German
    # ("Ordersatz") once and the date silently stopped updating, so a sheet showed the wrong day in
    # a store. The newer pages then switched the date itself to German and broke it a second time.
    s, n = re.subn(r'(Order Guide|Ordersatz) &nbsp;[A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc]{2,4}\., '
                   r'\d+\. [A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc]{3,5}\.?',
                   lambda mm: '%s &nbsp;%s, %d. %s' % (mm.group(1), WD_DE[wi], d, MON_DE[mo - 1]), s)
    if n == 0:
        s, n = re.subn(r'(Order Guide|Ordersatz) &nbsp;[A-Za-z]{3}, [A-Za-z]{3} \d+',
                       lambda mm: '%s &nbsp;%s, %s %d' % (mm.group(1), WD[wi], MON[mo - 1], d), s)
    if n != 1:
        raise Refusal(f"header date rewritten {n} times, expected exactly 1. The page would show "
                      f"the wrong day.")
    if store_label:
        s = re.sub(r'(<span class="dim">\|\s*&nbsp;)[^<]*(</span>)',
                   lambda mm: mm.group(1) + store_label + mm.group(2), s, count=1)
        s, n_title = re.subn(r'(<title>Freshflow · Bereiche-Bestandsabfrage · )[^<]*(</title>)',
                             lambda mm: mm.group(1) + store_label + mm.group(2), s, count=1)
        if n_title != 1:
            raise Refusal(f"<title> rewritten {n_title} times, expected exactly 1. The browser "
                          f"tab would still show the old store's name.")
    open(page, "w", encoding="utf-8").write(s)


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, help="BigQuery dataset, e.g. rewe_peeters_flueren")
    ap.add_argument("--algo", required=True, choices=["scenario", "classic"])
    ap.add_argument("--page", required=True, help="HTML file carrying a const ITEMS block")
    ap.add_argument("--date", default=None, help="ORDER date; omit for today")
    ap.add_argument("--label", default=None, help="store name for the header")
    ap.add_argument("--items-json", default=None,
                    help="scenario only: RP_items_*.json produced by RP_theta6.py")
    a = ap.parse_args()
    day = a.date or date.today().isoformat()     # resolved FRESH, never carried in
    print(f"Laden {a.store} | Algorithmus {a.algo} | Tag {day}")

    cfg = store_config(a.store)
    pol = (cfg.get("pol") or "").lower()
    print(f"  Store-Dokument: ordering_policy={pol or '?'} theta={cfg.get('theta')} "
          f"min_gain={cfg.get('mg')} shelf_life_floor={cfg.get('fl')}")
    if a.algo == "scenario" and pol != "scenario":
        raise Refusal(f"--algo scenario, but the store document says ordering_policy='{pol}'. "
                      f"The app would run the other rule and every row would be wrong.")
    if a.algo == "classic" and pol == "scenario":
        raise Refusal(f"--algo classic, but the store is flipped to scenario.")

    rows = pull(a.store, day)
    print(f"  aktive Artikel: {len(rows)}")

    ladders = {}
    if a.algo == "classic":
        for o in rows:
            cs, T, rqb = F(o["cs"]), F(o["sim_u"]), F(o["rqb"])
            ek, vk, sl = F(o["ek"]), F(o["vk"]), F(o["sl"])
            if None in (cs, T, rqb, ek, vk, sl) or cs <= 0 or sl <= 0:
                continue
            got = classic_ladder(cs, T, rqb, ek, vk, sl)
            if got:
                ladders[o["iid"]] = got
    else:
        if not a.items_json or not os.path.exists(a.items_json):
            raise Refusal("--algo scenario needs --items-json from RP_theta6.py --date " + day)
        src = {str(x["iid"]): x for x in json.load(open(a.items_json))}
        for o in rows:
            x = src.get(o["iid"])
            if not x or not x.get("ladder"):
                continue
            cs = F(o["cs"])
            rr = [(r["lo"], r["hi"], r["q"]) for r in x["ladder"]]
            qA = next((r["q"] for r in x["ladder"] if r["plan"]), rr[-1][2])
            ladders[o["iid"]] = (rr, qA)

    items, no_lad = build_items(rows, ladders)
    self_check(items)
    inject(a.page, items, day, a.label)
    print(f"  Artikel geschrieben: {len(items)} | ohne Leiter: {len(no_lad)}")
    print(f"  Bestand und Bestellvorschlag == App: {len(items)} von {len(items)}")
    print(f"GESCHRIEBEN {a.page}")


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Refusal as e:
        sys.stderr.write("\nNICHT GESCHRIEBEN\n%s\n" % e)
        sys.exit(2)
