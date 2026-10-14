#!/usr/bin/env python3
"""C&P: the Commandes tab as the app's orders overview, plus the 11:00 opening lock.

Mirrors freshflowai/mobile main (checked at 1ecca23aa, release 1.53.5):
  * lib/domain/extensions/order/state.dart          status of an order (open / completed / pastDue / future)
  * lib/presentation/features/orders/page/order_list_controller.dart
                                                    current / future / past buckets, page sizes 4 and 2
  * lib/presentation/features/orders/widgets/order_list_table.dart
                                                    C&P columns (hide_purchase_price_and_margin), sorting,
                                                    row colours, 2 rows before "Voir plus"
  * lib/presentation/shared/order_status_chip.dart  chip colours
  * i10n/intl_{fr,en,de_DE}.arb                     every label (the keys keep their arb names)

The rules that decide where an order shows:
  * status 'closed' -> Complétée, 'past_due' -> Passée.
  * status 'open': before the deadline day -> Future; on the day until the deadline -> Ouverte;
    after the deadline -> Ouverte until midnight if the store allows editing after the deadline,
    else Passée.
  * Current = Ouverte, or Complétée / Passée with the deadline today. Future = deadline after
    today. Everything else is past -- so yesterday's order, delivering tomorrow, is the first
    row under "Commandes précédentes".
  * One row per regular order; Prévision is the preorder document with the same deadline.

Data: --orders (tools/data/cp_*_orders_*.json). The page's clock replays every status change
at the time of day shown (?now=HH:MM, then running on), so the same page shows 10:20, 15:00
and 17:00 correctly.

  python3 tools/cp_orders_overview.py --page cerise-perrache-2026-10-13.html \
      --orders tools/data/cp_foch_orders_2026-10-13.json --opens-at 11:00

build_cp_perrache.py calls inject() / inject_lock() at the end when it gets --orders / --opens-at.
"""
import argparse, json, sys

MARK = '/* ===== C&P: orders overview ===== */'
LOCK_MARK = '/* ===== C&P: order opening time (MOB-1730) ===== */'

ANCH = {'de': "    rManualWarning:'Manuelle Warnung',",
        'en': "    rManualWarning:'Manual warning',",
        'fr': "    rManualWarning:'Alerte manuelle',"}

# Copied from i10n/intl_fr.arb, intl_en.arb, intl_de_DE.arb (mobile main 1ecca23aa). Do not reword.
LOC = {
    'fr': dict(ordersListOrderDateColumn='Date', ordersListDeliveryDateColumn='Date livraison',
               ordersListStatusColumn='Statut', ordersListSupplierColumn='Fournisseur',
               ordersListOrderCasesColumn='Commande', ordersListPreOrderCasesColumn='Prévision',
               ordersListOrderRetailColumn='Prix de vente', ordersListPreOrderRetailColumn='PV prévision',
               ordersListPastOrdersHeader='Commandes précédentes', ordersListFutureOrdersHeader='Commandes futures',
               ordersListCurrentOrdersHeader='Commandes en cours', ordersListDeadlineCaption='Heure limite',
               ordersListDeliveryCaption='Livraison', orderStatusCompleted='Complétée', orderStatusOpen='Ouverte',
               orderStatusPastDue='Passée', orderStatusFuture='Future', commonLoadMore='Voir plus',
               commonShowLessCaption='Afficher moins',
               commonNoDataMessage='Pas de données disponibles. Veuillez réessayer plus tard.'),
    'en': dict(ordersListOrderDateColumn='Order Date', ordersListDeliveryDateColumn='Delivery Date',
               ordersListStatusColumn='Status', ordersListSupplierColumn='Supplier',
               ordersListOrderCasesColumn='Order', ordersListPreOrderCasesColumn='Pre-order',
               ordersListOrderRetailColumn='Order Retail', ordersListPreOrderRetailColumn='Pre-order Retail',
               ordersListPastOrdersHeader='Past Orders', ordersListFutureOrdersHeader='Future Orders',
               ordersListCurrentOrdersHeader='Current Orders', ordersListDeadlineCaption='Deadline',
               ordersListDeliveryCaption='Delivery', orderStatusCompleted='Completed', orderStatusOpen='Open',
               orderStatusPastDue='Past due', orderStatusFuture='Future', commonLoadMore='Load More',
               commonShowLessCaption='Show Less', commonNoDataMessage='No data available. Try again later.'),
    'de': dict(ordersListOrderDateColumn='Bestelldatum', ordersListDeliveryDateColumn='Lieferdatum',
               ordersListStatusColumn='Status', ordersListSupplierColumn='Lieferant',
               ordersListOrderCasesColumn='Bestellung', ordersListPreOrderCasesColumn='Vorbestellung',
               ordersListOrderRetailColumn='VK', ordersListPreOrderRetailColumn='Vorbest. VK',
               ordersListPastOrdersHeader='Vergangene Bestellungen', ordersListFutureOrdersHeader='Zukünftige Bestellungen',
               ordersListCurrentOrdersHeader='Aktuelle Bestellungen', ordersListDeadlineCaption='Bestellfrist',
               ordersListDeliveryCaption='Zustellung', orderStatusCompleted='Abgeschlossen', orderStatusOpen='Offen',
               orderStatusPastDue='Überfällig', orderStatusFuture='Zukunft', commonLoadMore='Mehr anzeigen',
               commonShowLessCaption='Weniger anzeigen',
               commonNoDataMessage='Keine Daten verfügbar. Versuchen Sie es später erneut.'),
}
# Prototype-only strings (no arb key: the app has no such screen state yet).
PROTO_LOC = {
    'fr': dict(ocProtoOnly="Prototype : seule la commande du jour s'ouvre ici.", ocLeft='restantes'),
    'en': dict(ocProtoOnly="Prototype: only today's order opens here.", ocLeft='left'),
    'de': dict(ocProtoOnly='Prototyp: nur die heutige Bestellung lässt sich hier öffnen.', ocLeft='verbleibend'),
}

