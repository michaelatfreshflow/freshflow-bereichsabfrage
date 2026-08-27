
## Font notes

Both `AppFonts` families are real: `Inter` and `Euclid Circular` are declared in
`Mobile/pubspec.yaml` and bundled under `Mobile/assets/fonts/`. This prototype
renders entirely in **Inter** (`AppFonts.primary`), so only primary-font text
styles were used for matching -- naming a `secondary*` (Euclid) style for text
that is not set in Euclid would be misleading.

Tokens the app declares but never reads were excluded from matching, so every
`var(--ff-*)` in the prototype points at a style that actually has precedent in
the app. For reference, these exist in the theme but nothing uses them:
`primaryHeading30`, `primaryHeading32`, `primaryBigText38/48`,
`secondaryBodyText16`, `secondaryCaption10/12`, `secondaryHeading32`,
`textfieldHint`, `textfieldLabel`, plus the unread `AppColors` marked
`UNUSED in app` in `assets/ff-tokens.css`.

**Weight divergence worth a decision.** The prototype leans heavy; the app does
not:

| weight | prototype | app |
|---|---|---|
| medium (500) | 3 | 121 |
| semibold (600) | 21 | 118 |
| bold (700) | 34 | 31 |
| extraBold (800) | 16 | 1 |

The prototype's emphasis is roughly one step heavier than the app's house style.
Worth agreeing whether the screen really wants that, or whether these should
step down to `medium`/`semibold` on build.

The prototype was also loading Inter at 400-700 only, so its 16 uses of weight
800 were being *synthesised* by the browser. It now loads 800 as well, matching
the bundled `Inter-ExtraBold.ttf`, so what you see is what the app will render.

## Layout: what could NOT be tokenized, and why

Spacing, grid and sizing are raw px. There is no spacing scale to map them onto
-- `Mobile/lib/core/theme/` defines colours, fonts, weights and radii, but no
spacing or dimension file. In the app, spacing is written as literals at the
call site:

    SizedBox(height: 13.h)
    EdgeInsets.all(12).r
    mainAxisSpacing: 16.h, crossAxisSpacing: 21.w

So `gap: 11px` has no token equivalent. That is a gap in the design system, not
something this prototype can fix.

**Units.** Every dimension in the app is wrapped in a flutter_screenutil suffix
-- `.h` scales by height, `.w` by width, `.r` by the smaller. The px values here
are design-width values and need the same treatment.

## The shelf grid: written to be transcribed

`GridView` appears exactly once in the whole app (`VideoGrid`, tutorials), and the shelf
concept does not exist in the app at all -- "regal" appears only in config and mapper
files, never in UI. So this grid is new, and it has been written so it can be read
straight into Dart. Class names are English to match the codebase.

**Naming rule.** Each class is the widget it becomes; each `__part` is the local that
`build()` would name. `grep ShelfGridItem` finds the same component in both repos.

| CSS | Dart |
|---|---|
| `.ShelfGrid` | `GridView.builder` + `SliverGridDelegateWithFixedCrossAxisCount` |
| `.ShelfGridItem` | `_ShelfGridItem`: `InkWell > Container > Row` |
| `.ShelfGridItem__leading` | `ClipRRect(borderRadius: c8) > AppImage` |
| `.ShelfGridItem__body` | `Expanded > Column(crossAxisAlignment: start)` |
| `.ShelfGridItem__title` | `Text(...primaryBodyText14.bold.grey900)` |
| `.ShelfGridItem__meta` | `Row` |
| `.ShelfGridItem__statusDot` | `Container(shape: BoxShape.circle)` |
| `.ShelfGridItem__count` | `Text(...primaryCaption12.grey500)` |
| `.ShelfGridItem__badge` | `Tag(type: TagType.filled)` |
| `.ShelfGridItem--done` | the finished state |

The grid delegate's parameters are CSS custom properties with the delegate's own names:

    --cross-axis-count: 4;      ->  crossAxisCount: 4
    --main-axis-spacing: 11px;  ->  mainAxisSpacing: 11.h
    --cross-axis-spacing: 11px; ->  crossAxisSpacing: 11.w

Both the shelf picker and the item-to-shelf assignment screen use this one component --
in Flutter that is literally the same widget twice.

## Checked against the app: type, radius, elevation

### Headlines are NOT uppercased

The app uppercases UI text **exactly once** in the entire codebase -- a table column
caption in `store_logs_table.dart`. Strings in `intl_de_DE.arb` are plain sentence-case
German ("Vergangene Bestellungen", "Update verfügbar"). There is no Title Case and no
all-caps label pattern.

