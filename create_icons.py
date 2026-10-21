"""
Script to generate ultra-sharp, multi-resolution modern application icons for
Turbo Download Manager Pro.
Generates:
  - app_icon.ico (16, 24, 32, 48, 64, 128, 256)
  - app_icon.png (256x256)
  - extension/icons/icon16.png
  - extension/icons/icon48.png
  - extension/icons/icon128.png
"""
import os
import math
from PIL import Image, ImageDraw, ImageFilter

def generate_master_icon(size=1024) -> Image.Image:
    # 1024x1024 master canvas with RGBA transparency
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Subtle glowing outer ring
    for i in range(12):
        alpha = int(18 * (1.0 - i / 12.0))
        offset = 36 - i * 3
        draw.rounded_rectangle(
            [offset, offset, size - offset, size - offset],
            radius=220 + i * 2,
            outline=(56, 189, 248, alpha),
            width=3
        )

    # 2. Main rounded squircle container
    box = [48, 48, size - 48, size - 48]
    corner_radius = 210

    # Draw gradient background (Slate 900 -> Slate 800)
    bg_mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(bg_mask)
    mask_draw.rounded_rectangle(box, radius=corner_radius, fill=255)

    gradient = Image.new("RGBA", (size, size))
    g_draw = ImageDraw.Draw(gradient)
    top_color = (15, 23, 42, 255)      # #0f172a
    bot_color = (30, 41, 59, 255)      # #1e293b
    for y in range(size):
        ratio = y / float(size)
        r = int(top_color[0] + (bot_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bot_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bot_color[2] - top_color[2]) * ratio)
        g_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    img.paste(gradient, (0, 0), bg_mask)

    # 3. Inner border with metallic/neon sky accent
    draw.rounded_rectangle(box, radius=corner_radius, outline=(56, 189, 248, 200), width=8)
    inner_box = [box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8]
    draw.rounded_rectangle(inner_box, radius=corner_radius - 6, outline=(2, 132, 199, 120), width=4)

    # 4. Modern Turbo Lightning + Download Arrow Motif
    # Lightning bolt (Turbo energy) angled in top-right / center
    bolt_pts = [
        (590, 150),
        (390, 460),
        (510, 460),
        (430, 720),
        (660, 390),
        (540, 390),
        (620, 150),
    ]

    # Download chevron / arrow head at base
    arrow_pts = [
        (512, 790),   # Bottom tip
        (320, 560),   # Left wing
        (410, 560),   # Left inner
        (512, 680),   # Center notch
        (614, 560),   # Right inner
        (704, 560),   # Right wing
    ]

    # Arrow shaft (vertical download beam)
    shaft_pts = [
        (470, 260),
        (554, 260),
        (554, 580),
        (470, 580),
    ]

    # Draw download beam with emerald/cyan gradient
    draw.polygon(shaft_pts, fill=(56, 189, 248, 220))

    # Draw arrow head
    draw.polygon(arrow_pts, fill=(56, 189, 248, 255))
    draw.polygon(arrow_pts, outline=(255, 255, 255, 200), width=6)

    # Draw glowing lightning bolt cutting dynamically across
    # Glow layer
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.polygon(bolt_pts, fill=(56, 189, 248, 160))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(glow)

    # Crisp lightning bolt core (Cyan to bright electric amber/white)
    draw.polygon(bolt_pts, fill=(56, 189, 248, 250))
    # Inner bright core
    inner_bolt_pts = [
        (585, 175),
        (415, 450),
        (515, 450),
        (455, 680),
        (640, 400),
        (545, 400),
        (610, 175),
    ]
    draw.polygon(inner_bolt_pts, fill=(240, 249, 255, 255))

    # 5. Base speed indicator segments (IDM dynamic chunking aesthetic)
    seg_y = 835
    seg_h = 24
    seg_w = 64
    spacing = 18
    start_x = 512 - ((seg_w * 4 + spacing * 3) // 2)

    colors = [
        (16, 185, 129, 240),  # Emerald 500
        (16, 185, 129, 240),  # Emerald 500
        (56, 189, 248, 240),  # Sky 400
        (56, 189, 248, 240),  # Sky 400
    ]

    for idx, col in enumerate(colors):
        sx = start_x + idx * (seg_w + spacing)
        draw.rounded_rectangle(
            [sx, seg_y, sx + seg_w, seg_y + seg_h],
            radius=8,
            fill=col,
            outline=(255, 255, 255, 80),
            width=2
        )

    return img

def main():
    print("Generating master 1024x1024 icon...")
    master = generate_master_icon(1024)

    # Master PNG
    icon256 = master.resize((256, 256), Image.Resampling.LANCZOS)
    icon256.save("app_icon.png", format="PNG")
    print("Saved app_icon.png (256x256)")

    # Multi-resolution ICO: 16, 24, 32, 48, 64, 128, 256
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(
        "app_icon.ico",
        format="ICO",
        sizes=sizes
    )
    print(f"Saved app_icon.ico with {len(sizes)} resolutions: {sizes}")

    # Also update extension icons
    os.makedirs("extension/icons", exist_ok=True)
    master.resize((16, 16), Image.Resampling.LANCZOS).save("extension/icons/icon16.png", format="PNG")
    master.resize((48, 48), Image.Resampling.LANCZOS).save("extension/icons/icon48.png", format="PNG")
    master.resize((128, 128), Image.Resampling.LANCZOS).save("extension/icons/icon128.png", format="PNG")
    print("Updated extension/icons/ (16, 48, 128)")

    # Also copy to dist if dist exists
    if os.path.isdir("dist/extension/icons"):
        master.resize((16, 16), Image.Resampling.LANCZOS).save("dist/extension/icons/icon16.png", format="PNG")
        master.resize((48, 48), Image.Resampling.LANCZOS).save("dist/extension/icons/icon48.png", format="PNG")
        master.resize((128, 128), Image.Resampling.LANCZOS).save("dist/extension/icons/icon128.png", format="PNG")
        print("Updated dist/extension/icons/ (16, 48, 128)")

if __name__ == "__main__":
    main()