CSS = r"""
/* ===== C&P: orders overview (order_list_page.dart / order_list_table.dart) ===== */
.oc-sec{margin:0 0 24px}
.oc-hd{display:flex;align-items:center;gap:24px;height:40px;padding:0 40px}
.oc-hd h2{margin:0;font-size:18px;font-weight:var(--ff-weight-semibold);color:var(--ff-color-primary)}
.oc-hd .dt{color:#A1A1AA;font-size:var(--ff-text-primary-body-text-14);font-weight:400}
/* column flex 20 | 18 | 20 | 17 | 14 | 16 | 16 | 16 */
.oc-grid{display:grid;grid-template-columns:20fr 18fr 20fr 17fr 14fr 16fr 16fr 16fr;align-items:center;padding:0 28px 0 40px}
.oc-list.cur .oc-grid{padding:0 16px}
.oc-list.cur{margin:0 28px 0 24px}
.oc-colh{height:48px;font-size:var(--ff-text-primary-body-text-14);font-weight:var(--ff-weight-medium);color:#27272A}
.oc-colh button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:4px;line-height:1.2}
.oc-row{min-height:64px;background:#fff;border-radius:8px;cursor:pointer;font-size:16px;color:#18181B}
.oc-list:not(.cur) .oc-row{margin-bottom:1px}
.oc-list.cur .oc-row{border:1px solid #E7E6E6;margin-bottom:8px}
.oc-row.open{background:#FFFAF3;border:1px solid #FDCA88}
.oc-row > div{padding-right:16px;min-width:0}
.oc-d b{display:block;font-weight:var(--ff-weight-medium);font-size:16px;white-space:nowrap}
.oc-d.dv b{color:#71717A}
.oc-d span{display:flex;gap:6px;white-space:nowrap;font-size:14px}
.oc-d span i{font-style:normal;font-weight:300;color:#A1A1AA}
.oc-d span em{font-style:normal;font-weight:var(--ff-weight-medium);color:#C1CE5D}
.oc-sup{font-weight:var(--ff-weight-medium);overflow:hidden;text-overflow:ellipsis}
.oc-chip{display:inline-flex;align-items:center;gap:4px;max-width:100%;height:24px;box-sizing:border-box;padding:0 8px;border-radius:25px;
  font-size:12px;font-weight:var(--ff-weight-semibold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.oc-chip.open{color:#FC9511;background:rgba(234,140,47,.2)}
.oc-chip.completed{color:#429359;background:rgba(70,140,105,.2)}
.oc-chip.pastDue{color:#777DA0;background:rgba(117,123,154,.3)}
.oc-chip.future{color:#5A6BC2;background:rgba(93,112,216,.2)}
.oc-num{white-space:nowrap;font-weight:400;padding-right:12px}
.oc-foot{display:flex;justify-content:flex-end;gap:8px;padding:0 36px}
.oc-foot button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:8px;height:64px;font-size:var(--ff-text-primary-body-text-14);color:var(--ff-color-primary);padding:0 8px}
.oc-empty{padding:24px 40px;color:#A1A1AA;text-align:center}
.oc-scroll{overflow-x:auto}
.oc-scroll > div{min-width:900px}
"""