`letterSpacing` appears **3 times** in the whole app, and every one either resets it to
`0` or nudges it to `+0.4/+0.5`. Negative tracking is never used.

The prototype had five uppercase, letter-spaced labels and five negative-tracked
headings. All are now sentence case with normal tracking:

| was | now |
|---|---|
| `REGALE` | `Regale` |
| `REGAL ÄNDERN` | `Regal ändern` |
| `REGAL ABGESCHLOSSEN` | `Regal abgeschlossen` |
| `REGAL ABSCHLIESSEN` | `Regal abschließen` |
| `23 REGALE` (CSS transform) | `23 Regale` |

### Weight: bold, not extraBold

The app uses `.bold` 31 times and `.extraBold` once. The shelf view's headings and tile
titles moved from 800 to 700. The dashboard and the item table still use 800 in 11
places -- out of scope here, but the same argument applies to them.

### Heading sizes

The largest style the app actually uses in a screen is `primaryTitle18` (11 uses), then
`primaryHeading20` (4) and `primaryHeading24` (2). `primaryHeading30/32` and
`primaryBigText38/48` are declared but never used.

The shelf header sits at `primaryHeading24` -- in the app, but at its top end. Two
sizes in the completion overlay have no token at all: `30px` and `22px`. Left as-is,
flagged: a celebration moment arguably earns a bigger number, but it is a departure.

### Radius: c8 is the convention

`AppBorderRadius` usage across the app: **c8 52 uses**, c4 14, c40 6, c32 6, c25 5,
c35 3, c15 2, c12 1. The tile is now `c8`, matching both `AppCard` and the `VideoGrid`
item. `c12` is effectively unused -- do not reach for it.

### Elevation: already correct

I previously wrote that the app has no elevation convention. **That was wrong** -- I had
only looked at `AppCard` and the `VideoGrid` item. The app uses `BoxShadow` 33 times, and
the prototype's two shadows already match its vocabulary:

| prototype | app |
|---|---|
| `0 2px 6px rgba(0,0,0,.08)` | `Color(0x14000000)` -- the app's most common shadow, 5 uses |
| `0 2px 8px rgba(39,39,42,.118)` (hover) | `Color(0x1E27272A)` at `blurRadius: 8` -- `gradient_panel.dart` exactly |

Both become a `BoxShadow` inside the `BoxDecoration`. No change needed.

### Pressed state

Before this, the tile's only feedback was `:hover` — which never fires on the store's
iPad, so a tap gave no visual response at all.

    .ShelfGridItem:active { background: var(--ff-primary-20); }

It maps onto `InkWell`, which is how the app wraps every tappable surface (20+ uses in
`core/widgets` alone; `menu_button.dart` shows the `borderRadius` clipping pattern):

    InkWell(
      onTap: () => onShelfSelected(tile.id),
      borderRadius: AppBorderRadius.c8,          // clips the ripple to the card
      highlightColor: AppColors.primary.shade20, // held
      splashColor: AppColors.primary.shade30,    // the expanding ripple
      child: ...,
    )

Three deliberate constraints:

- **Background overlay only.** That is all `InkWell` can express without a
  `StatefulWidget` tracking the pressed state. Changing the border or shadow on press
  would look fine in CSS and then quietly cost a stateful wrapper to reproduce.
- **`shade20`, not `shade10`.** This screen is used at arm's length with a trolley in
  the other hand. `shade10` (`#f7fcf6`) is a 3% tint and reads as nothing under store
  lighting; `shade20` (`#d9e9de`) is unmistakable without shouting.
- **Set the colours explicitly in Dart.** Relying on Material's default splash would
  make the app and this prototype diverge again.

`-webkit-tap-highlight-color: transparent` is set on the tile so iOS's own grey flash
cannot fight the designed state, and `:hover` is now behind `@media (hover: hover)` so
it stays desktop polish and can never be a tap's only feedback.

### Behaviour contract

**One component, two callers.** The picker and the item-to-shelf sheet render the same
tile with different intents and different meta text. In Dart that is one widget with a
callback and a label, not a boolean:

    ShelfGrid({
      required List<ShelfTile> shelves,
      required ValueChanged<String> onShelfSelected,
      String? selectedId,                       // drives --done in the sheet
      required String Function(ShelfTile) metaLabel,
    })

The picker passes a count ("10 Artikel"); the sheet passes "aktuell"/"wählen". A bool
would collapse two different labels into one branch inside the widget.

