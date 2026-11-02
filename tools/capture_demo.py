"""
Demo capture tool.

Drives the running dashboard with Playwright and produces:

    deliverables/screenshots/*.png   full-page screenshots of every view
    deliverables/demo.gif            animated walkthrough (overview -> lab -> RCA)
    deliverables/console-errors.log  any browser console errors (should be empty)

Usage
-----
    pip install playwright && python -m playwright install chromium
    python tools/capture_demo.py --base http://localhost:5173
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "deliverables" / "screenshots"
FRAMES = ROOT / "deliverables" / ".frames"
SHOTS.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)


def log(page, errors: list[str]) -> None:
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"[pageerror] {exc}"))


def shot(page, name: str, frames: list[Path], caption: str | None = None, wait: int = 1200) -> Path:
    page.wait_for_timeout(wait)
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    if caption is not None:
        frames.append((path, caption))
    print(f"  ✓ {path.name}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:5173")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--gif-only", action="store_true", help="rebuild the GIF from existing screenshots")
    args = parser.parse_args()

    errors: list[str] = []
    frames: list = []

    if args.gif_only:
        ordered = [
            ("01-overview", "APIGuard - Monitoring overview"),
            ("02-endpoints", "Endpoint SLOs & 24h availability"),
            ("03-incidents-rca", "Incident console with root cause analysis"),
            ("04-failure-lab", "Failure lab - 7 scenarios"),
            ("05-failure-lab-result", "HTTP 500 detected - RCA + alerts dispatched"),
            ("06-alerts", "Alert history & notification channels"),
            ("07-settings", "Thresholds, channels & alert rules"),
            ("08-api-explorer", "Sample API explorer"),
        ]
        frames = [(SHOTS / f"{n}.png", c) for n, c in ordered if (SHOTS / f"{n}.png").exists()]
        build_gif(frames, ROOT / "deliverables" / "demo.gif")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=1)
        log(page, errors)

        print("→ overview")
        page.goto(f"{args.base}/#overview", wait_until="networkidle")
        page.wait_for_timeout(2500)
        shot(page, "01-overview", frames, "APIGuard · Monitoring overview")

        print("→ endpoints")
        page.goto(f"{args.base}/#endpoints", wait_until="networkidle")
        page.wait_for_timeout(2500)
        shot(page, "02-endpoints", frames, "Per-endpoint SLOs & uptime history")

        print("→ incidents")
        page.goto(f"{args.base}/#incidents", wait_until="networkidle")
        page.wait_for_timeout(2000)
        shot(page, "03-incidents-rca", frames, "Incident console with root cause analysis")

        print("→ failure lab (running scenarios)")
        page.goto(f"{args.base}/#lab", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "04-failure-lab", frames, "Failure lab · scenario catalogue")

        # run the HTTP 500 scenario and capture the detection
        buttons = page.get_by_role("button", name="Run scenario")
        if buttons.count():
            buttons.nth(2).click()  # server_error
            page.wait_for_timeout(3500)
        shot(page, "05-failure-lab-result", frames, "HTTP 500 detected → RCA + alerts", wait=800)

        print("→ alerts")
        page.goto(f"{args.base}/#alerts", wait_until="networkidle")
        page.wait_for_timeout(2000)
        shot(page, "06-alerts", frames, "Alert history & notification channels")

        print("→ settings")
        page.goto(f"{args.base}/#settings", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "07-settings", frames, "Thresholds, channels & alert rules")

        print("→ explorer")
        page.goto(f"{args.base}/#explorer", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.get_by_role("button", name="Send request").click()
        shot(page, "08-api-explorer", frames, "API explorer", wait=1200)

        browser.close()

    # ------------------------------------------------------------ GIF build
    print("→ building demo.gif")
    build_gif(frames, ROOT / "deliverables" / "demo.gif")

    log_file = ROOT / "deliverables" / "console-errors.log"
    log_file.write_text("\n".join(errors) if errors else "No console errors captured.\n", encoding="utf-8")
    print(f"→ console errors: {len(errors)} (see deliverables/console-errors.log)")


def build_gif(frames: list, out: Path, width: int = 1180, hold_ms: int = 1500) -> None:
    """Crop each screenshot to a 16:9-ish window, add a caption, and animate."""
    if not frames:
        print("  ! no frames captured")
        return
    height = int(width * 0.62)
    images: list[Image.Image] = []
    for path, caption in frames:
        img = Image.open(path).convert("RGB")
        # take the top slice of the page (the fold) so the GIF stays readable
        crop_h = min(img.height, int(img.width * 0.72))
        img = img.crop((0, 0, img.width, crop_h)).resize((width, height), Image.LANCZOS)
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rectangle([0, height - 54, width, height], fill=(7, 11, 22, 215))
        draw.text((22, height - 36), caption, fill=(226, 232, 240))
        # adaptive 96-colour palette keeps the animated GIF small (~400 KB)
        images.append(img.convert("P", palette=Image.ADAPTIVE, colors=96))

    images[0].save(
        out,
        save_all=True,
        append_images=images[1:] + [images[-1]],
        duration=hold_ms,
        loop=0,
        optimize=True,
    )
    print(f"  ✓ {out} ({len(images)} frames)")


if __name__ == "__main__":
    main()
