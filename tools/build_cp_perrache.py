#!/usr/bin/env python3
"""Build the C&P Perrache prototype from the current REWE prototype.

Adds what only C&P has: the Prévision (preorder) column after Commande, the
order guide changed marker behind the item name, recalculated markers, and
removed lines. Logic follows freshflowai/mobile main (see MOB-1765):

  * column order Item | Inventory | Order | Preorder
  * a preorder edit never changes the commande
  * netting runs the other way: a commande change moves the preorder reco of
    machine lines (not user-edited, not locked); the user sees only the new
    preorder value plus the recalculated marker
  * locked preorder lines come from the backend, show the lock, are not editable
  * no preorder line -> an em dash
  * footer totals exclude the preorder

Usage:
  python3 tools/build_cp_perrache.py --base rewe-peeters-flueren-2026-08-25.html \
      --items-from intermarche-hyper-dole-2026-09-03.html \
      --out cerise-perrache-2026-10-13.html [--cp-json cp.json]

Without --cp-json the C&P fields are seeded deterministically (dummy data) and
the page is stamped as such. With --cp-json (keyed by item index, same fields
as CP_DEMO below) nothing is invented.
"""
import argparse, json, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('--base', required=True)
ap.add_argument('--items-from', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--cp-json')
ap.add_argument('--hide-purchase-price-and-margin', action='store_true', help="set when the store doc has hide_purchase_price_and_margin = true (Perrache: true)")
ap.add_argument('--ladders-json', help='RP_items json: items whose note starts with "kein Forecast" are no-forecast items')
ap.add_argument('--tiles-from', help='page whose TILES (shelf keywords) to use; default --items-from')
ap.add_argument('--deadline', default=None, help='HH:MM order deadline shown in the header')
ap.add_argument('--cp-lines', help='real lines pulled from prod_orders_output (see cp_lines_*.json)')
ap.add_argument('--demo-og', type=int, default=0, help='add N clearly labelled example lines for the order guide marker (incl. one removed)')
ap.add_argument('--orders', help='orders overview data for the Commandes tab (tools/data/cp_*_orders_*.json)')
ap.add_argument('--opens-at', help='HH:MM: orders cannot be opened before this (C&P: 11:00, MOB-1730); needs --orders')
ap.add_argument('--sales-json', help='past.sales per PLU for the order day (tools/data/cp_<store>_sales_<date>.json): the 7-day strip under the commande')
ap.add_argument('--city', default='Lyon', help='city shown on the dashboard weather card')
ap.add_argument('--order-date', default='2026-10-13', help='YYYY-MM-DD order day: dashboard date and the 30-day chart window')
ap.add_argument('--clock', help='HH:MM the page opens on when no ?now= is given (see cp_orders_overview.py)')
ap.add_argument('--store-name', default='Cerise &amp; Potiron Perrache')
ap.add_argument('--guide-id', default='cerise-perrache-2026-10-13')
args = ap.parse_args()

s = open(args.base, encoding='utf-8').read()
src = open(args.items_from, encoding='utf-8').read()


def rep(a, b, cnt=1):
    global s
    n = s.count(a)
    if n != cnt:
        sys.exit(f'anchor x{n} (want {cnt}): {a[:90]!r}')
    s = s.replace(a, b)


def rep_set(a, b):
    """Like rep(), but a page where build_store_page.py already set the value passes."""
    global s
    if s.count(a) == 0:
        return          # build_store_page.py already set this day's value
    rep(a, b)


def block(text, start, end_pat):
    i = text.index(start)
    j = text.index(end_pat, i) + len(end_pat)
    return i, j


# ---- items + shelves -------------------------------------------------------
m_dst = re.search(r'const ITEMS = \[.*?\];\n', s, re.S)
m_src = re.search(r'const ITEMS = \[.*?\];\n', src, re.S)
s = s[:m_dst.start()] + m_src.group(0) + s[m_dst.end():]
items = json.loads(m_src.group(0)[len('const ITEMS = '):-2])

for name in ('HIST_PROMO', 'HIST_SHRINK', 'HIST'):
    m = re.search(r'const %s = \{.*?\};\n' % name, s, re.S)
    s = s[:m.start()] + 'const %s = {};\n' % name + s[m.end():]
# Sales of the 7 days before the order day, per PLU, from the order line's past.sales (what
# the app shows). HIST keeps the base layout: 14 days from HIST_FROM, [sales, intake]; only the
# last 7 are filled, and the strip runs in the app's 7-day mode (HIST_ITER1).
if args.sales_json:
    from datetime import date as _d0, timedelta as _t0
    _sj = json.load(open(args.sales_json, encoding='utf-8'))
    _from = _d0.fromisoformat(_sj['order_date']) - _t0(days=14)
    _hist = {}
    for plu, byday in _sj['sales'].items():
        sales = [None] * 14
        for d, q in byday.items():
            i = (_d0.fromisoformat(d) - _from).days
            if 0 <= i < 14:
                sales[i] = q
        _hist[plu] = [sales, [None] * 14]
    rep('const HIST = {};\n', 'const HIST = %s;\n' % json.dumps(_hist, separators=(',', ':')))
    m = re.search(r'const HIST_FROM = new Date\(\d+, \d+, \d+\);', s)
    s = s[:m.start()] + 'const HIST_FROM = new Date(%d, %d, %d);' % (_from.year, _from.month - 1, _from.day) + s[m.end():]
    _promo = {plu: sorted((_d0.fromisoformat(d) - _from).days for d in days if 0 <= (_d0.fromisoformat(d) - _from).days < 14)
              for plu, days in (_sj.get('promo') or {}).items()}
    rep('const HIST_PROMO = {};\n', 'const HIST_PROMO = %s;\n' % json.dumps(_promo, separators=(',', ':')))
    rep("const HIST_ITER1 = new URLSearchParams(location.search).get('iter')==='1';",
        "const HIST_ITER1 = true;   /* C&P: the app's 7 days, no swipe to the week before */")

i, j = block(s, 'const TILES = [', '\n];')
tsrc = open(args.tiles_from, encoding='utf-8').read() if args.tiles_from else src
k, l = block(tsrc, 'const TILES = [', '\n];')
s = s[:i] + tsrc[k:l] + s[j:]
# Perrache produce names the Dole keywords miss. First match wins, so the specific
# bagged-salad terms go into the chilled tile and only the head salads into salate-kohl.
EXTRA_KW = {
    'kartoffeln-zwiebeln': ['ail violet', 'ail blanc', 'ail rose'],
    'wurzelgemuese': ['igname', 'manioc'],
    'salate-kohl': ['feuille de chene', 'cresson', 'celeri vert', 'scarole', 'frisee'],
    'fruchtgemuese': ['chayotte', 'christophine'],
    'gekuehltes-gemuese': ['jeune pousse', 'roquette sachet', 'pousse epinard'],
    'bananen-exoten': ['kaki', 'persimon'],
}
for tid, kws in EXTRA_KW.items():
    m = re.search(r"\['%s','[^']*','[^']*',\[" % re.escape(tid), s)
    if not m:
        sys.exit(f'tile {tid} not found')
    s = s[:m.end()] + ''.join(f"'{k}'," for k in kws) + s[m.end():]
if args.deadline:
    for a, b in (('Bestellschluss heute 13:00 Uhr', f'Bestellschluss heute {args.deadline} Uhr'),
                 ('Order deadline today 13:00', f'Order deadline today {args.deadline}'),
                 ('Heure limite aujourd’hui 13:00', f'Heure limite aujourd’hui {args.deadline}')):
        s = s.replace(a, b)

# The REWE base page hides a few rows for its own demo. A clone shows only what the store's app
# shows: hidden comes from hidden_state in the data (build_store_page.py), nothing is inherited.
m = re.search(r'const DEMO_HIDDEN_IDS = new Set\(\[[^\]]*\]\);', s)
if m:
    s = s[:m.start()] + 'const DEMO_HIDDEN_IDS = new Set([]);   /* C&P clone: no demo-hidden rows */' + s[m.end():]

# ---- C&P dashboard: all data in, Lyon weather, French holidays, French tutorials ----
# Missing data: every category up to date, so the header shows the app's success badge
# (green check, no text) and the status sheet no longer opens on its own.
rep("""    { key:'intake',    lbl:()=>t().miCatIntake, level:'err',
      days:[ new Date(MI_TODAY.getTime() - MI_DAY_MS) ] }""",
    """    { key:'intake',    lbl:()=>t().miCatIntake, level:'ok',  days:[] }""")
# Weather: the store's city (--city), 15-20 °C, sunny.
rep('<div class="dash-city">Berlin</div>', f'<div class="dash-city">{args.city}</div>')
i = s.index('<div class="dash-temp">14°C | 23°C'); j = s.index('</div>', i) + len('</div>')
s = s[:i] + ('<div class="dash-temp">15°C | 20°C\n'
             '          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#E8A33D" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>\n'
             '        </div>') + s[j:]
rep('<span class="dash-rainpill">Regen</span>',
    '<span class="dash-rainpill" style="background:#FDF1DC;color:#9A6512">Ensoleillé</span>')
# Upcoming French public holidays after the order day (October 2026).
rep('<div class="dash-evrow"><div class="nm">Tag der Deutschen Einheit</div><div class="dt">Okt. 03<br>2026</div></div>',
    '<div class="dash-evrow"><div class="nm">Toussaint</div><div class="dt">nov. 01<br>2026</div></div>')
rep('<div class="dash-evrow"><div class="nm">Allerheiligen</div><div class="dt">Nov. 01<br>2026</div></div>',
    '<div class="dash-evrow"><div class="nm">Armistice 1918</div><div class="dt">nov. 11<br>2026</div></div>')
# Tutorials: the French versions of the standard set (no C&P-specific videos exist yet).
rep('</span>Einführung in die Bestellvorbereitungen</div>', "</span>Présentation de l'application</div>")
rep('</span>Wie kann man Elemente ausblenden?</div>', '</span>Vérification de la commande</div>')

# ---- C&P dashboard in French (the store's language), on the order day's window ------
# The charts cover the 30 days up to the order day (the REWE demo had 26 Jul - 25 Aug).
from datetime import date as _date, timedelta as _td
_od = _date.fromisoformat(args.order_date)
_MON_FR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']
_WD_FR = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim']
_fr = lambda d: f'{d.day} {_MON_FR[d.month - 1]}'
_start = _od - _td(days=29)
m = re.search(r'(<span id="dbOverview">[^<]*</span> <span class="dt">)[^<]*(</span>)', s)
s = s[:m.start()] + m.group(1) + f'{_fr(_od)} {_od.year}' + m.group(2) + s[m.end():]
for a, b, n in (('Juli 26 - Aug. 25', f'{_fr(_start)} - {_fr(_od)}', 4),
                ('<span class="nm">Umsatz</span>', '<span class="nm">Chiffre d\'affaires</span>', 1),
                ('<span class="nm">Abschriften im Verkaufspreis</span>', '<span class="nm">Casse en prix de vente</span>', 1),
                ('*Vor 52 Wochen', '*Il y a 52 semaines', 2)):
    rep(a, b, n)
for k, old in enumerate(('>26 So<', '>30 Do<', '>3 Mo<', '>7 Fr<', '>11 Di<', '>15 Sa<', '>19 Mi<', '>23 So<')):
    d = _start + _td(days=4 * k)
    rep(old, f'>{d.day} {_WD_FR[d.weekday()]}<', 2)

# The REWE base page still counts extra shelves (placedOn) on the "change shelf" pill in
# "Gérer la commande", but the second-shelf feature and that variable were removed on
# 16 Sep (f782b96). The pill then throws and the manage view never draws. C&P has one shelf.
s = s.replace("${tileLabel(tileOf(it))}${placedOn.length?' +'+placedOn.length:''} \u270e</button>`;",
              "${tileLabel(tileOf(it))} \u270e</button>`;")

# The "change shelf" sheet has its subtitle hard-coded in German in the base page.
rep('<div class="sub">Gilt ab sofort dauerhaft für diesen Artikel.</div>', '<div class="sub">${L.shelfPermanent}</div>')
for _lg, _txt in (('de', 'Gilt ab sofort dauerhaft für diesen Artikel.'), ('en', 'Applies from now on to this item.'),
                  ('fr', "S'applique dès maintenant à cet article.")):
    _a = {'de': "    rManualWarning:'Manuelle Warnung',", 'en': "    rManualWarning:'Manual warning',",
          'fr': "    rManualWarning:'Alerte manuelle',"}[_lg]
    rep(_a, _a + "\n    shelfPermanent:" + json.dumps(_txt, ensure_ascii=False) + ",")

# ---- store identity --------------------------------------------------------
rep('<title>Freshflow · Bereiche-Bestandsabfrage · REWE Peeters Flüren</title>', '<title>Freshflow · Bereiche-Bestandsabfrage · ' + args.store_name.replace('&amp;', '&') + '</title>')
rep('REWE Peeters Flüren', args.store_name, 3)
rep("const GUIDE_ID = 'rewe-peeters-flueren-2026-08-25';", f"const GUIDE_ID = '{args.guide_id}';")
rep_set("let LANG='de';", "let LANG='fr';")
rep_set("const MI_TODAY = new Date(2026, 7, 25);", "const MI_TODAY = new Date(2026, 9, 13);")
for a, b in (("hdrOrderDate:'Di., 25. Aug.'", "hdrOrderDate:'Di., 13. Okt.'"),
             ("hdrOrderDate:'Tue, 25 Aug'", "hdrOrderDate:'Tue, 13 Oct'"),
             ("hdrOrderDate:'mar. 25 août'", "hdrOrderDate:'mar. 13 oct.'"),
             ("hdrPrevDate:'Mo., 24. Aug.'", "hdrPrevDate:'Mo., 12. Okt.'"),
             ("hdrPrevDate:'Mon, 24 Aug'", "hdrPrevDate:'Mon, 12 Oct'"),
             ("hdrPrevDate:'lun. 24 août'", "hdrPrevDate:'lun. 12 oct.'")):
    rep_set(a, b)
rep("(new URLSearchParams(location.search).get('retailer') || 'rewe')",
    "(new URLSearchParams(location.search).get('retailer') || 'cp')")

# ---- locale keys (same keys in all three, parity) --------------------------
LOC = {
    'de': dict(hdrPre='Vorbestellung', preOrdered='Vorbestellt', preLabel='Vorbestellung',
               tipRecTitle='Neu berechnet', tipRecText='Dieser Bestellvorschlag wurde neu berechnet.',
               tipRecFirst='Zuerst', tipRecNow='Jetzt',
               tipOgTitle='Ordersatz geändert', ogCase='Kistengröße geändert', ogPromo='Aktionsdaten geändert',
               ogPrice='Verkaufspreis geändert', ogAdded='Heute zum Ordersatz hinzugefügt',
               ogRemoved='Aus dem Ordersatz entfernt',
               tipLockTitle='Gesperrt', tipLockText='Dieses Feld kann nicht bearbeitet werden.',
               cpDummy='Demodaten · noch nicht Perrache', cpDemo='Beispiel', labelNew='Neu'),
    'en': dict(hdrPre='Preorder', preOrdered='Pre-ordered', preLabel='Preorder',
               tipRecTitle='Recalculated', tipRecText='This order recommendation was recalculated.',
               tipRecFirst='First', tipRecNow='Now',
               tipOgTitle='Order guide changed', ogCase='Case size changed', ogPromo='Promo dates changed',
               ogPrice='Sales price changed', ogAdded="Added to today's order guide",
               ogRemoved='Removed from order guide',
               tipLockTitle='Locked', tipLockText='This field cannot be edited.',
               cpDummy='Demo data · not Perrache yet', cpDemo='Example', labelNew='New'),
    'fr': dict(hdrPre='Prévision', preOrdered='Prévision', preLabel='Pré-commande',
               tipRecTitle='Recalculé', tipRecText='Cette recommandation de commande a été recalculée.',
               tipRecFirst='Initial', tipRecNow='Maintenant',
               tipOgTitle='Guide de commande modifié', ogCase='Colisage modifié', ogPromo='Dates de promo modifiées',
               ogPrice='Prix de vente modifié', ogAdded='Ajouté au guide de commande du jour',
               ogRemoved='Retiré du guide de commande',
               tipLockTitle='Verrouillé', tipLockText='Ce champ ne peut pas être modifié.',
               cpDummy='Données fictives · pas encore Perrache', cpDemo='Exemple', labelNew='Nouveau'),
}
ANCH = {'de': "    rManualWarning:'Manuelle Warnung',",
        'en': "    rManualWarning:'Manual warning',",
        'fr': "    rManualWarning:'Alerte manuelle',"}
for lg, kv in LOC.items():
    add = ''.join(f"\n    {k}:{json.dumps(v, ensure_ascii=False)}," for k, v in kv.items())
    rep(ANCH[lg], ANCH[lg] + add)

# ---- C&P data --------------------------------------------------------------
if args.cp_json:
    cp = json.load(open(args.cp_json, encoding='utf-8'))
    dummy = False
elif args.cp_lines:
    dummy = False
    src_lines = json.load(open(args.cp_lines, encoding='utf-8'))
    by_name = {l['name'].strip().upper(): l for l in src_lines['lines']}
    by_id = {l['id']: l for l in src_lines['lines']}
    cp, unmatched = {}, []
    for ix, it in enumerate(items):
        l = by_id.get(it.get('plu')) or by_name.get(it['name'].strip().upper())
        if not l:
            unmatched.append(it['name']); continue
        d = {'itemId': l['id']}
        if l.get('pre') is not None:
            d['pre'] = {'sys': l['pre'], 'locked': bool(l.get('preLocked'))}
        if l.get('preY') is not None:
            d['preOrdered'] = l['preY']          # the app shows the tag at 0 too
        if l.get('ordLocked'):
            d['ordLocked'] = True
        labs = [k for k, ids in src_lines.get('labels', {}).items() if l['id'] in ids and k != 'core_assortment']
        if labs:
            d['labels'] = labs
        cp[str(ix)] = d
    if args.ladders_json:
        nofc = {str(x['iid']) for x in json.load(open(args.ladders_json, encoding='utf-8'))
                if (x.get('note') or '').startswith('kein Forecast')}
        for d in cp.values():
            if str(d.get('itemId')) in nofc:
                d['noForecast'] = True
    if unmatched:
        sys.exit(f'{len(unmatched)} page items without a real line: {unmatched[:8]}')
    if len(cp) != len(src_lines['lines']):
        print(f'warning: {len(src_lines["lines"])} real lines, {len(cp)} on the page')
    # labelled examples for the order guide marker -- Perrache had no change during the day
    if args.demo_og:
        pool = [ix for ix in range(len(items)) if 'ordLocked' not in cp[str(ix)]]
        kinds = [['price'], ['case', 'price'], ['promo'], ['added'], ['removed']]
        step = max(1, len(pool) // (args.demo_og + 1))
        for n in range(args.demo_og):
            ix = pool[(n + 1) * step]
            cp[str(ix)]['og'] = kinds[n % len(kinds)]
            cp[str(ix)]['demo'] = True
else:
    dummy = True
    cp = {}
    for ix, it in enumerate(items):
        plan = next((r for r in it['rungs'] if r.get('plan')), it['rungs'][0]) if it['rungs'] else {}
        d = {}
        if ix % 10 < 7:
            d['pre'] = {'sys': (ix * 7) % 3, 'locked': ix % 13 == 0}
        if ix % 6 == 0:
            d['preOrdered'] = 1 + ix % 2
        if ix % 9 == 4:
            d['preLabel'] = {'date': '16.10', 'qty': 2}
        if ix % 11 == 3:
            d['recFirst'] = (plan.get('order') or 0) + 1
        if ix % 17 == 2:
            d['og'] = ['price']
        elif ix % 17 == 5:
            d['og'] = ['case', 'price']
        elif ix % 23 == 7:
            d['og'] = ['added']
        if ix % 41 == 9:
            d['og'] = ['removed']
        if d:
            cp[str(ix)] = d

# The counting self-test assumes its row has no order warning; on real C&P data the first
# range row may carry one, and then "counted = done" is rightly false. Pick a row without.
rep("const ixQ=ITEMS.findIndex((it,ix)=>ST[ix].home==='range' && it.rungs.length>1);",
    "const ixQ=ITEMS.findIndex((it,ix)=>ST[ix].home==='range' && it.rungs.length>1 && !it.ordNote);")

# ---- store settings the app reads (Perrache: hide_purchase_price_and_margin = true) ----
ap_hide = args.hide_purchase_price_and_margin   # copy the store doc's hide_purchase_price_and_margin
if ap_hide:
    rep("      + `<span class=\"metarow\">${it.ek!=null?eur(it.ek):'?'}`\n"
        "      + `${marginPct!=null?' '+marginPct.toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' %':''}`\n"
        "      + ` ${it.vk!=null?eur(it.vk):'?'}</span>`;",
        "      + `<span class=\"metarow\">${it.vk!=null?eur(it.vk):'?'}</span>`;   /* hide_purchase_price_and_margin: retail price only */")
    rep("          ${it.ek!=null?col(eur(it.ek), L.sdPurchase):''}\n"
        "          ${margin!=null?col(margin.toLocaleString(dateLoc(),{minimumFractionDigits:2,maximumFractionDigits:2})+'%', L.sdMargin):''}\n",
        "")
    rep('    <div class="m"><span id="lblEk">EK</span><b id="fcost">0,00 €</b></div>\n',
        '    <div class="m" hidden><span id="lblEk">EK</span><b id="fcost">0,00 €</b></div>\n')
    rep('    <div class="m"><span id="lblMargin">Spanne</span><b id="fmar">0,00 %</b></div>\n',
        '    <div class="m" hidden><span id="lblMargin">Spanne</span><b id="fmar">0,00 %</b></div>\n')
# core tag only where the data carries a core_assortment label (Perrache: none)
core_ids = []
if args.cp_lines:
    core = set(src_lines.get('labels', {}).get('core_assortment', []))
    core_ids = [ix for ix, d in cp.items() if d.get('itemId') in core]
# The app draws a promotion pill only from a 'promotion' label with dates; the order guide's
# is_in_promotion alone does not make one. No such label in the data -> no promo pill.
if args.cp_lines and not src_lines.get('labels', {}).get('promotion'):
    rep("    if(pl) pills+=`<span class=\"pill promo\">${pl}</span>`;",
        "    if(true){ /* no 'promotion' label at this store: the app shows no promo pill (an in_promotion\n       reason is a needs-attention reason and stays in the ? tooltip) */ }")
if not core_ids:
    # no core items at this store: no core filter either (it would read "Base 0")
    rep("        + chk('kern',`<span class=\"pill kern\">${L.kernTag}</span>`,count(it=>it.kern))",
        "        + (ITEMS.some(it=>it.kern) ? chk('kern',`<span class=\"pill kern\">${L.kernTag}</span>`,count(it=>it.kern)) : '')")
m = re.search(r'const KERN_IDS = new Set\(\[[^\]]*\]\);', s)
s = s[:m.start()] + 'const KERN_IDS = new Set([%s]);' % ','.join(core_ids) + s[m.end():]

# ---- CSS -------------------------------------------------------------------
CSS = r"""
/* ===== C&P: Prévision column (Item | Inventory | Order | Preorder, as in the app) ===== */
body.hasPre .colh, body.hasPre #list > .row{
  grid-template-columns:minmax(0, 1fr)
    minmax(var(--inv-cell-min), calc(var(--pvt-col-1) * 100%))
    minmax(var(--ord-cell-min), calc(var(--pvt-col-2) * 100%))
    minmax(var(--ord-cell-min), calc(var(--pvt-col-2) * 100%));}
body.hasPre.seqEdit #list > .row, body.hasPre.seqEdit #colh{
  grid-template-columns:minmax(0, 1fr)
    minmax(var(--inv-cell-min), calc(var(--pvt-col-1) * 100%))
    minmax(var(--ord-cell-min), calc(var(--pvt-col-2) * 100%))
    minmax(var(--ord-cell-min), calc(var(--pvt-col-2) * 100%)) 52px}
.row > *:nth-child(4) .statusSlot{flex:0 0 auto;width:24px;display:flex;align-items:center;justify-content:center}
.statusSlot.stack{flex-direction:column;gap:4px}
.statusSlot.stack .whyBtn{width:44px;height:26px;margin:0 -10px}
.preDash{display:flex;align-items:center;justify-content:center;height:48px;width:72px;margin-left:42px;
  color:var(--ff-grey-800);font-weight:var(--ff-weight-medium);font-size:var(--ff-text-primary-body-text-14)}
.ColumnCounterField--locked .ColumnCounterField__box{background:var(--ff-grey-100);color:var(--ff-grey-500)}
.withbang.hasLineTag{position:relative}
#list > .row:has(.lineTag){padding-top:28px}
.lineTag{position:absolute;left:0;right:24px;bottom:100%;margin-bottom:3px;text-align:center;white-space:nowrap;line-height:1.2;
  font-size:var(--ff-text-primary-body-text-14);color:var(--ff-grey-500);font-weight:var(--ff-weight-regular, 400)}
.lineTag b{font-weight:var(--ff-weight-medium);color:var(--ff-grey-600);margin-left:6px}
.preLabelTag{display:inline-block;padding:1px 8px;border-radius:var(--ff-radius-c15);border:1px solid #FF8502;color:#FF8502;
  font-size:var(--ff-text-primary-caption-12);font-weight:var(--ff-weight-semibold)}
.nm .nmTxt{display:inline}
.nm .ogBtn{display:inline-grid;vertical-align:middle;margin:-12px -8px -10px -4px}
.row.cpRemoved{background:#FAFBFA}
.row.cpRemoved > div:not(.itemcell), .row.cpRemoved .itemtext .meta, .row.cpRemoved .itemtext .pills{opacity:.45;pointer-events:none}
.row.cpRemoved .nm > span.nmTxt{opacity:.45}
.demoTag{display:inline-block;padding:1px 8px;border-radius:var(--ff-radius-c15);border:1px dashed #1F7A80;color:#1F7A80;font-size:var(--ff-text-primary-caption-12);font-weight:var(--ff-weight-semibold)}
.cpDummy{position:fixed;left:12px;bottom:84px;z-index:50;background:#FFF4D6;color:#7A5A00;border:1px solid #F0C64A;
  border-radius:999px;padding:4px 12px;font-size:12px;font-weight:700;pointer-events:none}
"""
CSS_NOSCAN = """
/* ===== C&P: no scanning ===== */
#scanFab, #scanCam, #scanRes, #bsCam, #invRev, #catScanBtn, .backBand, #panelInv,
.dash-navitem:has(#dbNav3){display:none !important}
"""
CSS += CSS_NOSCAN
rep('</style>', CSS + '</style>', 1) if s.count('</style>') == 1 else None
if s.count('</style>') != 1:
    idx = s.index('</style>')
    s = s[:idx] + CSS + s[idx:]

# ---- header column ---------------------------------------------------------
hdr_old = '</svg></span></div><div></div></div>'
i = s.index('<div class="colh" id="colh">')
j = s.index(hdr_old, i)
s = s[:j] + '</svg></span></div><div><span id="hdrPre">Prévision</span></div><div></div></div>' + s[j + len(hdr_old):]

# ---- JS --------------------------------------------------------------------
JS = r"""
/* ===== C&P layer (MOB-1765 + preorder as built in the app) ===== */
const CP = __CP__;
const CP_DUMMY = __DUMMY__;
const cpOf = ix => CP[String(ix)] || {};
const cpRemoved = ix => (cpOf(ix).og||[]).includes('removed');
document.body.classList.add('hasPre');
const ICON_REC='<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="12" fill="#FFDD33"/><g transform="translate(4 4) scale(.6667)" stroke="#2B2300" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18.34 14.96A7 7 0 1 1 16.95 7.05"/><path d="M19.5 9.6L14.8 9.2L19.1 4.9Z" fill="#2B2300" stroke-width="1"/></g></svg>';
const ICON_OG='<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="12" fill="#1F7A80"/><g transform="translate(4 4) scale(.6667)" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 3.5h7.5l4 4v12.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5z" fill="#fff" stroke="#fff" stroke-width="1.6"/><path d="M14 3.5V7.5h4" stroke="#1F7A80" stroke-width="1.6"/><path d="M9 12.2h6" stroke="#1F7A80" stroke-width="2"/><path d="M9 15.8h6" stroke="#1F7A80" stroke-width="2"/></g></svg>';
const ICON_LOCKED='<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="11.1" fill="#fff" stroke="#5B7FB2" stroke-width="1.75"/><g transform="translate(4 4) scale(.6667)" stroke="#5B7FB2" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="11" width="12" height="9" rx="1" fill="#5B7FB2"/><path d="M9 11V8.5a3 3 0 0 1 6 0V11"/></g></svg>';
Object.assign(TIP_ICON,{rec:()=>ICON_REC, prerec:()=>ICON_REC, og:()=>ICON_OG, lock:()=>ICON_LOCKED, preedit:()=>ICON_EDITED});

/* Planned commande of the line without any user action -- the base the netting compares against. */
function cpBaseOrder(ix){ const it=ITEMS[ix], s=ST[ix]; return it.rungs[s.plan].order??0; }
/* Netting, commande -> Prévision only (preorder_reference_inventory_sync): more cases on the
   commande now means fewer needed on the later delivery. Machine lines only. */
function preApp(ix){
  const p=cpOf(ix).pre; if(!p) return null;
  if(p.locked) return p.sys;
  /* what actually gets ordered, not a pending (unconfirmed) value */
  return Math.max(0, p.sys - (ordCommitted(ix) - cpBaseOrder(ix)));
}
function preShown(ix){ const s=ST[ix]; return s.preUser!=null ? s.preUser : preApp(ix); }
function preRecalc(ix){ const p=cpOf(ix).pre; return !!p && !p.locked && ST[ix].preUser==null && preApp(ix)!==p.sys; }
function ordRecalc(ix){ const f=cpOf(ix).recFirst; return f!=null && !ST[ix].manual && f!==orderVal(ix); }
function ogOn(ix){ const og=cpOf(ix).og; return !!(og&&og.length) && (cpRemoved(ix) || !ST[ix].manual); }

function cpSlot(btns){
  if(!btns.length) return '<span class="statusSlot"></span>';
  return `<span class="statusSlot${btns.length>1?' stack':''}">${btns.slice(0,2).join('')}</span>`;
}
function cpBtn(kind,ix,label){
  return `<button type="button" class="whyBtn" data-a="why" data-i="${ix}" data-kind="${kind}" aria-label="${label}">${TIP_ICON[kind]()}</button>`;
}
function preCellHTML(ix){
  const p=cpOf(ix).pre, L=t();
  if(cpRemoved(ix)) return `<div class="withbang"><div class="ColumnCounterField ColumnCounterField--locked"><button class="ColumnCounterField__button" disabled>${ICON_MINUS}</button><div class="ColumnCounterField__box"><span class="ColumnCounterField__value"><b>0</b><i>${L.caseUnit}</i></span></div><button class="ColumnCounterField__button" disabled>${ICON_PLUS}</button></div><span class="statusSlot"></span></div>`;
  if(!p) return `<div class="preDash">—</div>`;
  const v=preShown(ix), locked=!!p.locked, s=ST[ix];
  const icons=[];
  if(locked) icons.push(cpBtn('lock',ix,L.tipLockTitle));
  if(preRecalc(ix)) icons.push(cpBtn('prerec',ix,L.tipRecTitle));
  if(!locked && s.preUser!=null && s.preUser!==preApp(ix)) icons.push(cpBtn('preedit',ix,L.tipEditTitle));
  const it=ITEMS[ix];
  return `<div class="withbang"><div class="ColumnCounterField${locked?' ColumnCounterField--locked':''}">
      <button class="ColumnCounterField__button" data-a="predec" data-i="${ix}"${locked||v<=0?' disabled':''} aria-label="${L.less}">${ICON_MINUS}</button>
      <div class="ColumnCounterField__box"><span class="ColumnCounterField__value"><b>${v}</b><i>${L.caseUnit}</i></span>
        ${it.case!=null?`<span class="ColumnCounterField__label">${Math.round(v*it.case)} ${uw(it)}</span>`:''}</div>
      <button class="ColumnCounterField__button" data-a="preinc" data-i="${ix}"${locked?' disabled':''} aria-label="${L.more}">${ICON_PLUS}</button>
    </div>${cpSlot(icons)}</div>`;
}

/* Hook into the row: OG marker behind the name, recalculated + stacking on the commande,
   the Pre-ordered line tag above the commande, the Pré-commande label in the pills, the
   Prévision cell as the fourth column, removed lines greyed and locked. */
const _rowHTML_cp = rowHTML;
rowHTML = function(ix, ...rest){
  let h = _rowHTML_cp(ix, ...rest);
  if(h.indexOf('class="row row--back')>=0) return h;
  const L=t(), c=cpOf(ix);
  // name + OG marker
  h = h.replace(/<div class="nm">([\s\S]*?)<\/div>/, (m,nm)=>`<div class="nm"><span class="nmTxt">${nm}</span>${ogOn(ix)?cpBtn('og',ix,L.tipOgTitle).replace('class="whyBtn"','class="whyBtn ogBtn"'):''}</div>`);
  if(cpRemoved(ix)) h = h.replace('<div class="row', '<div class="row cpRemoved');
  // Pré-commande label
  /* order item labels as the app draws them: grey outlined pills. 'new' is translated,
     anything without a string (on_sale) is the type in title case, as _simpleText does. */
  if(c.labels) h = h.replace('<div class="pills">', `<div class="pills">${c.labels.map(k=>`<span class="pill">${k==='new'?L.labelNew:k.split('_').map(w=>w[0].toUpperCase()+w.slice(1)).join(' ')}</span>`).join(' ')} `);
  if(c.demo) h = h.replace('<div class="pills">', `<div class="pills"><span class="demoTag">${L.cpDemo}</span> `);
  if(c.preLabel) h = h.replace('<div class="pills">', `<div class="pills"><span class="preLabelTag">${L.preLabel}: ${c.preLabel.date}, ${c.preLabel.qty} ${L.caseUnit}</span> `);
  return h;
};
/* The commande status slot and the Prévision cell are rebuilt after render(), from the
   DOM the base row produced -- the base keeps owning everything else. */
function cpDecorate(){
  document.querySelectorAll('#list > .row[data-ix]').forEach(row=>{
    const ix=+row.dataset.ix, s=ST[ix], it=ITEMS[ix], L=t();
    const cells=row.children;
    if(!cells[2] || row.querySelector('.cpPre')) return;
    // locked commande: the inventory cell does not claim "no count needed"
    if(cpOf(ix).ordLocked){ const n=cells[1].querySelector('.InventoryCounterField__note'); if(n) n.textContent='–';
      const sl=cells[1].querySelector('.statusSlot'); if(sl) sl.innerHTML=''; }
    // removed: no ! / ? / info in the inventory cell -- the user cannot act on the line
    if(cpRemoved(ix)){ const sl=cells[1].querySelector('.statusSlot'); if(sl) sl.innerHTML=''; }
    // commande: removed -> 0 and nothing else
    const ordWrap=cells[2].querySelector('.withbang');
    if(ordWrap){
      const slot=ordWrap.querySelector(':scope > .statusSlot');
      const btns=[];
      if(!cpRemoved(ix)){
        const own=slot && slot.querySelector('button');
        const ownKind=own && own.dataset.kind;
        if(ownKind==='ord') btns.push(own.outerHTML);
        if(ordRecalc(ix)) btns.push(cpBtn('rec',ix,L.tipRecTitle));
        if(ownKind==='edit') btns.push(own.outerHTML);
      }
      if(slot) slot.outerHTML=cpSlot(btns);
      if(cpRemoved(ix)){ const b=cells[2].querySelector('.ColumnCounterField__value b'); if(b) b.textContent='0'; }
      if(cpOf(ix).ordLocked){
        const f=cells[2].querySelector('.ColumnCounterField');
        if(f){ f.classList.add('ColumnCounterField--locked'); f.querySelectorAll('button').forEach(x=>{x.disabled=true; x.removeAttribute('data-a');});
          const bx=f.querySelector('.ColumnCounterField__box'); if(bx){ bx.removeAttribute('data-a'); bx.innerHTML=`<span class="ColumnCounterField__value"><b>–</b></span>`; } }
        const sl=ordWrap.querySelector(':scope > .statusSlot'); if(sl) sl.outerHTML=cpSlot([cpBtn('lock',ix,L.tipLockTitle)]);
      }
      const cc=cpOf(ix);
      if(cc.preOrdered!=null && !cpRemoved(ix)) { ordWrap.classList.add('hasLineTag'); ordWrap.insertAdjacentHTML('afterbegin', `<div class="lineTag">${L.preOrdered}<b>${cc.preOrdered} ${L.caseUnit}</b></div>`); };
    }
    const pre=document.createElement('div'); pre.className='cpPre'; pre.innerHTML=preCellHTML(ix);
    cells[2].after(pre);
  });
  const hp=document.getElementById('hdrPre'); if(hp) hp.textContent=t().hdrPre;
}
/* "No count needed": no-forecast items say so and always carry the order warning; locked lines
   never say it -- the lock is the reason, shown on the commande (Lars, MOB-1602, 12 Oct). */
infoIsNoForecast = function(ix){ return ST[ix].mode==='noladder' || !!cpOf(ix).noForecast; };
ITEMS.forEach((it,ix)=>{ if(cpOf(ix).noForecast && !cpOf(ix).ordLocked && !(it.ordNote||'').includes('kein Forecast'))
  it.ordNote = it.ordNote ? it.ordNote+' · kein Forecast' : 'kein Forecast'; });
/* Removed lines go to the bottom of the list (MOB-1765 section 7, to be confirmed). */
const _sortIdx_cp = sortIdx;
sortIdx = function(list){ const r=_sortIdx_cp(list); return r.filter(ix=>!cpRemoved(ix)).concat(r.filter(cpRemoved)); };
const _render_cp = render;
render = function(...a){ const r=_render_cp(...a); cpDecorate(); return r; };
const _orderVal_cp = orderVal;
orderVal = function(ix){ return (cpRemoved(ix) || cpOf(ix).ordLocked) ? 0 : _orderVal_cp(ix); };

/* Tooltip content for the C&P kinds; the base openWhy keeps inv/ord/edit/info. */
const _openWhy_cp = openWhy;
openWhy = function(btn, ix, kind){
  const L=t();
  if(!['rec','prerec','og','lock','preedit'].includes(kind)) return _openWhy_cp(btn, ix, kind);
  closeWhy();
  let title, text='', box='';
  if(kind==='rec'||kind==='prerec'){
    title=L.tipRecTitle; text=L.tipRecText;
    const first = kind==='rec' ? cpOf(ix).recFirst : cpOf(ix).pre.sys;
    const now = kind==='rec' ? orderVal(ix) : preShown(ix);
    box=`<div class="whyRow"><span>${L.tipRecFirst} <s>${first} ${L.caseUnit}</s> → ${L.tipRecNow} <b>${now} ${L.caseUnit}</b></span></div>`;
  } else if(kind==='og'){
    title=L.tipOgTitle;
    const og=cpOf(ix).og, order=['added','removed','case','promo','price'];
    const lines=order.filter(k=>og.includes(k)).map(k=>({added:L.ogAdded,removed:L.ogRemoved,case:L.ogCase,promo:L.ogPromo,price:L.ogPrice}[k]));
    box=lines.length===1 ? `<div class="whyRow"><span>${lines[0]}</span></div>` : lines.map(x=>`<div class="whyRow"><span>• ${x}</span></div>`).join('');
  } else if(kind==='lock'){ title=L.tipLockTitle; text=L.tipLockText; }
  else { title=L.tipEditTitle; text=L.tipEditText; }
  const p=document.createElement('div'); p.className='whyPop';
  p.innerHTML=`<div class="whyHd">${TIP_ICON[kind]()}<b>${title}</b></div>`+(text?`<div class="whyTx">${text}</div>`:'')+(box?`<div class="whyBox">${box}</div>`:'');
  document.body.appendChild(p);
  const r=btn.getBoundingClientRect(), pw=p.offsetWidth, ph=p.offsetHeight, GAP=8, M=10;
  let top=r.bottom+GAP, cls='below';
  if(top+ph > window.innerHeight-M && r.top-GAP-ph > M){ top=r.top-GAP-ph; cls='above'; }
  const cx=r.left+r.width/2, left=Math.max(M, Math.min(cx-pw/2, window.innerWidth-pw-M));
  p.style.top=top+'px'; p.style.left=left+'px';
  p.style.setProperty('--arrow', Math.max(10, Math.min(cx-left-6, pw-22))+'px');
  p.classList.add(cls); WHY_POP=p;
};
/* Prévision -/+ : writes the user layer of the preorder line only. */
document.addEventListener('click', e=>{
  const b=e.target.closest('[data-a="predec"],[data-a="preinc"]'); if(!b) return;
  e.stopPropagation();
  const ix=+b.dataset.i, s=ST[ix];
  const v=preShown(ix) + (b.dataset.a==='preinc'?1:-1);
  s.preUser=Math.max(0,v);
  if(s.preUser===preApp(ix)) s.preUser=null;
  render();
}, true);
if(CP_DUMMY){ const d=document.createElement('div'); d.className='cpDummy'; d.textContent=t().cpDummy; document.body.appendChild(d); }
render();
"""

# The page's ?selftest=1 is the back-storage scan test; C&P has no scanning, so it is skipped.
rep("if(/[?&]selftest=1/.test(location.search)) setTimeout(bsSelfTest, 0);",
    "if(/[?&]selftest=1/.test(location.search)) console.log('C&P: no scanning on this page, the scan self-test is skipped');")

# ---- C&P: no scanning ---------------------------------------------------------
# C&P has neither the back-storage scan (Bestand tab, "Lager scannen" band on the shelves,
# Fläche bestätigen) nor the barcode scan. Every way in is removed; the scan code stays
# in the page unused (the page's ?selftest=1 still exercises it).
# The inventory keypad's typed Lager / Fläche split is not a scan and stays.
JS += r"""
/* ===== C&P: no scanning ===== */
backBandHTML = function(){ return ''; };
openScanCam = function(){};
bsOpen = function(){};
bsOpenFromShelves = function(){};
(function(){
  const nav=document.getElementById('dbNav3'); if(nav && nav.closest('.dash-navitem')) nav.closest('.dash-navitem').style.display='none';
  ['scanFab','invFab'].forEach(id=>{ const el=document.getElementById(id); if(el) el.remove(); });
})();
"""
JS += r"""
/* ===== C&P: running total since Tuesday, under the 7-day sales =====
   The week starts on Tuesday. Wednesday shows Tuesday, Thursday Tuesday+Wednesday, ...
   Monday Tuesday..Sunday; on Tuesday the full previous week (Tuesday..Monday).
   Same unit as the strip (cases where the item has a case size). */
const CP_WTD = {
  de:{sum:'Summe', week:'Vorwoche'}, en:{sum:'Total', week:'Last week'}, fr:{sum:'Cumul', week:'Semaine préc.'}};
function cpWtd(ix){
  const it=ITEMS[ix];
  const today=histDay(14), k=((today.getDay()-2+7)%7)||7;      // days since Tuesday, 7 on a Tuesday
  const S=sdSeries(it).sales; let sum=0, any=false;
  for(let d=14-k; d<14; d++){ if(S[d]!=null){ sum+=S[d]; any=true; } }
  const W=CP_WTD[LANG]||CP_WTD.en;
  const wd=d=>histDay(d).toLocaleDateString(dateLoc(),{weekday:'short'});
  const span = k===1 ? wd(13) : `${wd(14-k)}–${wd(13)}`;
  const dd=d=>histDay(d).toLocaleDateString(dateLoc(),{weekday:'short', day:'numeric', month:'short'});
  const dated = k===1 ? dd(13) : `${dd(14-k)} – ${dd(13)}`;
  return {label: k===7 ? `${W.week} (${span})` : `${W.sum} ${span}`, v: any ? histNum(sum, it, false) : null,
          longLabel: `${k===7 ? W.week : W.sum} ${dated}`};
}
/* Product sheet: promo days as light red columns (every row), and the running total as one
   line underneath, naming the days it adds up. No Σ column there. */
function cpSheetStrip(ix, h){
  const it=ITEMS[ix], w=cpWtd(ix), L=t();
  const promo=new Set((HIST_PROMO[it.plu]||[]).filter(d=>d>=7).map(d=>d-7));
  const n={};
  const h2=h.replace(/<span class="(SalesHistory__(wd|s|x|d)(?![a-z])[^"]*)"/g, (m,c,k)=>{
    const i=(n[k]=(n[k]||0)+1)-1;
    return promo.has(i) ? `<span class="${c} cpPromo"${k==='wd'?` title="${L.histPromo}"`:''}` : m;
  }).replace('class="SalesHistory', 'class="cpStripLg SalesHistory');
  const val = w.v==null ? '–' : `${w.v}${it.case?' '+L.caseUnit:''}`;
  return h2 + `<div class="cpWtdLg"><span>${w.longLabel}</span><b>${val}</b></div>`;
}
const _histHTML_wtd = histHTML;
/* Under the commande: no row icon on the left, and the running total as an eighth column
   ("Σ") after a divider. The item sheet (opt.lg) keeps its own full strip. */
histHTML = function(ix, opt){
  const h=_histHTML_wtd(ix, opt);
  if(!h) return h;
  if(opt && opt.lg) return cpSheetStrip(ix, h);
  const it=ITEMS[ix], w=cpWtd(ix), L=t();
  const val = w.v==null ? '–' : w.v;
  const sumH = `<span class="SalesHistory__wd cpSum cpSumH" title="${w.label}">Σ</span>`;
  const sumV = `<span class="SalesHistory__s cpSum cpSumV${w.v==null?' is-nil':''}" title="${w.label}${w.v!=null&&it.case?': '+w.v+' '+L.caseUnit:''}">${val}</span>`;
  /* promo days: the 7 columns are days 7..13 of HIST; light red in the header and the value */
  const promo=new Set((HIST_PROMO[it.plu]||[]).filter(d=>d>=7).map(d=>d-7));
  let nh=0, nv=0;
  const mark=(cls, n)=>promo.has(n) ? cls+' cpPromo' : cls;
  const h2=h.replace(/<span class="(SalesHistory__wd[^"]*)"/g, (m,c)=>`<span class="${mark(c, nh++)}"${promo.has(nh-1)?` title="${L.histPromo}"`:''}`)
            .replace(/<span class="(SalesHistory__s[^"]*)"/g, (m,c)=>`<span class="${mark(c, nv++)}"`);
  return h2.replace('class="SalesHistory', 'class="cpStrip SalesHistory')
          .replace(/(<div class="SalesHistory__wk"[^>]*>)((?:<span class="SalesHistory__wd[^"]*"[^>]*>[\s\S]*?<\/span>){7})/, `$1$2${sumH}`)
          .replace(/((?:<span class="SalesHistory__s[^"]*">[^<]*<\/span>){7})(<\/div>)/, `$1${sumV}$2`);
};
render();
"""
CSS_WTD = """
/* ===== C&P: 7-day sales under the commande, running total as an 8th column ===== */
.cpStrip .SalesHistory__card{grid-template-columns:minmax(0,1fr);padding-left:3px;padding-right:3px}
.cpStrip .SalesHistory__marks{display:none}
.cpStrip .SalesHistory__wk{grid-template-columns:repeat(7,minmax(0,1fr)) minmax(0,1.35fr)}
.cpStrip .cpSum{align-self:stretch;display:flex;align-items:center;justify-content:center;margin-left:2px;
  border-left:1px solid var(--ff-grey-300)}
.cpStrip .cpPromo{align-self:stretch;display:flex;align-items:center;justify-content:center;background:#FDECEC}
.cpStrip .cpSum{background:var(--ff-grey-100)}
.cpStripLg .cpPromo{background:#FDECEC}
.cpWtdLg{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:8px;padding:9px 12px;
  border-radius:var(--ff-radius-c8);background:var(--ff-grey-100);font-size:var(--ff-text-primary-body-text-14);color:var(--ff-grey-600)}
.cpWtdLg b{font-size:var(--ff-text-primary-body-text-16);font-weight:var(--ff-weight-semibold);color:var(--ff-grey-900);white-space:nowrap}
.cpStrip .cpSumH{font-weight:var(--ff-weight-semibold);color:var(--ff-grey-600)}
.cpStrip .cpSumV{font-weight:var(--ff-weight-semibold);color:var(--ff-grey-900)}
"""
idx = s.rindex('</style>')
s = s[:idx] + CSS_WTD + s[idx:]
JS = JS.replace('__CP__', json.dumps(cp, ensure_ascii=False)).replace('__DUMMY__', 'true' if dummy else 'false')
idx = s.rindex('</script>')
s = s[:idx] + JS + s[idx:]

if args.orders:
    sys.path.insert(0, __import__('os').path.dirname(__file__))
    from cp_orders_overview import inject, inject_lock
    oc = json.load(open(args.orders, encoding='utf-8')); oc.pop('_source', None)
    s = inject(s, oc, args.clock)
    if args.opens_at:
        s = inject_lock(s, args.opens_at)

open(args.out, 'w', encoding='utf-8').write(s)
print(f'wrote {args.out}: {len(items)} items, {len(cp)} with C&P fields, dummy={dummy}')