**The shelf accent is a domain rule, not styling.** It was a copy-pasted ternary with
raw hexes at two call sites -- two places to get it wrong in Dart too. Now one function:

    Color shelfAccent(ShelfTile t) => switch (t.id) {
      'sonstiges' => AppColors.grey.shade500,
      _ => t.type == ShelfType.obst ? AppColors.accentLime : AppColors.accentGreen,
    };

Note `accentGreen`, not `primary.shade100` -- same value (`#429359`), but `accentGreen`
is what the app actually reaches for (4 uses; `primary.shade100` is referenced only
inside the theme file itself).

**Keys.** `data-key="shelf:<id>"` marks every tile, following the app's
`ValueKey('<name>:<id>')` convention in `app_keys.dart`:

    static Key shelf(String id) => ValueKey('shelf:$id');

**Strings.** Every visible string in this view now routes through `t()`, and each entry
in `T` carries its proposed `.arb` key as a trailing comment:

| string | proposed key |
|---|---|
| Regale | `shelfPickerEyebrow` |
| Wo bist du gerade? | `shelfPickerTitle` |
| {count} Regale | `shelfPickerShelfCountLabel` |
| {count} Artikel | `shelfGridItemItemCountLabel` |
| ✓ Fertig | `shelfGridItemDoneBadge` |
| aktuell | `shelfAssignCurrentLabel` |
| wählen | `shelfAssignChooseLabel` |

Verified by switching `LANG` at runtime: the whole view flips to English, so nothing is
still hardcoded in the markup.

### Still a deliberate departure

**4 columns**, where `VideoGrid` is 2-up. This screen is read at arm's length in the
store; 2-up doubles the scrolling. Keep, but it is a new grid spec.

**`padding: 9px`**, where the app's card convention is `EdgeInsets.all(12)`. 12 costs a
line of label text at 4-up. Left at 9 pending your call -- it is a one-line change.

### A layout bug fixed on the way

With the shelf thumbnails actually loaded, the grid overflowed its container:
`scrollWidth` 713 against a 574 px track set, so the fourth column ran off the edge. This
pre-dated the rewrite -- it was only invisible because the thumbnails 404 under `file://`
and `onerror` hides them, so the tiles were narrower in testing than they are in the store.

Cause: a CSS grid track's default minimum is `min-content`, so a long shelf name widened
its own column. `repeat(4, 1fr)` cannot prevent this; `repeat(4, minmax(0, 1fr))` can.

This is also the more faithful mapping. Flutter has no equivalent behaviour --
`SliverGridDelegateWithFixedCrossAxisCount` hands every cell a fixed width and lays the
child out inside it. Supporting rules, each with a Dart counterpart:

| CSS | Dart |
|---|---|
| `overflow-wrap: break-word` on `__title` | `Text(..., softWrap: true)` |
| `min-width: 0` on `__meta` | children shrink inside the fixed cell |
| `text-overflow: ellipsis` on `__count` | `Text(..., overflow: TextOverflow.ellipsis)` |

Verified at iPad width (1194x900) with thumbnails present: no overflow, and 0 of 23
titles wrap.

## The Bestand stepper: reuse, don't rebuild

`lib/presentation/shared/fields/column_counter_field.dart` already ships a
+/- counter, and its own doc comment says it is generic *"so the widget can drive
both order-flavoured counts and any future value-flavoured ones."* It is live in
`inv_sim_order_cell` and `inv_sim_preorder_cell`.

Its interaction split is already identical to this prototype's:

> "Only the value box opens the modal -- the +/- buttons keep their own taps… The
> +/- buttons do NOT focus the field at all."

That is exactly `data-a="bstep"` on the buttons versus `data-a="invpad"` on the box.
Arrived at independently, which is a good sign it is right.

**Build `InventoryCounterField` as a duplicate, not a modification.** The shared widget
is used by two other cells; widening it there would change them too.

| CSS | Dart |
|---|---|
| `.InventoryCounterField` | `DecoratedBox(borderRadius: c40, color: grey.shade100, border: …)` |
| `__button` | `_CounterButton`: `InkWell(borderRadius: c40) > Container(h38, pad h13) > AppIcon.asset(AppIcons.minus/plus)` |
| `__box` | `_ValueBox`: `Container(constraints: BoxConstraints.tight(Size(124, 40)), padding: h7, …)` |
| `__value` | `RichText`: value `primaryBodyText16.medium` + unit `primaryCaption12.light` |
| `__label` | the `label` slot `_ValueBox` already exposes |
| `--focused` | border `AppColors.accentOrange`, width 2 |
| `--warn` | untouched-warning border |

