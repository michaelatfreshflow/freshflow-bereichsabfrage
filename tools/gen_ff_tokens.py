#!/usr/bin/env python3
"""Generate assets/ff-tokens.css from the Flutter app's Dart theme files.

The design system lives in code in the Mobile repo, not in this one. Rather than
copying values by hand (and letting them rot), this reads the Dart source and
emits CSS custom properties named after the Dart identifiers, so a value in the
prototype can be traced back to exactly one token in the app.

Usage:
    python3 tools/gen_ff_tokens.py [--mobile /path/to/Mobile]

Caveat on sizes: the app uses flutter_screenutil, so `16.sp` is 16px only at the
design width. For a static prototype we treat 1.sp as 1px.
"""

import argparse
import json
import pathlib
import re
import sys

DEFAULT_MOBILE = pathlib.Path("/Users/michael/Github/Mobile")
REPO = pathlib.Path(__file__).resolve().parent.parent


def kebab(name):
    """primaryBodyText16 -> primary-body-text-16"""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", "-", name)
    s = re.sub(r"(?<=[A-Za-z])(?=\d)", "-", s)
    return s.lower()


def argb_to_css(hex_str):
    """0xFFE65050 -> #e65050 ; 0x1E27272A -> rgba(39,39,42,0.118)"""
    v = int(hex_str, 16)
    a, r, g, b = (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
    if a == 0xFF:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d, %d, %d, %.3f)" % (r, g, b, a / 255)


def read(path):
    if not path.exists():
        sys.exit("missing Dart source: %s" % path)
    return path.read_text(encoding="utf-8")


def parse_colors(src):
    """-> (flat {name: css}, swatches {swatch: {shade: css}}, aliases {name: target})"""
    flat, swatches, aliases = {}, {}, {}

    for name, hx in re.findall(
        r"static\s+const\s+Color\s+(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)", src
    ):
        flat[name] = argb_to_css(hx)

    for name, hx in re.findall(
        r"static\s+const\s+Color\s+(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{6})\)\s*;", src
    ):
        flat.setdefault(name, argb_to_css("FF" + hx))

    # static const Map<int, Color> _greyColorSwatchMap = { 50: Color(0xFF...), ... }
    for raw_name, body in re.findall(
        r"static\s+const\s+Map<int,\s*Color>\s+_(\w+?)(?:Color)?SwatchMap\s*=\s*"
        r"<int,\s*Color>\{(.*?)\};",
        src,
        re.S,
    ):
        shades = {
            int(k): argb_to_css(hx)
            for k, hx in re.findall(r"(\d+):\s*Color\(0x([0-9A-Fa-f]{8})\)", body)
        }
        if shades:
            swatches[raw_name] = shades

    # static const MaterialColor primary = MaterialColor(0xFF306A57, _primarySwatchMap);
    for name, hx, swatch in re.findall(
        r"static\s+const\s+MaterialColor\s+(\w+)\s*=\s*"
        r"\n?\s*MaterialColor\(0x([0-9A-Fa-f]{8}),\s*_(\w+?)(?:Color)?SwatchMap\)",
        src,
    ):
        flat[name] = argb_to_css(hx)
        if swatch in swatches and name != swatch:
            swatches[name] = swatches.pop(swatch)

    # static final Color accentPrimary = primary.shade100;
    for name, swatch, shade in re.findall(
        r"static\s+final\s+Color\s+(\w+)\s*=\s*(\w+)\.shade(\d+)\s*;", src
    ):
        aliases[name] = (swatch, int(shade))

    # final Color kHintColor = AppColors.grey.shade500;   (top-level, app_theme.dart)
    for name, swatch, shade in re.findall(
        r"(?:final|const)\s+Color\s+(k\w+)\s*=\s*AppColors\.(\w+)\.shade(\d+)\s*;", src
    ):
        aliases[name] = (swatch, int(shade))

    return flat, swatches, aliases