HTML = """
    <!-- C&P: Commandes = the app's orders overview (current, future, past). -->
    <div class="dash-panel" id="panelOrders" hidden><div class="oc-scroll"><div id="ocBody"></div></div></div>
"""

JS = r"""
const OC = __OC__;
/* ---- clock: the page's order day, at the real time of day or ?now=HH:MM (then running on) ---- */
const OC_T0 = Date.now();
const OC_START = (()=>{
  const q=new URLSearchParams(location.search), m=(q.get('now')||'').match(/^(\d{1,2}):(\d{2})$/);
  if(m) return +m[1]*60 + +m[2];
  if(q.get('selftest')==='1') return 12*60;
  /* a page built with a fixed starting time (--clock) opens on it, so whoever opens the link
     sees the state it was built to show; ?now= still overrides */
  const c=(OC.clock||'').match(/^(\d{1,2}):(\d{2})$/);
  if(c) return +c[1]*60 + +c[2];
  const d=new Date(); return d.getHours()*60 + d.getMinutes() + d.getSeconds()/60;
})();
function ocNowMin(){ return OC_START + (Date.now()-OC_T0)/60000; }
function ocDt(s){ const [d,tm]=s.split('T'); const [y,mo,dd]=d.split('-').map(Number); const [h,mi]=(tm||'00:00').split(':').map(Number); return new Date(y,mo-1,dd,h,mi); }
function ocNow(){ const d=ocDt(OC.today+'T00:00'); return new Date(d.getTime()+ocNowMin()*60000); }
const ocDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const ocSameDay = (a,b) => ocDay(a).getTime()===ocDay(b).getTime();

/* ---- state.dart: OrderModelStatusX.orderState ---- */
function ocStatusAt(o, now){
  let s='open';
  for(const [t,st] of o.status){ if(ocDt(t) <= now) s=st; }
  return s;
}
function ocState(o, now){
  const s=ocStatusAt(o, now), dl=ocDt(o.deadline);
  if(s==='closed') return 'completed';
  if(s==='past_due') return 'pastDue';
  if(dl >= now) return now < ocDay(dl) ? 'future' : 'open';
  if(OC.allowAfterDeadline && ocSameDay(now, dl)) return 'open';
  return 'pastDue';
}
function ocIsCurrent(o, now){
  const st=ocState(o, now);
  if(st==='open') return true;
  return (st==='completed' || st==='pastDue') && ocSameDay(now, ocDt(o.deadline));
}

/* ---- order_list_controller.dart: two queries, paged, then bucketed ---- */
const OC_PAGE = {fut:4, past:2};
const OC_UI = {cur:{col:'status', asc:false},
               fut:{col:'date', asc:true, pages:1, open:false},
               past:{col:'date', asc:false, pages:1, open:false}};
function ocBuckets(){
  const now=ocNow(), start=ocDay(now), end=new Date(start.getTime()+86400000-1);
  const byAsc=(a,b)=>ocDt(a.deadline)-ocDt(b.deadline);
  const futQ = OC.orders.filter(o=>ocDt(o.deadline) >= start).sort(byAsc).slice(0, OC_PAGE.fut*OC_UI.fut.pages);
  const pastQ = OC.orders.filter(o=>ocDt(o.deadline) <= start).sort((a,b)=>-byAsc(a,b)).slice(0, OC_PAGE.past*OC_UI.past.pages);
  const cur=[], fut=[], past=[], seen=new Set();
  for(const o of [...futQ, ...pastQ]){
    if(seen.has(o.id)) continue; seen.add(o.id);
    if(ocIsCurrent(o, now)) cur.push(o);
    else if(ocDt(o.deadline) > end) fut.push(o);
    else past.push(o);
  }
  return {cur, fut, past, now};
}

/* ---- order_list_table.dart ---- */
const OC_COLS = ['date','supplier','delivery','status','ordCases','ordRetail','preCases','preRetail'];
const OC_PRIO = {open:20, pastDue:10, completed:5, future:0};
function ocCmp(col, now){
  const v = {date:o=>ocDt(o.deadline).getTime(), delivery:o=>ocDt(o.delivery).getTime(), supplier:o=>OC.supplier,
    status:o=>OC_PRIO[ocState(o,now)], ordCases:o=>o.ord[0], ordRetail:o=>o.ord[1], preCases:o=>o.pre[0], preRetail:o=>o.pre[1]}[col];
  return (a,b)=>{ const x=v(a), y=v(b); return x<y?-1:x>y?1:0; };
}
function ocLoc(){ return LANG==='en' ? 'en-US' : dateLoc(); }
/* AppDateFormat 'MMMEd' -> "mar. 13 oct." / "Tue, Oct 13" / "Di., 13. Okt." */
const ocMMMEd = d => d.toLocaleDateString(ocLoc(), {weekday:'short', day:'numeric', month:'short'});
/* 'EEE, MMM dd, yyyy' -> "mar., oct. 13, 2026" */
function ocFullDate(d){ const l=ocLoc();
  return `${d.toLocaleDateString(l,{weekday:'short'})}, ${d.toLocaleDateString(l,{month:'short'})} ${String(d.getDate()).padStart(2,'0')}, ${d.getFullYear()}`; }
/* DateFormat.jm(locale) */
const ocTime = d => d.toLocaleTimeString(ocLoc(), {hour: LANG==='en'?'numeric':'2-digit', minute:'2-digit'});   // fr/de "05:00", en "5:00 AM"
/* AppMoneyFormat(isLong): de_DE currency, 2 decimals, none on a whole number */
const ocMoney = v => v.toLocaleString('de-DE', {minimumFractionDigits: v%1?2:0, maximumFractionDigits: v%1?2:0}) + ' €';
const OC_ARROW = up => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="transform:rotate(${up?0:180}deg)"><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></svg>`;
const OC_CHEV = up => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform:rotate(${up?180:0}deg)"><path d="M6 9l6 6 6-6"/></svg>`;
const OC_STATE_KEY = {open:'orderStatusOpen', completed:'orderStatusCompleted', pastDue:'orderStatusPastDue', future:'orderStatusFuture'};
function ocChip(o, now){ const st=ocState(o, now); return `<span class="oc-chip ${st}">${t()[OC_STATE_KEY[st]].toUpperCase()}</span>`; }
/* Today's order follows the edits made in the list, as the app's overview does when it reloads
   on return (didPopNext): the stored total plus whatever the list changed since the page loaded. */
function ocListSums(){
  let oc=0, ov=0, pc=0, pv=0;
  ITEMS.forEach((it,ix)=>{
    if(ST[ix].hidden) return;
    const o=orderVal(ix), p=(typeof preShown==='function' && !cpRemoved(ix)) ? (preShown(ix)||0) : 0;
    oc+=o; pc+=p; if(it.case){ ov+=o*it.case*(it.vk||0); pv+=p*it.case*(it.vk||0); }
  });
  return {oc, ov, pc, pv};
}
const OC_LIST0 = ocListSums();
function ocTotals(o){
  if(!o.deadline.startsWith(OC.today)) return o;
  const n=ocListSums();
  return {...o, ord:[o.ord[0]+n.oc-OC_LIST0.oc, Math.round((o.ord[1]+n.ov-OC_LIST0.ov)*100)/100],
                pre:[o.pre[0]+n.pc-OC_LIST0.pc, Math.round((o.pre[1]+n.pv-OC_LIST0.pv)*100)/100]};
}
function ocRow(o, kind, now){
  o = ocTotals(o);
  const L=t(), dl=ocDt(o.deadline), dv=ocDt(o.delivery), st=ocState(o, now);
  return `<div class="oc-grid oc-row${st==='open'?' open':''}" data-oc="row" data-id="${o.id}" data-kind="${kind}" role="button" tabindex="0">
    <div class="oc-d"><b>${ocMMMEd(dl)}</b><span><i>${L.ordersListDeadlineCaption}</i><em>${ocTime(dl)}</em></span></div>
    <div class="oc-sup">${OC.supplier}</div>
    <div class="oc-d dv"><b>${ocMMMEd(dv)}</b><span><i>${L.ordersListDeliveryCaption}</i><em>${ocTime(dv)}</em></span></div>
    <div>${ocChip(o, now)}</div>
    <div class="oc-num">${o.ord[0]} ${L.caseUnit}</div>
    <div class="oc-num">${ocMoney(o.ord[1])}</div>
    <div class="oc-num">${o.pre[0]} ${L.caseUnit}</div>
    <div class="oc-num">${ocMoney(o.pre[1])}</div>
  </div>`;
}
function ocColh(kind){
  const L=t(), ui=OC_UI[kind];
  const title={date:L.ordersListOrderDateColumn, supplier:L.ordersListSupplierColumn, delivery:L.ordersListDeliveryDateColumn,
    status:L.ordersListStatusColumn, ordCases:L.ordersListOrderCasesColumn, ordRetail:L.ordersListOrderRetailColumn,
    preCases:L.ordersListPreOrderCasesColumn, preRetail:L.ordersListPreOrderRetailColumn};
  return `<div class="oc-grid oc-colh">${OC_COLS.map(c=>`<div><button type="button" data-oc="sort" data-k="${kind}" data-c="${c}">${title[c]}${ui.col===c?' '+OC_ARROW(ui.asc):''}</button></div>`).join('')}</div>`;
}
function ocList(kind, rows, now){
  const L=t(), ui=OC_UI[kind];
  if(!rows.length) return `<div class="oc-empty">${L.commonNoDataMessage}</div>`;
  const cmp=ocCmp(ui.col, now);
  const sorted=rows.slice().sort((a,b)=>cmp(a,b)*(ui.asc?1:-1));
  const shown = kind==='cur' || ui.open ? sorted : sorted.slice(0, 2);
  let h = `<div class="oc-list ${kind}">${ocColh(kind)}${shown.map(o=>ocRow(o, kind, now)).join('')}</div>`;
  if(kind!=='cur'){
    /* the footer is always there: "Voir plus" fetches the next page, "Afficher moins" folds back to 2 */
    h += `<div class="oc-foot">${ui.open?`<button type="button" data-oc="less" data-k="${kind}">${L.commonShowLessCaption} ${OC_CHEV(true)}</button>`:''}`
       + `<button type="button" data-oc="more" data-k="${kind}">${L.commonLoadMore} ${OC_CHEV(false)}</button></div>`;
  }
  return h;
}
function renderOrdersPanel(){
  const el=document.getElementById('ocBody'); if(!el) return;
  const L=t(), b=ocBuckets();
  el.innerHTML =
    `<section class="oc-sec"><div class="oc-hd"><h2>${L.ordersListCurrentOrdersHeader}</h2><span class="dt">${ocFullDate(b.now)}</span></div>${ocList('cur', b.cur, b.now)}</section>
     <section class="oc-sec"><div class="oc-hd"><h2>${L.ordersListFutureOrdersHeader}</h2></div>${ocList('fut', b.fut, b.now)}</section>
     <section class="oc-sec"><div class="oc-hd"><h2>${L.ordersListPastOrdersHeader}</h2></div>${ocList('past', b.past, b.now)}</section>`;
}
function ocOpenRow(row){
  if(row.dataset.kind==='cur' && row.dataset.id===OC.orders.find(o=>o.deadline.startsWith(OC.today))?.id){ enterApp(); return; }
  if(typeof lkSay==='function') lkSay(t().ocProtoOnly);
}
document.getElementById('ocBody').addEventListener('click', e=>{
  const b=e.target.closest('[data-oc]'); if(!b) return;
  const ui=OC_UI[b.dataset.k];
  if(b.dataset.oc==='row'){ ocOpenRow(b); return; }
  if(b.dataset.oc==='sort'){ if(ui.col===b.dataset.c) ui.asc=!ui.asc; else { ui.col=b.dataset.c; ui.asc=true; } }
  if(b.dataset.oc==='more'){ ui.open=true; ui.pages++; }
  if(b.dataset.oc==='less'){ ui.open=false; }
  renderOrdersPanel();
});
document.getElementById('ocBody').addEventListener('keydown', e=>{
  const r=e.target.closest('[data-oc="row"]');
  if(r && (e.key==='Enter'||e.key===' ')){ e.preventDefault(); ocOpenRow(r); }
});
/* Dashboard "today's order" card: supplier, status chip text, time left to the deadline. */
function ocPaintCard(){
  if(OC.opensAt){ const [h,m]=OC.opensAt.split(':').map(Number); if(ocNowMin() < h*60+m) return; }   // the 11:00 lock paints the closed card
  const L=t(), card=document.querySelector('.dash-ordercard'); if(!card) return;
  const nm=card.querySelector('.nm'); if(nm) nm.textContent=OC.supplier;
  const pill=document.getElementById('dbOpenPill'), cd=document.getElementById('dbCountdown');
  const today=OC.orders.find(o=>o.deadline.startsWith(OC.today));
  const now=ocNow(), st=today ? ocState(today, now) : 'pastDue';
  if(pill) pill.textContent=L[OC_STATE_KEY[st]].toUpperCase();
  if(cd){
    const m=today ? Math.ceil((ocDt(today.deadline)-now)/60000) : 0;
    cd.textContent = m>0 ? `${Math.floor(m/60)}h${String(m%60).padStart(2,'0')}m ${L.ocLeft}` : '';
  }
}
(function(){ const mo=document.getElementById('dbMoreOrders'); if(mo){ mo.style.cursor='pointer'; mo.addEventListener('click', ()=>showDashTab(1)); } })();
const _showDash_oc = showDash;
showDash = function(...x){ const r=_showDash_oc(...x); if(DASH_TAB===1) renderOrdersPanel(); return r; };
const _applyLang_oc = applyLang;
applyLang = function(...a){ const r=_applyLang_oc(...a); ocPaintCard(); if(DASH_TAB===1) renderOrdersPanel(); return r; };
ocPaintCard();
setInterval(ocPaintCard, 30000);
/* statuses change with the clock (16:01 -> Passée, midnight -> new buckets) */
setInterval(()=>{ if(DASH_TAB===1 && document.body.classList.contains('dash-active')) renderOrdersPanel(); }, 30000);
"""


