"""
Script to generate ultra-sharp, multi-resolution modern application icons for
Smart Download (SD) from the official high-resolution badge artwork.
Generates:
  - app_icon.ico (16, 24, 32, 48, 64, 128, 256)
  - app_icon.png (512x512)
  - extension/icons/icon16.png
  - extension/icons/icon48.png
  - extension/icons/icon128.png
"""
import os
from PIL import Image, ImageDraw
import numpy as np
from scipy.ndimage import uniform_filter1d, distance_transform_edt

def extract_badge(src_path: str) -> Image.Image:
    img = Image.open(src_path)
    arr = np.array(img, dtype=np.float32)

    cx = 285.5
    cy = 513.5
    thetas = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    boundary_points = []

    for th in thetas:
        rs = np.linspace(180, 320, 281)
        xs = cx + rs * np.cos(th)
        ys = cy + rs * np.sin(th)

        valid = (xs >= 0) & (xs < img.width - 1) & (ys >= 0) & (ys < img.height - 1)
        xs = xs[valid]
        ys = ys[valid]
        rs = rs[valid]

        x0 = xs.astype(int)
        y0 = ys.astype(int)
        fx = xs - x0
        fy = ys - y0

        samples = (
            arr[y0, x0] * ((1 - fx) * (1 - fy))[:, None] +
            arr[y0, x0 + 1] * (fx * (1 - fy))[:, None] +
            arr[y0 + 1, x0] * ((1 - fx) * fy)[:, None] +
            arr[y0 + 1, x0 + 1] * (fx * fy)[:, None]
        )

        grad = np.linalg.norm(np.diff(samples, axis=0), axis=1)
        peaks = np.where(grad > 6.0)[0]
        if len(peaks) > 0:
            last_idx = peaks[-1]
            boundary_points.append((xs[last_idx], ys[last_idx]))

    pts_arr = np.array(boundary_points)
    pts_smooth = uniform_filter1d(pts_arr, size=9, axis=0, mode='wrap')

    scale = 4
    mask = Image.new('L', (img.width * scale, img.height * scale), 0)
    draw = ImageDraw.Draw(mask)
    poly_pts = [(p[0] * scale, p[1] * scale) for p in pts_smooth]
    draw.polygon(poly_pts, fill=255)
    mask = mask.resize((img.width, img.height), Image.Resampling.LANCZOS)

    min_x, min_y = pts_smooth.min(axis=0)
    max_x, max_y = pts_smooth.max(axis=0)
    cx_poly = (min_x + max_x) / 2
    cy_poly = (min_y + max_y) / 2
    size = max(max_x - min_x, max_y - min_y) + 6
    half = size / 2.0
    crop_box = (
        int(round(cx_poly - half)),
        int(round(cy_poly - half)),
        int(round(cx_poly + half)),
        int(round(cy_poly + half))
    )

    rgba = img.convert('RGBA')
    rgba.putalpha(mask)
    badge = rgba.crop(crop_box)

    # 2.5px distance transform erosion for clean antialiasing
    alpha = badge.split()[-1]
    a_arr = np.array(alpha, dtype=np.float32) / 255.0
    bin_m = a_arr > 0.5
    dist_in = distance_transform_edt(bin_m)
    dist_out = distance_transform_edt(~bin_m)
    signed_dist = dist_in - dist_out
    new_a = np.clip((signed_dist - 2.5) + 0.5, 0.0, 1.0) * 255.0

    # Ensure zero RGB fringe where fully transparent
    badge_np = np.array(badge)
    badge_np[:, :, 3] = new_a.astype(np.uint8)
    badge_np[badge_np[:, :, 3] == 0, :3] = 0
    badge = Image.fromarray(badge_np)

    return badge.resize((512, 512), Image.Resampling.LANCZOS)

def clean_transparent_rgb(im: Image.Image) -> Image.Image:
    arr = np.array(im)
    arr[arr[:, :, 3] == 0, :3] = 0
    return Image.fromarray(arr)

def main():
    src_path = r'C:/Users/hazoz/.gemini/antigravity/brain/1fb424b8-7352-420a-9e4e-5a26862632b1/.user_uploaded/media_1792680613694_4ba98c90.jpg'
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
    os.makedirs(ASSETS_DIR, exist_ok=True)
    png_path = os.path.join(ASSETS_DIR, "app_icon.png")
    ico_path = os.path.join(ASSETS_DIR, "app_icon.ico")

    if not os.path.exists(src_path):
        # Fallback to local app_icon.png if source is not present
        if os.path.exists(png_path):
            print("Using existing assets/app_icon.png as source master...")
            master = Image.open(png_path).convert('RGBA')
        elif os.path.exists('app_icon.png'):
            print("Using existing app_icon.png as source master...")
            master = Image.open('app_icon.png').convert('RGBA')
        else:
            raise FileNotFoundError(f"Source artwork not found at {src_path}")
    else:
        print("Extracting master 512x512 icon from artwork...")
        master = extract_badge(src_path)
        master = clean_transparent_rgb(master)
        icon256 = clean_transparent_rgb(master.resize((256, 256), Image.Resampling.LANCZOS))
        icon256.save(png_path, format="PNG")
        print(f"Saved {png_path} (256x256)")

    # Multi-resolution ICO: 16, 24, 32, 48, 64, 128, 256
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(
        ico_path,
        format="ICO",
        sizes=sizes
    )
    print(f"Saved {ico_path} with {len(sizes)} resolutions: {sizes}")

    # Update extension icons
    for d in [os.path.join(ROOT_DIR, "extension", "icons"), os.path.join(ROOT_DIR, "dist", "extension", "icons")]:
        os.makedirs(d, exist_ok=True)
        clean_transparent_rgb(master.resize((16, 16), Image.Resampling.LANCZOS)).save(os.path.join(d, "icon16.png"), format="PNG")
        clean_transparent_rgb(master.resize((48, 48), Image.Resampling.LANCZOS)).save(os.path.join(d, "icon48.png"), format="PNG")
        clean_transparent_rgb(master.resize((128, 128), Image.Resampling.LANCZOS)).save(os.path.join(d, "icon128.png"), format="PNG")
        print(f"Updated icons in {d}")

if __name__ == "__main__":
    main()
