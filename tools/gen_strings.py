#!/usr/bin/env python3
"""Check the prototype's string table against the app's .arb translations.

Anything the app already says is taken from Mobile/i10n/intl_*.arb verbatim, so
the demo reads exactly like the app in EN and FR. Only Bereichsabfrage-specific
strings -- the shelf picker, the stepper, the completion dialog -- are written
here, and those are the ones still needing real .arb keys.

    python3 tools/gen_strings.py           # list the arb-backed keys and values
    python3 tools/gen_strings.py --check   # fail if an arb key has disappeared

The table itself lives inline in edeka-dankenbring.html (the prototype has to
stay a single self-contained file); this script is how you verify it still
matches the app after the .arb files change.
"""

import json
import pathlib
import sys

ARB = pathlib.Path("/Users/michael/Github/Mobile/i10n")

# prototype key -> .arb key. Everything here is the app's own wording.
FROM_ARB = {
    "ordersatz": "missingInputOrderSetCategoryCaption", "back": "commonBack",
    "item": "commonItem", "inventory": "tableInventoryHeader",
    "order": "tableOrderHeader", "search": "commonSearch", "filter": "commonFilterBy",
    "cancel": "commonCancel", "close": "commonClose", "save": "commonSave",
    "confirm": "commonConfirm", "continue": "commonContinue",
    "completeOrder": "commonCompleteOrder", "manageOrder": "orderManageItemsCaption",
    "caseCount": "commonCaseCount", "caseUnit": "commonCaseUnitLabel",
    "piece": "orderItemUnitPiece", "displaySize": "needsAttentionGroupDisplaySizeCaption",
    "backStock": "orderItemFieldBackInventoryLabel",
    "frontStock": "orderItemFieldFrontInventoryLabel",
    "total": "tableTotalInventoryHeader", "cost": "commonOrderCost",
    "retail": "commonRetailPrice", "margin": "commonProfitMargin",
    "acceptance": "commonAcceptanceRateCaption",
    "shrink": "missingInputShrinkCategoryCaption", "revenue": "revenueOverviewTitle",
    "weather": "dashboardWeatherCardTitle",
    "todayOverview": "dashboardRevenueSalesOverviewCardTitle",
    "todayOrders": "dashboardTodayOrdersCardTitle",
    "tutorials": "dashboardTutorialsCardTitle",
    "upcoming": "dashboardUpcomingEventsCardTitle",
    "seeMoreOrders": "dashboardOrdersCardSeeAllCaption", "currentOrder": "fabNewOrder",
    "statusOpen": "orderStatusOpen", "deadline": "ordersListDeadlineCaption",
    "hiddenItems": "sortHiddenItemsCaption", "clearFilters": "filterClearCaption",
    "bio": "orderItemLabelBio", "sale": "orderItemLabelSale",
    "navDashboard": "navDashboard", "navOrders": "navOrders",
    "navMyStore": "navMyStore", "navSettings": "navSettings",
    "orderQuantity": "needsAttentionGroupOrderCaption",
    "allEvents": "dashboardEventsTableColumnHeader",
}

# No counterpart in the app -- translated in the prototype, awaiting .arb keys.
PROTOTYPE_ONLY = [
    "shelfEyebrow", "shelfTitle", "shelfCount", "shelfItems", "shelfDone",
    "shelfCurrent", "shelfChoose", "shelfSelect", "shelfNext", "shelfClose",
    "shelfCloseQ", "shelfCloseYes", "openItems", "showAll", "all", "onlyopen",
    "more", "less", "undo", "reset", "resetQ", "bulk", "searchItems", "scanDemo",
    "editShelves", "adjustDisplay", "adjustOrder", "switchToBack",
    "enterInventory", "enterDisplay", "enterOrder", "count", "noladder",
    "countsub", "nolsub", "unsure", "atLeast", "exactly", "anyAmount",
    "prevOrder", "case", "manageDone", "backArrow", "completeOrderArrow",
    "deadlineToday", "dlgPendingOne", "dlgPendingMany", "dlgAllChecked",
    "dlgClosing",
]


def main():
    locales = {loc: json.loads((ARB / f).read_text(encoding="utf-8"))
               for loc, f in (("de", "intl_de_DE.arb"), ("en", "intl_en.arb"),
                              ("fr", "intl_fr.arb"))}
    missing = [(k, a) for k, a in FROM_ARB.items()
               if any(a not in locales[loc] for loc in locales)]

    if "--check" in sys.argv:
        if missing:
            for k, a in missing:
                print("MISSING in .arb: %s -> %s" % (k, a))
            sys.exit(1)
        print("ok: all %d arb-backed keys resolve in de/en/fr" % len(FROM_ARB))
        print("    %d prototype-only strings still need .arb keys"
              % len(PROTOTYPE_ONLY))
        return

    print("%-20s %-40s %-22s %s" % ("key", "arb key", "en", "fr"))
    for k, a in sorted(FROM_ARB.items()):
        if a in locales["en"]:
            print("%-20s %-40s %-22s %s"
                  % (k, a, locales["en"][a][:22], locales["fr"][a][:26]))
    print("\nPrototype-only, no .arb key yet (%d):" % len(PROTOTYPE_ONLY))
    print("  " + ", ".join(PROTOTYPE_ONLY))


if __name__ == "__main__":
    main()