def _add_locale(rep, table):
    for lg, kv in table.items():
        rep(ANCH[lg], ANCH[lg] + ''.join(f"\n    {k}:{json.dumps(v, ensure_ascii=False)},  // [arb] {k}" if table is LOC
                                         else f"\n    {k}:{json.dumps(v, ensure_ascii=False)}," for k, v in kv.items()))


def inject(s, orders, clock=None):
    if clock:
        orders = {**orders, 'clock': clock}
    if MARK in s:
        sys.exit('orders overview already in the page')

    def rep(a, b, cnt=1):
        nonlocal s
        n = s.count(a)
        if n != cnt:
            sys.exit(f'anchor x{n} (want {cnt}): {a[:90]!r}')
        s = s.replace(a, b)

    _add_locale(rep, LOC)
    _add_locale(rep, PROTO_LOC)
    idx = s.index('</style>')
    s = s[:idx] + CSS + s[idx:]
    rep('    </div><!-- /panelDash -->\n', '    </div><!-- /panelDash -->\n' + HTML)
    rep("const DASH_PANELS=['panelDash','panelStore','panelInv'];",
        "const DASH_PANELS=['panelDash','panelOrders','panelStore','panelInv'];")
    rep("  if(i===1){ showApp(); return; }            // Bestellungen -> die Bestellliste\n", "")
    rep("  const panel = i===0?'panelDash' : i===2?'panelInv' : 'panelStore';",
        "  const panel = i===0?'panelDash' : i===1?'panelOrders' : i===2?'panelInv' : 'panelStore';")
    rep("  if(panel==='panelInv')   renderInvPanel();",
        "  if(panel==='panelInv')   renderInvPanel();\n  if(panel==='panelOrders') renderOrdersPanel();")
    js = MARK + JS.replace('__OC__', json.dumps(orders, ensure_ascii=False))
    idx = s.rindex('</script>')
    return s[:idx] + js + s[idx:]


