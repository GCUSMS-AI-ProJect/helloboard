# helloboard self-hosted fonts

English and Latin text uses **Inter Variable**. Simplified Chinese uses
**Noto Sans SC**. Both files are served by this device itself; visiting the site
does not contact Google Fonts, GitHub, or another font CDN.

These are open-source fonts chosen for clear, consistent rendering on Windows,
macOS, Android, and iOS. They are not Apple's San Francisco or PingFang fonts.

## Upstream sources

- Inter: [official rsms/inter repository](https://github.com/rsms/inter), commit
  `353b61b9f4430d5f420d56605a6e7993e0941470`.
  The unmodified `docs/font-files/InterVariable.woff2` identifies itself as
  version `4.001;git-9221beed3`. It contains variable weight 100–900 and optical
  size 14–32 axes. Copyright 2016 The Inter Project Authors.
- Noto Sans SC: [Google Fonts official source directory](https://github.com/google/fonts/tree/45e3d5269e4a17d823f6d84470bc084dc5ae46f6/ofl/notosanssc),
  commit `45e3d5269e4a17d823f6d84470bc084dc5ae46f6`.
  Source `NotoSansSC[wght].ttf` identifies itself as version
  `2.004-H2;hotconv 1.0.118;makeotfexe 2.5.65603`.
  Copyright 2014–2021 Adobe, with Reserved Font Name “Source”.

Redistribution and modification are governed by SIL Open Font License 1.1.
The full copyright and license notices are provided alongside the files as
`Inter-OFL.txt` and `NotoSansSC-OFL.txt`. Font copyright and license metadata
is also retained in the Chinese subsets.

## Font subsets

HelloBoard retains the pinned Inter binary as an on-demand extended fallback.
`tools/build_latin_fonts.py` derives an 893-character common Latin face (128,496
bytes) from it, preserving variable axes, hinting and license metadata. It covers
the usual English, numbers, Latin accents, punctuation and currency symbols.
Greek, Cyrillic and other Inter characters load the original face only when used;
the two faces have disjoint Unicode ranges. The preload requests just the core.

HelloBoard also retains the complete Noto fallback above.
The UI Noto face was rebuilt from the same pinned source with fontTools 4.67.0
and Brotli 1.2.1 using `tools/build_fonts.py`. It retains the variable weight axis;
the CSS uses weights 400–700. The 501-character UI subset is 130,152 bytes and
covers the templates, JavaScript and Python messages, plus the earlier UI core.
The full fallback retains weights 400–700. Exact, disjoint unicode ranges ensure
that only SSIDs containing additional characters request the complete face.
The original Inter fallback is 352,240 bytes. All font binaries are served locally
with immutable, hashed URLs; no CDN or external request is required. Normally the
two preloaded core faces total 258,648 bytes.
