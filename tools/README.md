# Tagesaktualisierung einer Store-Seite

Ein Kommando, jeder Laden, beide Algorithmen, jeder Tag.

```bash
# klassische Bestellung
python3 tools/build_store_page.py --store edeka_center_stroetmann_coesfeld \
        --algo classic --page ecenter-coesfeld.html

# Szenario-Bestellung: braucht vorher die Leitern aus RP_theta6.py
python3 RP_theta6.py --date $(date +%F) --refresh-extract --refresh-v3
python3 tools/build_store_page.py --store rewe_peeters_flueren --algo scenario \
        --page rewe-peeters.html \
        --items-json ~/Documents/Claude/peeters_sheet/RP_items_app_$(date +%Y%m%d).json
```

`--date` weglassen heisst heute, frisch von der Uhr. **Nie ein Datum aus einem aelteren Chat
uebernehmen**: genau so entstanden zwei Seiten auf dem Ordersatz von gestern, aufgefallen erst,
als Avik eine Zahl vom Telefon vorgelesen hat.

## Was garantiert ist

Bestand und Bestellvorschlag entsprechen Artikel fuer Artikel dem, was die App zeigt, weil beide
unveraendert aus `prod_orders_output` kommen und nicht nachgerechnet werden. Die **Bereiche** sind
unsere Ergaenzung und kommen aus dem Algorithmus des Ladens.

## Die Sperren, jede aus einem echten Fehler

| Sperre | wogegen |
|---|---|
| Datum wird bei jedem Lauf neu von der Uhr geholt | zwei Seiten liefen auf dem Vortag |
| nur `prod_orders_output` wird gelesen | `core_orders_agreement` und der Auswertungsreport hinken einen Tag hinterher und melden morgens null |
| `ordering_policy` muss zum `--algo` passen, sonst Abbruch | der Schalter wurde schon einmal zurueckgerollt, zwei Laeden binnen zwoelf Sekunden |
| Plan A haengt an `order.system`, die ganze Leiter wird mitverschoben | sonst weicht die sichtbare Zahl von der App ab, und ein Tippen bewegt ploetzlich zwei Kisten |
| `plo`, `phi`, `expr`, `pcs` werden immer berechnet und geprueft | einmal genullt, die Seite zeigte Zahlen ohne Fragen |
| Kopfzeile muss genau einmal ersetzt werden, sonst Abbruch | die Beschriftung wurde auf "Ordersatz" umbenannt, der Datumsersatz lief ins Leere, die Seite zeigte den falschen Tag |
| keine erfundenen Flags | `is_inventory_count_mandatory` zeigt die App nicht, erzwang aber eine Pflichtzahl |
| A kommt bei classic aus `rqb + Bestand` | eine Rekonstruktion von A trifft die Produktion nur zu rund 90 % |

## Danach

Immer gegen das Telefon gegenpruefen, das ist die einzige Wahrheit. Zwei oder drei Artikel mit
unterschiedlichen Bestellmengen reichen. Aus den Daten allein laesst sich nicht entscheiden, was
die App anzeigt, und genau dort lagen an einem Tag drei falsche Schlussfolgerungen.