# ---------------------------------------------------------------------------
# MOB-1730: C&P orders open at a fixed time (11:00), independent of when files arrive.
# Before that, today's order and future orders cannot be opened at all, and counting
# is locked too. Past orders stay viewable. No override, also not for Freshflow staff.
# Every way in is stopped: round button, overview rows, the order screen itself
# (showApp), the back button, and the Bestand scan button.

LOCK_LOC = {
    'de': dict(lkOpensAt='Öffnet um', lkMsg='Die Bestellung öffnet um {t} Uhr.', lkIn='noch {d}',
               lkCountMsg='Zählen ist ab {t} Uhr möglich, zusammen mit der Bestellung.',
               lkNowOpen='Die Bestellung ist jetzt offen.', lkLeft='verbleibend'),
    'en': dict(lkOpensAt='Opens at', lkMsg='The order opens at {t}.', lkIn='in {d}',
               lkCountMsg='Counting opens at {t}, together with the order.',
               lkNowOpen='The order is now open.', lkLeft='left'),
    'fr': dict(lkOpensAt='Ouvre à', lkMsg='La commande ouvre à {t}.', lkIn='dans {d}',
               lkCountMsg='Le comptage ouvre à {t}, en même temps que la commande.',
               lkNowOpen='La commande est maintenant ouverte.', lkLeft='restantes'),
}

