#!/usr/bin/env python3
"""PD-794: warn before saving an inventory count that can't be right (C&P and REWE pages).

The rule (from the PD-794 backtest): the count (back room + shelf, in cases) is above the larger of
  3 x (simulated inventory + today's intake)   and   simulated inventory + today's intake + 3 cases.
Both inputs are on the order item the app reads (simulated inventory = the page's it.app, in cases;
today's intake = order_intake_sku, kg or pieces, divided by the case). Then
  * the inventory keypad shows the warning in its hint box (the count in cases and in kg or
    pieces, next to what the app expects) and the save button reads "Confirm";
  * a + on the row that would cross the line does not step, it opens the same keypad with the
    stepped value already in it: confirm saves it, cancel leaves the row as it was.
A confirmed count saves as typed; after a confirmation + on that item steps without asking again.

Today's intake comes from --intake-json ({"intake_today": {PLU: quantity}}, items not listed have 0).
Running it again replaces the block, so a page that already has it (the REWE base the C&P build
starts from) is never patched twice.

Used by build_cp_perrache.py (--intake-json) and standalone on an already built page:
  python3 tools/cp_high_count.py --intake-json tools/data/cp_neuville_intake_today_2026-10-15.json \
      cerise-neuville-2026-10-15.html cerise-neuville-2026-10-15-11h.html
  python3 tools/cp_high_count.py --intake-json tools/data/rewe_peeters_intake_today_2026-08-25.json \
      rewe-peeters-flueren-2026-08-25.html
"""
import json

MARK = '/* PD-794: count that can\'t be right */'
END = '/* PD-794 end */'

JS = r"""
__MARK__
const CP_INTAKE_TODAY = __DATA__;   /* PLU -> kg or pieces arriving on the order day; missing = 0 */
function cpHighT(){ return ({
  de:{title:'Bestand ungewöhnlich hoch', facts:'Eingegeben: {v} = {u}. Die App erwartet etwa {e} (Bestand plus heutiger Wareneingang).',
      rule:'Der Bestand wird in Kisten eingegeben. Stimmt die Zahl, bestätige sie.', ok:'Bestätigen'},
  en:{title:'Inventory unusually high', facts:'Entered: {v} = {u}. The app expects about {e} (inventory plus today\'s intake).',
      rule:'Inventory is entered in cases. If the number is right, confirm it.', ok:'Confirm'},
  fr:{title:'Stock inhabituellement élevé', facts:'Saisi : {v} = {u}. L\'app attend environ {e} (stock plus livraison du jour).',
      rule:'Le stock se saisit en colis. Si le chiffre est juste, confirmez-le.', ok:'Confirmer'}})[LANG]; }
/* what the app expects, in cases: simulated inventory + today's intake; null = nothing to check against */
function cpExpectKo(it){ if(!(it.case>0) || it.app==null) return null;
  return Math.max(0, it.app) + (CP_INTAKE_TODAY[it.plu]||0)/it.case; }
function cpTooHigh(it,ko){ const e=cpExpectKo(it); return e!=null && ko > Math.max(3*e, e+3)+1e-9; }
/* same rounding as the "= 13 kg" line under the total, so the hint never shows another number */
function cpQtyTxt(it,ko){ return Math.round(ko*it.case)+' '+uw(it); }
const _drawInvPad_cp794 = drawInvPad;
drawInvPad = function(){
  _drawInvPad_cp794();
  const it=ITEMS[INV.ix], v=invPadVals(), hint=document.getElementById('invHint'), btn=document.getElementById('invSpeichern');
  INV.high = !INV.backOnly && !(INV.back==='0' && INV.floor==='0') && cpTooHigh(it, v.cases);
  btn.textContent = INV.high ? cpHighT().ok : t().saveTick;
  if(!INV.high || !hint) return;
  const T=cpHighT(), ex=cpExpectKo(it);
  const facts=T.facts.replace('{v}', csNum(v.cases)+' '+t().caseUnit).replace('{u}', cpQtyTxt(it, v.cases))
    .replace('{e}', koNum(Math.round(ex*10)/10)+' '+t().caseUnit+' = '+cpQtyTxt(it, ex));
  hint.hidden=false;
  hint.innerHTML = ICON_INV_BANG+'<span><b class="hintTitle">'+T.title+'</b>'+facts+'<br>'+T.rule+'</span>';
};
const _invSave_cp794 = document.getElementById('invSpeichern').onclick;
document.getElementById('invSpeichern').onclick = function(e){
  const ix=INV.ix, high=INV.high;
  _invSave_cp794.call(this, e);
  if(high) ST[ix].cpHighOk = true;   /* confirmed: + on this item no longer asks */
};
/* + that would cross the line: same keypad as "enter inventory", with the stepped value in it */
document.addEventListener('click', e=>{
  const b=e.target.closest('[data-a="bstep"][data-d="1"]'); if(!b || b.disabled) return;
  const ix=+b.dataset.i, it=ITEMS[ix], s=ST[ix];
  if(s.cpHighOk) return;
  /* the same step the row would take: C&P from the one number, REWE from the top of the range */
  const r=it.rungs[s.plan]||{};
  let next = s.step==='range' ? stepKo(it, typeof cpSimKo==='function' ? cpSimKo(it,s) : r.hi, 1)
           : s.step==='need' ? 1 : stepKo(it, s.ko, 1);
  if(next==null || isNaN(next)) return;
  next = Math.max(0, Math.min(99, next));
  if(!cpTooHigh(it, next)) return;
  e.stopImmediatePropagation(); e.preventDefault();
  openInvPad(ix);
  INV.floor = String(Math.round(next*100)/100); INV.act='floor';
  drawInvPad();
}, true);
__END__
"""


def strip(s):
    """Remove the block if the page has it (the REWE base page does)."""
    if MARK not in s:
        return s
    i = s.index('\n' + MARK)
    j = s.index(END, i) + len(END) + 1
    return s[:i] + s[j:]


def inject(s, intake):
    """Insert the check before the page's last </script>. intake: dict PLU -> today's intake."""
    s = strip(s)
    for a in ('function drawInvPad(){', "document.getElementById('invSpeichern').onclick=",
              'data-a="bstep" data-d="1"', 'function stepKo('):
        if a not in s:
            raise SystemExit(f'anchor missing: {a!r}')
    js = (JS.replace('__MARK__', MARK).replace('__END__', END)
          .replace('__DATA__', json.dumps(intake, separators=(',', ':'))))
    i = s.rindex('</script>')
    return s[:i] + js + s[i:]


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--intake-json', required=True)
    ap.add_argument('pages', nargs='+')
    a = ap.parse_args()
    intake = json.load(open(a.intake_json, encoding='utf-8'))['intake_today']
    for p in a.pages:
        s = open(p, encoding='utf-8').read()
        open(p, 'w', encoding='utf-8').write(inject(s, intake))
        print('patched', p)
