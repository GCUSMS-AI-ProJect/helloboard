"""Split the bundled Inter into common Latin and on-demand extended coverage.

Build only: fonttools[woff]. Keep variable axes, hinting, names and OFL metadata.
Usage: python tools/build_latin_fonts.py
"""
from hashlib import sha256
from pathlib import Path
import re
from fontTools import subset
from fontTools.ttLib import TTFont
from build_fonts import ranges

FONTS = Path(__file__).resolve().parents[1] / 'static/fonts'


def main():
    fallback = next(FONTS.glob('inter-variable.*.woff2'))
    font = TTFont(fallback, recalcTimestamp=False)
    repertoire = set(font.getBestCmap())
    common = (set(range(0x250)) | set(range(0x1E00, 0x1F00))
              | set(range(0x2000, 0x2070)) | set(range(0x20A0, 0x20D0))
              | {0x2116, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193, 0x2212}) & repertoire
    options = subset.Options()
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17, 25]
    builder = subset.Subsetter(options=options)
    builder.populate(unicodes=common)
    builder.subset(font)
    font.flavor = 'woff2'
    temporary = FONTS / 'inter-building.woff2'
    font.save(temporary)
    name = f'inter-core.{sha256(temporary.read_bytes()).hexdigest()[:12]}.woff2'
    temporary.rename(FONTS / name)
    def face(filename, points):
        return ("@font-face {\n  font-family: 'HelloBoard Inter';\n  font-style: normal;\n"
                "  font-weight: 100 900;\n  font-display: swap;\n"
                f"  src: url('/static/fonts/{filename}') format('woff2');\n"
                f"  unicode-range: {ranges(points)};\n}}")
    css = (FONTS / 'fonts.css').read_text()
    pattern = r"@font-face\s*\{[^}]*font-family:\s*'HelloBoard Inter';[^}]*\}"
    matches = list(re.finditer(pattern, css))
    for match in reversed(matches[1:]): css = css[:match.start()] + css[match.end():]
    css = re.sub(pattern, lambda _: face(name, common) + '\n\n' + face(fallback.name, repertoire-common), css, count=1)
    (FONTS / 'fonts.css').write_text(css)
    for path in FONTS.glob('inter-core.*.woff2'):
        if path.name != name: path.unlink()
    print(f'{name}: {len(common)} characters, {(FONTS/name).stat().st_size} bytes; full fallback retained')


if __name__ == '__main__': main()