LOCK_CSS = r"""
/* ===== C&P: order opening time (MOB-1730) ===== */
.oc-chip.lock{color:#52525B;background:#F4F4F5}
.oc-row.locked{cursor:default}
.oc-row.locked.open{background:#fff;border-style:dashed;border-color:#D4D4D8}
.oc-row.locked .oc-num{color:#A1A1AA}
.dash-fab.locked, .invFab.locked{background:var(--ff-grey-400);box-shadow:none}
.dash-fab .lkBadge, .invFab .lkBadge{position:absolute;right:-4px;top:-4px;width:20px;height:20px;border-radius:50%;
  background:var(--ff-color-white);color:var(--ff-grey-600);display:grid;place-items:center;box-shadow:0 1px 3px rgba(0,0,0,.25)}
.invFab{position:relative}
.dash-ordercard.locked{background:var(--ff-grey-100);border-color:var(--ff-grey-200)}
.dash-ordercard.locked .dash-pill-open{background:var(--ff-grey-500);display:inline-flex;align-items:center;gap:5px}
.lkMsg{position:fixed;left:50%;bottom:96px;transform:translateX(-50%) translateY(8px);z-index:400;max-width:calc(100vw - 32px);
  background:var(--ink);color:var(--ff-color-white);border-radius:12px;padding:12px 18px;font-size:var(--ff-text-primary-body-text-14);
  display:flex;align-items:center;gap:10px;opacity:0;pointer-events:none;transition:opacity .15s, transform .15s}
.lkMsg.on{opacity:1;transform:translateX(-50%)}
.lkMsg small{opacity:.7}
"""

