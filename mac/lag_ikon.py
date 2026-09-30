"""Lager Golflager.icns (programikonet). Kjøres bare når ikonet skal endres:
    python3 mac/lag_ikon.py   (krever Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
HERE = Path(__file__).resolve().parent


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 100  # macOS-ikoner har luft rundt seg
    d.rounded_rectangle([pad, pad, SIZE - pad, SIZE - pad], radius=185, fill=(19, 61, 43, 255))
    # Green (litt lysere oval nederst)
    d.ellipse([230, 700, 800, 860], fill=(31, 106, 69, 255))
    # Hullet
    d.ellipse([470, 745, 560, 790], fill=(10, 36, 25, 255))
    # Flaggstang
    d.rounded_rectangle([395, 250, 425, 775], radius=15, fill=(255, 255, 255, 255))
    # Flagg
    d.polygon([(425, 262), (760, 375), (425, 488)], fill=(242, 194, 48, 255))
    return img


def main() -> None:
    img = draw()
    img.save(HERE / "Golflager.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128),
                                              (256, 256), (512, 512), (1024, 1024)])
    img.resize((256, 256), Image.LANCZOS).save(HERE / "ikon-forhåndsvisning.png")


if __name__ == "__main__":
    main()
