# Bundled fonts

`NotoEmoji-subset.ttf` is a **subset** of Google's monochrome
[Noto Emoji](https://fonts.google.com/noto/specimen/Noto+Emoji) variable font,
pinned to the Regular weight and cut down to just the three symbol codepoints
GPXSheet draws on the map strip:

| glyph | codepoint | use   |
|-------|-----------|-------|
| ⛽    | U+26FD    | fuel  |
| ⛴    | U+26F4    | ferry |
| 🍴    | U+1F374   | food  |

The stock DejaVu Sans bundled with matplotlib covers none of these, so the
renderer registers this subset as a per-glyph fallback (see
`gpxsheet.strip._use_bundled_fonts`). Subsetting keeps the vendored file tiny
(~4 KB vs ~2 MB) while making PDF/PNG output identical across machines without
depending on any system-installed emoji font.

## Licence

Noto Emoji is licensed under the SIL Open Font License v1.1 — see `OFL.txt`.
The subset is a derivative under the same licence; "Noto" is a Google trademark.

## Regenerating the subset

```python
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.subset import Subsetter, Options

CPS = [0x26FD, 0x26F4, 0x1F374]  # fuel, ferry, food
src = TTFont("NotoEmoji[wght].ttf")               # google/fonts ofl/notoemoji
inst = instancer.instantiateVariableFont(src, {"wght": 400}, inplace=False)
opts = Options(); opts.name_IDs = ["*"]; opts.glyph_names = False
ss = Subsetter(options=opts); ss.populate(unicodes=CPS); ss.subset(inst)
inst.save("NotoEmoji-subset.ttf")
```