LOCK_JS = r"""
const OC_OPENS = OC.opensAt || null;          // 'HH:MM' store time; null = no lock (every other store)
const LK_ICON = s => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>`;
const lkMin = hhmm => { const [h,m]=hhmm.split(':').map(Number); return h*60+m; };
/* The one check. Before the opening time, nothing from today on opens. */
function orderLocked(){ return !!OC_OPENS && ocNowMin() < lkMin(OC_OPENS); }
function lkDur(min){ min=Math.max(1, Math.ceil(min)); const h=Math.floor(min/60), m=min%60;
  return h ? `${h} h ${String(m).padStart(2,'0')}` : `${m} min`; }
function lkLeft(){ return lkDur(lkMin(OC_OPENS) - ocNowMin()); }
let LK_MSG_T=null;
function lkSay(text){
  let el=document.getElementById('lkMsg');
  if(!el){ el=document.createElement('div'); el.id='lkMsg'; el.className='lkMsg'; el.setAttribute('role','status'); document.body.appendChild(el); }
  el.innerHTML = text; el.classList.add('on');
  clearTimeout(LK_MSG_T); LK_MSG_T=setTimeout(()=>el.classList.remove('on'), 2600);
}
function lkSayLocked(kind){
  const L=t(), msg=(kind==='count'?L.lkCountMsg:L.lkMsg).replace('{t}', OC_OPENS);
  lkSay(`${LK_ICON(16)}<span>${msg} <small>${L.lkIn.replace('{d}', lkLeft())}</small></span>`);
}

/* The order screen itself refuses to show -- whatever led there. */
const _showApp_lk = showApp;
showApp = function(...a){
  if(orderLocked()){ showDash(); lkSayLocked('order'); return; }
  return _showApp_lk(...a);
};
const _enterApp_lk = enterApp;
enterApp = function(...a){ if(orderLocked()){ lkSayLocked('order'); return; } return _enterApp_lk(...a); };
const _bsOpen_lk = bsOpen;
bsOpen = function(...a){ if(orderLocked()){ lkSayLocked('count'); return; } return _bsOpen_lk(...a); };
['dashFab','invFab'].forEach(id=>{
  const el=document.getElementById(id); if(!el) return;
  el.addEventListener('click', e=>{
    if(!orderLocked()) return;
    e.stopImmediatePropagation(); e.preventDefault();
    lkSayLocked(id==='invFab'?'count':'order');
  }, true);
});

/* Overview: today's and future rows show the opening time instead of their status chip. */
const _ocRow_lk = ocRow;
ocRow = function(o, kind, now){
  let h=_ocRow_lk(o, kind, now);
  if(!orderLocked() || kind==='past') return h;
  return h.replace(/<span class="oc-chip [a-zA-Z]+">[^<]*<\/span>/, `<span class="oc-chip lock">${LK_ICON(12)}${OC_OPENS}</span>`)
          .replace('class="oc-grid oc-row', 'class="oc-grid oc-row locked')
          .replace('data-oc="row"', 'data-oc="locked"');
};
document.getElementById('ocBody').addEventListener('click', e=>{
  if(e.target.closest('[data-oc="locked"]')) lkSayLocked('order');
});

/* Dashboard card + buttons follow the clock. */
function lkPaint(){
  const L=t(), locked=orderLocked();
  const card=document.querySelector('.dash-ordercard');
  if(card){
    card.classList.toggle('locked', locked);
    if(locked){
      const pill=document.getElementById('dbOpenPill'), cd=document.getElementById('dbCountdown');
      const nm=card.querySelector('.nm'); if(nm) nm.textContent=OC.supplier;
      if(pill) pill.innerHTML=`${LK_ICON(12)}${OC_OPENS}`;
      if(cd) cd.textContent=`${L.lkOpensAt} ${OC_OPENS} · ${L.lkIn.replace('{d}', lkLeft())}`;
    } else ocPaintCard();
  }
  ['dashFab','invFab'].forEach(id=>{
    const el=document.getElementById(id); if(!el) return;
    el.classList.toggle('locked', locked);
    let b=el.querySelector('.lkBadge');
    if(locked && !b){ el.insertAdjacentHTML('beforeend', `<span class="lkBadge">${LK_ICON(12)}</span>`); }
    if(!locked && b) b.remove();
  });
  if(DASH_TAB===1) renderOrdersPanel();
}
let LK_WAS = orderLocked();
setInterval(()=>{
  const now=orderLocked();
  if(now!==LK_WAS){ LK_WAS=now; lkPaint(); if(!now) lkSay(`${t().lkNowOpen}`); }
  else lkPaint();
}, 15000);
const _applyLang_lk = applyLang;
applyLang = function(...a){ const r=_applyLang_lk(...a); lkPaint(); return r; };
lkPaint();
"""


