"""Make every image MoneyThistle needs from the logo and wordmark artwork.

Run on a computer with Pillow (only this tool needs it; the app itself doesn't):
    python tools/make_brand.py path/to/logo.png path/to/wordmark.png

Writes:
  brand/logo-1024.png, brand/wordmark-2048.png   smaller masters kept with the project
  moneyapp/static/brand/logo-{64,128}.png         the mark in the header
  moneyapp/static/brand/wordmark-{450,900}.png    the sign-in screen (and README)
  moneyapp/static/icon-{180,192,512}.png          home-screen icons (logo on the header navy)
  moneyapp/static/icon-maskable-512.png           Android's cut-to-shape icon (logo in the safe middle)
  moneyapp/static/favicon-32.png                  the browser tab
"""

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, ".."))
STATIC = os.path.join(APP, "moneyapp", "static")
NAVY = (0x12, 0x32, 0x5F, 255)


def trimmed(path):
    """The artwork without its empty transparent margin."""
    im = Image.open(path).convert("RGBA")
    box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return im.crop(box) if box else im


def fit(im, size):
    """Scaled to fit a size x size square, centred, transparent around it."""
    im = im.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return out


def icon(logo, size, share, bg=NAVY):
    """The logo on a solid square (home screens show transparency as black)."""
    out = Image.new("RGBA", (size, size), bg)
    mark = fit(logo, round(size * share))
    out.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2), mark)
    return out.convert("RGB")


def width(im, w):
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def main(logo_path, word_path):
    os.makedirs(os.path.join(APP, "brand"), exist_ok=True)
    os.makedirs(os.path.join(STATIC, "brand"), exist_ok=True)
    logo, word = trimmed(logo_path), trimmed(word_path)
    fit(logo, 1024).save(os.path.join(APP, "brand", "logo-1024.png"), optimize=True)
    width(word, 2048).save(os.path.join(APP, "brand", "wordmark-2048.png"), optimize=True)
    for s in (64, 128):
        fit(logo, s).save(os.path.join(STATIC, "brand", f"logo-{s}.png"), optimize=True)
    for w in (450, 900):
        width(word, w).save(os.path.join(STATIC, "brand", f"wordmark-{w}.png"), optimize=True)
    for s in (180, 192, 512):
        icon(logo, s, 0.84).save(os.path.join(STATIC, f"icon-{s}.png"), optimize=True)
    icon(logo, 512, 0.62).save(os.path.join(STATIC, "icon-maskable-512.png"), optimize=True)
    fit(logo, 32).save(os.path.join(STATIC, "favicon-32.png"), optimize=True)
    print("brand images written")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
