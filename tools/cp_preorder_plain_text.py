#!/usr/bin/env python3
"""C&P: the "Prévision N CS" line above the commande as plain text, not a chip.

Label in grey, the quantity a little darker, centred over the commande stepper -- as the
app draws it. build_cp_perrache.py builds new pages this way; this script converts pages
that were built before (python3 tools/cp_preorder_plain_text.py page.html [...]).
"""
import sys

OLD_CSS = """.lineTag{display:inline-block;margin:0 0 5px 42px;padding:1px 8px;border-radius:var(--ff-radius-c15);
  border:1px solid var(--ff-grey-300);font-size:var(--ff-text-primary-caption-12);color:var(--ff-grey-600)}"""
NEW_CSS = """.withbang.hasLineTag{flex-wrap:wrap}
.lineTag{flex:0 0 100%;order:-1;box-sizing:border-box;margin:0 0 6px;padding-right:24px;text-align:center;white-space:nowrap;
  font-size:var(--ff-text-primary-body-text-14);color:var(--ff-grey-500);font-weight:var(--ff-weight-regular, 400)}
.lineTag b{font-weight:var(--ff-weight-medium);color:var(--ff-grey-600);margin-left:6px}"""
OLD_TAG = '`<div class="lineTag">${L.preOrdered} ${cc.preOrdered} ${L.caseUnit}</div>`'
NEW_TAG = '`<div class="lineTag">${L.preOrdered}<b>${cc.preOrdered} ${L.caseUnit}</b></div>`'
OLD_INSERT = "ordWrap.insertAdjacentHTML('beforebegin', " + NEW_TAG + ")"
NEW_INSERT = "{ ordWrap.classList.add('hasLineTag'); ordWrap.insertAdjacentHTML('afterbegin', " + NEW_TAG + "); }"


def convert(s):
    if NEW_INSERT in s:
        return s, False
    for a in (OLD_CSS, OLD_TAG):
        if s.count(a) != 1:
            sys.exit(f'anchor x{s.count(a)} (want 1): {a[:70]!r}')
    s = s.replace(OLD_CSS, NEW_CSS).replace(OLD_TAG, NEW_TAG)
    return s.replace(OLD_INSERT, NEW_INSERT), True


if __name__ == '__main__':
    for p in sys.argv[1:]:
        s, changed = convert(open(p, encoding='utf-8').read())
        if changed:
            open(p, 'w', encoding='utf-8').write(s)
        print(('converted ' if changed else 'already plain ') + p)
