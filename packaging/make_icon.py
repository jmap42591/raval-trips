"""Developer tool: draw the app icon (packaging/icon.png, icon.ico, icon.icns on macOS)."""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent
N = 1024


def draw():
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    # rounded square with a vertical green gradient
    grad = Image.new("RGBA", (N, N))
    gp = grad.load()
    for y in range(N):
        t = y / (N - 1)
        c = (int(18 + 20 * t), int(166 - 45 * t), int(120 - 25 * t), 255)
        for x in range(N):
            gp[x, y] = c
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, N - 40, N - 40), radius=210, fill=255)
    img.paste(grad, (0, 0), mask)
    # lightning bolt
    d = ImageDraw.Draw(img)
    bolt = [(585, 170), (330, 560), (500, 560), (440, 860), (700, 450), (530, 450)]
    d.polygon(bolt, fill=(255, 255, 255, 255))
    return img


img = draw()
img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
if sys.platform == "darwin" and shutil.which("iconutil"):
    iconset = OUT / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        img.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        img.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
    shutil.rmtree(iconset)
print("icons written to", OUT)
