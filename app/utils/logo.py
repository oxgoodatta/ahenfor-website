"""Automatic logo clean-up.

Logo files often come with a white (or off-white) margin around the drawing.
That margin counts towards the height set in CSS, so the visible icon looks
smaller than the text beside it and a faint grey box shows on the white navbar.

prepare_logo() crops the empty margin, makes the near-white background
transparent and caches the result in instance/brand/. It re-runs only when
app/static/images/logo.png (or .jpg/.webp) changes. SVG logos are used as-is.
"""
import logging
import os

from PIL import Image, ImageChops

log = logging.getLogger(__name__)

RASTER_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")
WHITE_THRESHOLD = 232   # channels above this count as background
PADDING = 2             # px kept around the drawing after cropping
CACHE_NAME = "logo.png"


def find_source(static_root):
    for name in RASTER_NAMES:
        path = os.path.join(static_root, "images", name)
        if os.path.exists(path):
            return path
    return None


def _clean(src_path, dst_path):
    with Image.open(src_path) as im:
        im = im.convert("RGBA")
    r, g, b, a = im.split()
    # Pixels that are near-white (or already transparent) are background.
    light = Image.eval(ImageChops.darker(ImageChops.darker(r, g), b), lambda v: 255 if v > WHITE_THRESHOLD else 0)
    clear = Image.eval(a, lambda v: 255 if v < 16 else 0)
    background = ImageChops.lighter(light, clear)
    foreground = Image.eval(background, lambda v: 255 - v)
    box = foreground.getbbox()
    if box:
        left, top, right, bottom = box
        box = (max(0, left - PADDING), max(0, top - PADDING),
               min(im.width, right + PADDING), min(im.height, bottom + PADDING))
        im = im.crop(box)
        background = background.crop(box)
    # Make the background transparent so the logo sits cleanly on any light surface.
    alpha = ImageChops.multiply(im.getchannel("A"), Image.eval(background, lambda v: 255 - v))
    im.putalpha(alpha)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    tmp = dst_path + ".tmp"
    im.save(tmp, "PNG", optimize=True)
    os.replace(tmp, dst_path)


def prepare_logo(static_root, instance_path):
    """Return (path_to_cleaned_png, version) or None when there is no raster logo."""
    src = find_source(static_root)
    if src is None:
        return None
    dst = os.path.join(instance_path, "brand", CACHE_NAME)
    src_mtime = int(os.path.getmtime(src))
    try:
        if not os.path.exists(dst) or int(os.path.getmtime(dst)) < src_mtime:
            _clean(src, dst)
            os.utime(dst, (src_mtime, src_mtime))
    except (OSError, ValueError) as exc:
        log.warning("Could not prepare the logo (%s); using the original file.", exc)
        return src, src_mtime
    return dst, src_mtime


FAVICON_SIZES = (32, 180, 512)


def prepare_favicon(static_root, instance_path, size=180):
    """Square icon made from the cleaned logo, centred on a white tile.

    A white tile keeps the dark logo visible on dark browser tabs. Returns
    (path, version) or None when there is no raster logo.
    """
    if size not in FAVICON_SIZES:
        size = 180
    prepared = prepare_logo(static_root, instance_path)
    if prepared is None:
        return None
    src, version = prepared
    dst = os.path.join(instance_path, "brand", f"favicon-{size}.png")
    try:
        if not os.path.exists(dst) or int(os.path.getmtime(dst)) < version:
            with Image.open(src) as logo:
                logo = logo.convert("RGBA")
                inner = int(size * 0.84)
                logo.thumbnail((inner, inner), Image.Resampling.LANCZOS)
                tile = Image.new("RGBA", (size, size), (255, 255, 255, 255))
                tile.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".tmp"
            tile.save(tmp, "PNG", optimize=True)
            os.replace(tmp, dst)
            os.utime(dst, (version, version))
    except (OSError, ValueError) as exc:
        log.warning("Could not build the favicon (%s).", exc)
        return None
    return dst, version