Everything -- colours, type, radii, icons, both radii -- is copied unchanged. The
icons are `Mobile/assets/icons/minus.svg` and `plus.svg` verbatim, with the hardcoded
`#34443F` swapped for `currentColor` so the disabled state can grey them.

### The one difference: width

The shared `_ValueBox` is `Size(72, 40)`, built for `"12"`. Measured across all 223
items in this order guide at the app's real type sizes, **218 of them need more room
than that box allows**:

| | |
|---|---|
| widest value line | 105 px — `10,64 – 11,6 KO` |
| widest label line | 77 px — `234 – 255 Stück` |
| box needed | 105 + 14 padding + 2 border = 121, rounded to **124** |

**Fixed, never auto.** Every stepper in the Bestand column has to line up; sizing each
box to its own content would leave the column ragged.

### Two things to watch in the Dart

**Box model.** `BoxConstraints.tight` is the *outer* size with padding inside, so 124
is the total. Written border-box here for the same reason -- with content-box the
focused state's 2 px border silently widens that one cell and breaks the column's
alignment. This actually happened while building the preview.

**The disabled visual.** `_CounterButton.onPressed` is already `VoidCallback?`, so
passing `null` disables the `InkWell` -- but the widget has no disabled appearance, so
a null callback goes dead silently. The grey (`grey.shade300`) is the one thing
`_CounterButton` needs adding, and this prototype already carries it.

### Which button greys out

Per-button, never both — straight from `stepHTML()`:

    minusOff = r.lo == null || r.lo <= 0;   // rung starts at zero
    plusOff  = r.hi == null;                // open-ended upward — the "mind." case

| | − | + |
|---|---|---|
| `mind. 1,1 KO` | live | greyed |
| `0 – 0,8 KO` | greyed | live |
| `1,1 – 2,3 KO` | live | live |
| `0 KO` typed | greyed | live |
| `need` / `unsure` | live | live |

Verified in the live page: 223 steppers, every box exactly 124 px, none clipped, 140 of
446 buttons greyed, keypad still opens on box tap, a disabled button is inert.

### Still inconsistent

The **Bestellung** column still uses the old `.step` markup, so the two columns no
longer match. In the app that cell is `inv_sim_order_cell`, which already uses
`ColumnCounterField` — so it should get the same treatment, probably with its own
measured width.

## The state machine

The behaviour behind the Bestand cell -- five item modes, three stepper views, two
warning markers -- is written up separately, with a state diagram:

  https://claude.ai/code/artifact/55dd250d-1a33-4c5d-8de3-8994d28f06bb

Source functions: `mode()`, `initState()`, `applyKo()`, `stepHTML()`, `rowClear()`,
`orderVal()`.

### Classification, first match wins

| # | mode | condition | items in live data |
|---|---|---|---|
| 1 | `noladder` | flag `KEINE LEITER`, or plan rung `kind === 'none'` | 0 |
| 2 | `count` | flag `ZÄHLEN` | 0 |
| 3 | `unsure` | app estimate outside the plan rung's band, or flag `PLAN A UNSICHER` | 0 |
| 4 | `any` | plan rung `kind === 'any'` | 42 |
| 5 | `ask` | everything else | 181 |

### Initial state

| mode | answered | auto | home |
|---|---|---|---|
| `ask` | true | true | `range` |
| `any` | true | false | `need` |
| `unsure` | false | false | `range` |
| `count` | false | false | `need` |
| `noladder` | false | false | `need` |

**Only `ask` and `any` occur in the real Dankenbring data.** All 223 items are one or
the other; no item carries any of the three flags, and every plan rung's app estimate
is in band. `count`, `noladder` and `unsure` are designed-for but have never been seen
on screen -- build them, but treat them as unvalidated.

### Two warning markers, independently driven

| marker | shows when | cleared by |
|---|---|---|
| Bestand | `!touched && (mode === 'unsure' \|\| it.invNote)` | any press or typed value, permanently |
| Bestellmenge | `!manual && it.ordNote` | editing the order quantity by hand |

A row is *erfasst* for shelf progress when neither shows (`rowClear`) -- deliberately
not the `answered` flag. Live data: 40 Bestand markers, 71 Bestellmenge markers.

### Open questions for Michael

1. Should the three unobserved modes ship at all?
2. Is silence consent? An untouched row orders the plan quantity -- true for 181 of 223 items.
3. Is *erfasst* the right progress signal, given it can disagree with `answered`?
4. Should `touched` stay sticky for the whole session?
