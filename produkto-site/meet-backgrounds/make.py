"""Google Meet backgrounds (1920x1080). Run: python3 make.py"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
W, H = 1920, 1080
A = "../dist/assets/"

def glow(base, xy, r, color, alpha):
    layer = Image.new("RGBA", (W, H), color + (0,))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.ellipse((x - r, y - r, x + r, y + r), fill=color + (alpha,))
    return Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(r * 0.6)))

def font(size):
    for f in ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc"]:
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()

def make(name, bg, glows, logo_file, url_color):
    im = Image.new("RGBA", (W, H), bg + (255,))
    for g in glows: im = glow(im, *g)
    logo = Image.open(A + logo_file).convert("RGBA")
    logo = logo.crop(logo.getbbox())
    w = 420; logo = logo.resize((w, round(logo.height * w / logo.width)), Image.LANCZOS)
    im.alpha_composite(logo, (96, 88))
    d = ImageDraw.Draw(im)
    d.text((96, H - 96), "getprodukto.com", font=font(30), fill=url_color, anchor="ls")
    im.convert("RGB").save(name, quality=95)

# Navy: logo navy with soft blue light, like the site's navy sections
make("produkto-meet-navy.png", (11, 27, 53),
     [((1650, 160), 520, (46, 92, 170), 120), ((250, 1000), 460, (30, 60, 120), 90)],
     "produkto-wordmark-light.png", (170, 185, 210))
# Light: site background with a faint blue wash
make("produkto-meet-light.png", (250, 250, 248),
     [((1650, 160), 560, (205, 220, 245), 200), ((250, 1000), 480, (225, 232, 245), 160)],
     "produkto-wordmark-transparent.png", (90, 105, 130))