def parse_text_styles(src):
    """-> {styleName: (px, 'primary'|'secondary'|None)}"""
    out = {}
    block = re.search(r"class AppTextTheme\s*\{(.*?)\n\}", src, re.S)
    if not block:
        return out
    for name, body in re.findall(
        r"final\s+TextStyle\s+(\w+)\s*=\s*\n?\s*TextStyle\((.*?)\);", block.group(1), re.S
    ):
        m = re.search(r"fontSize:\s*([\d.]+)\.sp", body)
        if not m:
            continue
        fam = None
        if "_secondaryFontFamily" in body:
            fam = "secondary"
        elif "_fontFamily" in body:
            fam = "primary"
        out[name] = (float(m.group(1)), fam)
    return out


def parse_weights(src):
    return {
        n: int(w)
        for n, w in re.findall(
            r"static\s+const\s+FontWeight\s+(\w+)\s*=\s*FontWeight\.w(\d+)", src
        )
    }


def parse_radii(src):
    out = {}
    for n, px in re.findall(
        r"static\s+(?:final|const)\s+BorderRadius\s+(c\d+)\s*=\s*BorderRadius\.circular\((\d+)\)",
        src,
    ):
        out[n] = int(px)
    for n, px in re.findall(
        r"static\s+(?:final|const)\s+Radius\s+(r\d+)\s*=\s*const\s+Radius\.circular\((\d+)\)",
        src,
    ):
        out[n] = int(px)
    return out


