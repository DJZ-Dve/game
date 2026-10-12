#!/usr/bin/env python3
"""标牌用的黑体：从 blender/fonts/NotoSansSC-VF.ttf（SIL OFL）取 700 字重的静态实例，只留要用到的字，
存成 assets/fonts/NotoSansSC-Signs.ttf（几十 KB；整个字体 17 MB）。
要用到的字从 SOURCES 这几个脚本的字符串里找（加了新的标牌文字以后重跑一次）：
    python3 tools/gen_sign_font.py
"""
import re
import string
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ["scripts/shaft/lift_cab.gd"]
SRC_FONT = ROOT / "blender/fonts/NotoSansSC-VF.ttf"
OUT = ROOT / "assets/fonts/NotoSansSC-Signs.ttf"


def main() -> None:
    chars = set(string.ascii_letters + string.digits + string.punctuation + " ")
    for src in SOURCES:
        text = (ROOT / src).read_text(encoding="utf-8")
        for lit in re.findall(r'"([^"\n]*)"', text):
            chars.update(c for c in lit if ord(c) > 0x7F)
    font = TTFont(SRC_FONT)
    font = instancer.instantiateVariableFont(font, {"wght": 700})
    opts = subset.Options()
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    font.save(OUT)
    cjk = sorted(c for c in chars if ord(c) > 0x7F)
    print(f"{OUT.relative_to(ROOT)}：{len(chars)} 个字（非 ASCII：{''.join(cjk)}），{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