def inject_lock(s, opens_at):
    if LOCK_MARK in s:
        sys.exit('order opening lock already in the page')
    if MARK not in s:
        sys.exit('the lock needs the orders overview (inject() first)')

    def rep(a, b, cnt=1):
        nonlocal s
        n = s.count(a)
        if n != cnt:
            sys.exit(f'anchor x{n} (want {cnt}): {a[:90]!r}')
        s = s.replace(a, b)

    _add_locale(rep, LOCK_LOC)
    idx = s.index('</style>')
    s = s[:idx] + LOCK_CSS + s[idx:]
    rep('const OC = {', 'const OC = {"opensAt": %s, ' % json.dumps(opens_at))
    idx = s.rindex('</script>')
    return s[:idx] + LOCK_MARK + LOCK_JS + s[idx:]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--page', required=True)
    ap.add_argument('--orders', required=True)
    ap.add_argument('--opens-at', help="HH:MM: today's and future orders cannot be opened before this (C&P: 11:00, MOB-1730)")
    ap.add_argument('--clock', help='HH:MM the page opens on when no ?now= is given (default: the real time of day)')
    ap.add_argument('--out')
    a = ap.parse_args()
    page = open(a.page, encoding='utf-8').read()
    orders = json.load(open(a.orders, encoding='utf-8'))
    orders.pop('_source', None)
    out = inject(page, orders, a.clock)
    if a.opens_at:
        out = inject_lock(out, a.opens_at)
    open(a.out or a.page, 'w', encoding='utf-8').write(out)
    print(f'wrote {a.out or a.page}: {len(orders["orders"])} orders')
