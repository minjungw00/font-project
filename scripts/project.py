#!/usr/bin/env python3
"""Pinned inputs, experimental full patch, and fail-closed font audit."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
CONFIG = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
VENDOR = ROOT / "vendor"
CACHE = ROOT / ".cache"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
MAX_GLYPHS = CONFIG["max_glyphs"]
IEC = {0x23FB, 0x23FC, 0x23FD, 0x23FE, 0x2B58}


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def fetch():
    CACHE.mkdir(exist_ok=True)
    VENDOR.mkdir(exist_ok=True)
    for key, spec in LOCK.items():
        archive = CACHE / spec["archive"]
        if not archive.exists() or digest(archive) != spec["sha256"]:
            tmp = archive.with_suffix(archive.suffix + ".part")
            request = urllib.request.Request(spec["url"], headers={"User-Agent": "font-project"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as out:
                    shutil.copyfileobj(response, out)
                if digest(tmp) != spec["sha256"]:
                    raise RuntimeError(f"SHA-256 mismatch: {archive.name}")
                tmp.replace(archive)
            finally:
                tmp.unlink(missing_ok=True)
        dest = VENDOR / key
        stamp = dest / ".source-sha256"
        if stamp.exists() and stamp.read_text().strip() == spec["sha256"]:
            print(f"{key}: already extracted")
            continue
        if dest.exists():
            raise RuntimeError(f"Remove or move stale extracted directory first: {dest}")
        with tempfile.TemporaryDirectory(dir=VENDOR) as temp:
            extracted = Path(temp) / "files"
            extracted.mkdir()
            if archive.suffix == ".zip":
                with zipfile.ZipFile(archive) as z:
                    for member in z.infolist():
                        target = (extracted / member.filename).resolve()
                        if not target.is_relative_to(extracted.resolve()):
                            raise RuntimeError("Unsafe archive member")
                    z.extractall(extracted)
            elif archive.suffix == ".7z":
                subprocess.run(["7z", "x", "-y", f"-o{extracted}", str(archive)], check=True)
            else:
                raise RuntimeError(f"Unsupported archive: {archive}")
            (extracted / ".source-sha256").write_text(spec["sha256"] + "\n")
            extracted.rename(dest)
        print(f"{key}: verified and extracted")


def one(paths, label):
    paths = list(paths)
    if len(paths) != 1:
        raise RuntimeError(f"Expected exactly one {label}, got {len(paths)}. Run fetch and inspect inputs.")
    return paths[0]


def normalized(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def source_font(style):
    wanted = normalized("Sarasa Fixed J " + style)
    candidates = []
    for p in (VENDOR / "sarasa").rglob("*.ttf"):
        if normalized(p.stem) == wanted:
            candidates.append(p)
    if not candidates:
        for p in (VENDOR / "sarasa").rglob("*.ttf"):
            with TTFont(p, lazy=True) as f:
                n = f["name"]
                full = n.getDebugName(4) or ""
                family = n.getBestFamilyName() or ""
                sub = n.getBestSubFamilyName() or ""
                if normalized(full) == wanted or normalized(family + " " + sub) == wanted:
                    candidates.append(p)
    return one(candidates, "Sarasa Fixed J " + style)


def symbols_font():
    return one((VENDOR / "symbols").rglob("SymbolsNerdFontMono-Regular.ttf"), "Symbols Nerd Font Mono")


def patcher():
    return one((VENDOR / "patcher").rglob("font-patcher"), "Nerd Fonts font-patcher")


def is_pua(cp):
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def is_mdi(cp):
    return 0xF0001 <= cp <= 0xF1AF0


def cmap(font):
    return font.getBestCmap() or {}


def icon_set(font):
    return {cp for cp in cmap(font) if is_pua(cp) or cp in IEC}


def uv_keys(font):
    return {(cp, selector) for t in font["cmap"].tables if t.format == 14
            for selector, entries in t.uvsDict.items() for cp, _ in entries}


def width(font, cp):
    name = cmap(font).get(cp)
    return None if name is None else font["hmtx"].metrics[name][0]


def codepoints(cps):
    return " ".join(f"U+{cp:04X}" for cp in sorted(cps)[:12])


def inspect(style):
    with TTFont(source_font(style)) as base, TTFont(symbols_font()) as donor:
        existing = set(cmap(base))
        icons = icon_set(donor)
        count = base["maxp"].numGlyphs
        missing = icons - existing
        print(json.dumps({
            "style": style,
            "source_glyphs": count,
            "source_codepoints": len(existing),
            "source_ivs": len(uv_keys(base)),
            "glyph_slots_remaining": MAX_GLYPHS - count,
            "source_halfwidth_units": width(base, ord("A")),
            "source_fullwidth_units": width(base, ord("한")),
            "source_hangul_syllables": sum(cp in existing for cp in range(0xAC00, 0xD7A4)),
            "donor_icon_codepoints": len(icons),
            "donor_material_design_codepoints": sum(is_mdi(cp) for cp in icons),
            "new_icon_codepoints": len(missing),
            "distinct_donor_glyphs_for_new_icons": len({cmap(donor)[cp] for cp in missing}),
            "note": "The final glyph count depends on actual patching, duplicates and auxiliary glyphs."
        }, ensure_ascii=False, indent=2))


def audit(base, result, donor):
    errors = []
    original, actual = cmap(base), cmap(result)
    expected = icon_set(donor)
    configured = {int(s, 16) for s in CONFIG["required_icons"]}
    required = expected | configured
    cell = width(base, ord("A"))
    if not cell or base["head"].unitsPerEm != result["head"].unitsPerEm:
        errors.append("Invalid cell or changed unitsPerEm")
        return errors
    if result["maxp"].numGlyphs > MAX_GLYPHS:
        errors.append("OpenType glyph limit exceeded")
    missing = set(original) - set(actual)
    if missing:
        errors.append(f"Original codepoints lost ({len(missing)}): {codepoints(missing)}")
    lost_ivs = uv_keys(base) - uv_keys(result)
    if lost_ivs:
        errors.append(f"Original IVS mappings lost: {len(lost_ivs)}")
    changed = {cp for cp in original.keys() & actual.keys() if width(base, cp) != width(result, cp)}
    if changed:
        errors.append(f"Original advances changed ({len(changed)}): {codepoints(changed)}")
    missing_hangul = set(range(0xAC00, 0xD7A4)) - set(actual)
    if missing_hangul:
        errors.append(f"Hangul syllables missing: {len(missing_hangul)}")
    for chars, units in [('Ai w0123"—', 1), ("한글日本語あいうアイウ", 2)]:
        for ch in chars:
            if width(result, ord(ch)) != units * cell:
                errors.append(f"Unexpected advance for U+{ord(ch):04X}: expected {units * cell}")
    absent = required - set(actual)
    if absent:
        errors.append(f"Expected icon codepoints missing ({len(absent)}): {codepoints(absent)}")
    if "glyf" not in result:
        errors.append("Expected static TrueType glyf outlines")
        return errors
    glyf = result["glyf"]
    bad_width, overhang, empty = set(), set(), set()
    # A non-PUA IEC symbol already present in Sarasa is not replaced by the patcher.
    # Preserve the original rather than silently forcing its width.
    for cp in required & set(actual):
        if cp in original and not is_pua(cp):
            continue
        name = actual[cp]
        if width(result, cp) != cell:
            bad_width.add(cp)
        g = glyf[name]
        g.recalcBounds(glyf)
        if not hasattr(g, "xMin") or (g.xMin == g.xMax and g.yMin == g.yMax):
            empty.add(cp)
            continue
        lsb = result["hmtx"].metrics[name][1]
        if lsb < 0 or lsb + g.xMax - g.xMin > cell:
            overhang.add(cp)
    for label, cps in [("Icon advance mismatch", bad_width), ("Icon overhang", overhang), ("Empty icon", empty)]:
        if cps:
            errors.append(f"{label} ({len(cps)}): {codepoints(cps)}")
    return errors


def shape_check(path):
    errors = []
    if not shutil.which("hb-shape"):
        return ["hb-shape missing; install libharfbuzz-bin"]
    features = "-liga,-clig,-dlig,-hlig,-calt,-rclt,-rlig"
    for sample in CONFIG["shape_samples"]:
        def shape(extra):
            cmd = ["hb-shape", "--output-format=json", "--no-glyph-names", *extra, str(path), sample]
            return json.loads(subprocess.check_output(cmd, text=True))
        normal = shape([])
        disabled = shape(["--features=" + features])
        if len(normal) != len(sample) or normal != disabled:
            errors.append(f"Unexpected coding substitution: {sample}")
    return errors


def verify(style, output):
    with TTFont(source_font(style)) as base, TTFont(output) as result, TTFont(symbols_font()) as donor:
        print(f"Result: {result['maxp'].numGlyphs} glyphs")
        print(f"Family: {result['name'].getBestFamilyName()}")
        errors = audit(base, result, donor)
        if result["name"].getBestFamilyName() != CONFIG["family"]:
            errors.append("Unexpected font family name")
    errors.extend(shape_check(output))
    if errors:
        raise RuntimeError("Font audit failed:\n- " + "\n- ".join(errors))
    print("PASS: structural checks and representative coding strings")


def rename_font(base_path, input_path, output_path, style):
    family = CONFIG["family"]
    version = CONFIG["version"]
    full = f"{family} {style}"
    ps = re.sub(r"[^A-Za-z0-9-]", "", family) + "-" + style.replace(" ", "")
    replacements = {1: family, 2: style, 3: f"{ps}-{version}", 4: full,
                    5: f"Version {version}", 6: ps, 16: family, 17: style,
                    18: full, 21: family, 22: style}
    with TTFont(input_path, recalcTimestamp=False) as out, TTFont(base_path) as base:
        name = out["name"]
        for record in list(name.names):
            if record.nameID in replacements:
                name.setName(replacements[record.nameID], record.nameID,
                             record.platformID, record.platEncID, record.langID)
        for name_id, value in replacements.items():
            name.setName(value, name_id, 3, 1, 0x409)
        # Restore original copyright and license records where they were omitted or modified.
        for record in base["name"].names:
            if record.nameID in (0, 13, 14):
                name.setName(record.toUnicode(), record.nameID,
                             record.platformID, record.platEncID, record.langID)
        if "DSIG" in out:
            del out["DSIG"]
        out.save(output_path)


def build(style):
    base = source_font(style)
    inspect(style)
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    final = DIST / (normalized(CONFIG["family"]) + "-" + style.replace(" ", "") + ".ttf")
    if final.exists():
        raise RuntimeError(f"Move existing result before rebuilding: {final}")
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        stage = Path(tmp)
        raw_dir = stage / "patched"
        raw_dir.mkdir()
        script = patcher()
        subprocess.run([
            "fontforge", "-lang=py", "-script", str(script), str(base),
            "--complete", "--single-width-glyphs", "--careful", "--no-progressbars",
            "--extension", "ttf", "--outputdir", str(raw_dir),
            "--name", f"{CONFIG['family']} {style}"
        ], cwd=script.parent, check=True)
        raw = one(raw_dir.rglob("*.ttf"), "patched TTF")
        candidate = stage / "candidate.ttf"
        rename_font(base, raw, candidate, style)
        verify(style, candidate)
        candidate.replace(final)
        print(f"Verified development font: {final}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch")
    for cmd in ("inspect", "build", "verify"):
        p = sub.add_parser(cmd)
        p.add_argument("--style", choices=CONFIG["styles"], default="Regular")
        if cmd == "verify":
            p.add_argument("font", type=Path)
    args = parser.parse_args()
    if args.command == "fetch":
        fetch()
    elif args.command == "inspect":
        inspect(args.style)
    elif args.command == "build":
        build(args.style)
    else:
        verify(args.style, args.font.resolve())


if __name__ == "__main__":
    main()