def count_usage(lib_dir, color_names, swatch_names, style_names):
    """How often each token is actually referenced in the app.

    A token that exists in the theme but is never read is aspirational, not a
    design decision -- pointing a prototype at one is worse than leaving the
    value raw, because it implies a precedent that does not exist.
    """
    blob = []
    for f in lib_dir.rglob("*.dart"):
        if f.name in ("app_colors.dart", "app_theme.dart", "app_style.dart",
                      "app_border_radius.dart", "app_fonts.dart"):
            continue
        try:
            blob.append(f.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    blob = "\n".join(blob)

    colors = {n: blob.count("AppColors.%s" % n) for n in color_names}
    # A bare `AppColors.primary` is the MaterialColor's own value, which equals
    # one of its shades. Without this, the app's most-used brand colour reads as
    # unused just because nobody spells it `.shade500`.
    bare = {n: len(re.findall(r"AppColors\.%s\b(?!\.shade)" % n, blob))
            for n in swatch_names}
    styles = {n: blob.count("text.%s" % n) for n in style_names}
    swatches = {}
    for sw, shades in swatch_names.items():
        for sh in shades:
            # AppColors.grey.shade500  and the TextStyle extension .grey500
            swatches["%s-%d" % (sw, sh)] = (
                blob.count("AppColors.%s.shade%d" % (sw, sh))
                + len(re.findall(r"\.%s%d\b" % (sw, sh), blob))
            )
    return colors, swatches, styles, bare


def parse_fonts(src):
    return dict(re.findall(r"static\s+const\s+String\s+(\w+)\s*=\s*'([^']+)'", src))


def num(x):
    return "%g" % x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mobile", type=pathlib.Path, default=DEFAULT_MOBILE)
    ap.add_argument("--out", type=pathlib.Path, default=REPO / "assets" / "ff-tokens.css")
    args = ap.parse_args()

    theme_dir = args.mobile / "lib" / "core" / "theme"
    colors_src = read(theme_dir / "app_colors.dart")
    theme_src = read(theme_dir / "app_theme.dart")

    flat, swatches, aliases = parse_colors(colors_src + "\n" + theme_src)
    styles = parse_text_styles(theme_src)
    weights = parse_weights(read(theme_dir / "app_style.dart"))
    radii = parse_radii(read(theme_dir / "app_border_radius.dart"))
    fonts = parse_fonts(read(theme_dir / "app_fonts.dart"))

    use_colors, use_swatches, use_styles, use_bare = count_usage(
        args.mobile / "lib", set(flat), {k: set(v) for k, v in swatches.items()}, set(styles)
    )

    # credit a bare MaterialColor reference to the shade that carries its value
    for sw, n in use_bare.items():
        if not n or sw not in swatches or sw not in flat:
            continue
        for shade, css in swatches[sw].items():
            if css == flat[sw]:
                use_swatches["%s-%d" % (sw, shade)] = (
                    use_swatches.get("%s-%d" % (sw, shade), 0) + n)
                break

    resolved = dict(flat)
    for name, (swatch, shade) in aliases.items():
        if swatch in swatches and shade in swatches[swatch]:
            resolved[name] = swatches[swatch][shade]

    L = []
    w = L.append
    w("/* GENERATED by tools/gen_ff_tokens.py -- do not edit by hand.")
    w("   Source of truth: Mobile/lib/core/theme/*.dart")
    w("   Regenerate:      python3 tools/gen_ff_tokens.py")
    w("")
    w("   Every value below exists in the Flutter app. If a value in a prototype")
    w("   is NOT one of these, that is a deliberate new design decision and must")
    w("   be added to the Dart theme before it ships. */")
    w("")
    w(":root {")

    w("  /* --- font families (AppFonts) --- */")
    fallback = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    for n, fam in sorted(fonts.items()):
        w("  --ff-font-%s: '%s', %s;" % (kebab(n), fam, fallback))

    w("")
    w("  /* --- color swatches (AppColors.<swatch>.shade<n>) --- */")
    for swatch in sorted(swatches):
        for shade in sorted(swatches[swatch]):
            u = use_swatches.get("%s-%d" % (swatch, shade), 0)
            w("  --ff-%s-%d: %s;%s" % (kebab(swatch), shade, swatches[swatch][shade],
                                        "" if u else "  /* UNUSED in app */"))

    w("")
    w("  /* --- named colors (AppColors.<name>) --- */")
    for n in sorted(resolved):
        note = ""
        if n in aliases:
            note = "  /* = %s.shade%d */" % (aliases[n][0], aliases[n][1])
        if not use_colors.get(n, 0) and n not in aliases:
            note += "  /* UNUSED in app */"
        w("  --ff-color-%s: %s;%s" % (kebab(n), resolved[n], note))

    w("")
    w("  /* --- type scale (AppTheme.text.<style>) --- */")
    for n in sorted(styles):
        px, fam = styles[n]
        u = use_styles.get(n, 0)
        note = "  /* %s font" % fam if fam else "  /*"
        note += ", %s */" % ("%dx in app" % u if u else "UNUSED in app")
        w("  --ff-text-%s: %spx;%s" % (kebab(n), num(px), note))

    w("")
    w("  /* --- font weights (AppFontWeight) --- */")
    for n in sorted(weights, key=lambda k: weights[k]):
        w("  --ff-weight-%s: %d;" % (kebab(n), weights[n]))

    w("")
    w("  /* --- border radii (AppBorderRadius) --- */")
    for n in sorted(radii, key=lambda k: (k[0], int(k[1:]))):
        w("  --ff-radius-%s: %dpx;" % (n, radii[n]))

    w("}")
    w("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(L), encoding="utf-8")

    index = {
        "colors": {"--ff-color-%s" % kebab(n): v for n, v in resolved.items()},
        "swatches": {
            "--ff-%s-%d" % (kebab(s), sh): v
            for s in swatches
            for sh, v in swatches[s].items()
        },
        "text": {"--ff-text-%s" % kebab(n): styles[n][0] for n in styles},
        "text_family": {"--ff-text-%s" % kebab(n): (styles[n][1] or "primary")
                        for n in styles},
        "usage": dict(
            [("--ff-color-%s" % kebab(n), use_colors.get(n, 0)) for n in resolved]
            + [("--ff-%s" % kebab(k), v) for k, v in use_swatches.items()]
            + [("--ff-text-%s" % kebab(n), use_styles.get(n, 0)) for n in styles]
        ),
        "weights": {"--ff-weight-%s" % kebab(n): weights[n] for n in weights},
        "radii": {"--ff-radius-%s" % n: radii[n] for n in radii},
    }
    (args.out.parent / "ff-tokens.json").write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(
        "wrote %s\n  %d swatch steps, %d named colors, %d text sizes, "
        "%d weights, %d radii"
        % (
            args.out,
            len(index["swatches"]),
            len(index["colors"]),
            len(index["text"]),
            len(index["weights"]),
            len(index["radii"]),
        )
    )


if __name__ == "__main__":
    main()
