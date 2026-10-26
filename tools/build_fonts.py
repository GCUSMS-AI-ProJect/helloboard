"""Build a small UI Chinese face; keep the complete face as on-demand fallback.
Build tool only: fonttools[woff]. Runtime has no font-building dependency.
Usage: python tools/build_fonts.py /path/to/NotoSansSC-wght.ttf
"""
from hashlib import sha256
from pathlib import Path
import re
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'static/fonts'


def ranges(points):
    groups = []
    start = end = None
    for point in sorted(points):
        if start is None:
            start = end = point
        elif point == end + 1:
            end = point
        else:
            groups.append((start, end))
            start = end = point
    if start is not None:
        groups.append((start, end))
    return ','.join(f'U+{a:X}' if a == b else f'U+{a:X}-{b:X}' for a, b in groups)


def main():
    source = TTFont(sys.argv[1], recalcTimestamp=False)
    repertoire = set(source.getBestCmap())
    old_core = list(FONTS.glob('noto-sans-sc-core.*.woff2'))
    points = set().union(*(set(TTFont(p).getBestCmap()) for p in old_core))
    files = list((ROOT / 'templates').glob('*.html')) + list((ROOT / 'static').glob('*.js')) + list(ROOT.glob('*.py'))
    points |= {ord(c) for p in files for c in p.read_text() if ord(c) > 127}
    points &= repertoire
    options = subset.Options()
    options.hinting = False
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17, 25]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=points)
    subsetter.subset(source)
    source.flavor = 'woff2'
    temporary = FONTS / 'core-building.woff2'
    source.save(temporary)
    name = f'noto-sans-sc-core.{sha256(temporary.read_bytes()).hexdigest()[:12]}.woff2'
    temporary.rename(FONTS / name)
    fallback = next(FONTS.glob('noto-sans-sc-fallback.*.woff2'))
    fallback_points = set(TTFont(fallback).getBestCmap()) - points
    css = (FONTS / 'fonts.css').read_text()
    css = re.sub(r'noto-sans-sc-core\.[a-f0-9]+\.woff2', name, css)
    # First Chinese face is the small UI font; the complete face is only requested
    # when an SSID contains characters absent from the UI repertoire.
    matches = list(re.finditer(r'unicode-range:\s*[^;]+;', css))
    for match, value in reversed(list(zip(matches, [ranges(points), ranges(fallback_points)]))):
        css = css[:match.start()] + 'unicode-range: ' + value + ';' + css[match.end():]
    (FONTS / 'fonts.css').write_text(css)
    for path in old_core:
        if path.name != name:
            path.unlink()
    print(f'{name}: {len(points)} glyphs, {(FONTS/name).stat().st_size} bytes')


if __name__ == '__main__': main()
