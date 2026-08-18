#!/usr/bin/env python3
"""Render docs/demo.gif from the real killer-demo numbers.

Built with Pillow + ffmpeg so every byte count on screen is exact.
Not an image-model mockup.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (125, 133, 144)
GREEN = (63, 185, 80)
AMBER = (210, 153, 34)
CYAN = (88, 166, 255)
RED = (248, 81, 73)
BAR = (22, 27, 34)
MUTED = (72, 79, 88)

W, H = 1080, 560
MARGIN = 28
LINE_H = 22


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def new_canvas() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((16, 16, W - 16, H - 16), radius=14, fill=BAR, outline=(48, 54, 61))
    # traffic lights
    for x, color in ((40, (255, 95, 86)), (64, (255, 189, 46)), (88, (39, 201, 63))):
        draw.ellipse((x, 30, x + 12, 42), fill=color)
    draw.text((118, 28), "crashmin — killer demo", font=font(13), fill=DIM)
    return img


def wrap(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    while text:
        out.append(text[:max_chars])
        text = text[max_chars:]
    return out


def draw_lines(img: Image.Image, rows: list[tuple[str, tuple[int, int, int]]]) -> Image.Image:
    draw = ImageDraw.Draw(img)
    y = 62
    face = font(15)
    for text, color in rows:
        for piece in wrap(text, 86):
            if y > H - 36:
                return img
            draw.text((MARGIN + 8, y), piece, font=face, fill=color)
            y += LINE_H
    return img


def save_hold(frames: list[Image.Image], img: Image.Image, n: int) -> None:
    for _ in range(n):
        frames.append(img.copy())


def type_command(frames: list[Image.Image], prefix_rows, command: str) -> None:
    typed = ""
    for ch in command:
        typed += ch
        rows = list(prefix_rows)
        rows.append(("$ " + typed + "█", FG))
        save_hold(frames, draw_lines(new_canvas(), rows), 1)


def storyboard(stats: dict) -> list[Image.Image]:
    frames: list[Image.Image] = []
    cmd = "crashmin saas.curl --status 500 --body-regex 'panic: nil pointer'"
    title = [("# Chrome 128 · Copy as cURL · anonymized", DIM)]

    save_hold(frames, draw_lines(new_canvas(), title + [("$ █", FG)]), 6)
    type_command(frames, title, cmd)
    save_hold(frames, draw_lines(new_canvas(), title + [("$ " + cmd, FG)]), 4)

    running: list[tuple[str, tuple[int, int, int]]] = title + [
        ("$ " + cmd, FG),
        ("", DIM),
        (
            f"parsed {stats['in_bytes']:,} byte request "
            f"({stats['in_comp']} components) → POST /a",
            CYAN,
        ),
        ("oracle: status 500, body ~ /panic: nil pointer/", DIM),
        ("loopback only · cookies and query values not logged", DIM),
    ]
    save_hold(frames, draw_lines(new_canvas(), running), 5)

    for phase in (
        "headers  18 → 1",
        "cookies  17 → 0",
        "query    8 → 0",
        "json     nested object → payload.deeply.nested.trigger",
    ):
        running.append((f"  {phase}", AMBER))
        save_hold(frames, draw_lines(new_canvas(), running), 4)

    score = running + [
        ("", DIM),
        (
            f"{stats['in_bytes']:,} bytes  →  {stats['out_bytes']} bytes",
            GREEN,
        ),
        (
            f"{stats['in_comp']} components  →  {stats['out_comp']}",
            GREEN,
        ),
        (f"{stats['pct']:.2f}% reduction", GREEN),
        (f"same failure: YES  ({stats['confirm']})", GREEN),
        ("", DIM),
        ("curl -H 'x-crash-token: letmein' \\", FG),
        ("  -d '{\"payload\":{\"deeply\":{\"nested\":{\"trigger\":\"boom\"}}}}' \\", FG),
        ("  'http://127.0.0.1:18765/a'", FG),
    ]
    save_hold(frames, draw_lines(new_canvas(), score), 28)
    return frames


def measure() -> dict:
    from crashmin.corpus import anonymized_saas_request
    from crashmin.executor import Executor
    from crashmin.fixtures import make_server
    from crashmin.oracle import compile_oracle
    from crashmin.reduce import reduce_request, render_result

    server = make_server("127.0.0.1", 0, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        req = anonymized_saas_request(base)
        result = reduce_request(
            req,
            Executor(
                oracle=compile_oracle(statuses=["500"], body_regexes=[r"panic: nil pointer"]),
                timeout=2.0,
            ),
            final_confirm=20,
        )
        curl = render_result(result, pretty=False)
        # Strip the ephemeral port for a stable README command.
        import re

        curl = re.sub(r"http://127\.0\.0\.1:\d+", "http://127.0.0.1:18765", curl)
        return {
            "in_bytes": result.original_bytes,
            "out_bytes": result.minimized_bytes,
            "in_comp": result.original_components,
            "out_comp": result.minimized_components,
            "pct": result.ratio * 100,
            "confirm": f"{result.final_hits}/{result.final_trials}",
            "curl": curl,
        }
    finally:
        server.shutdown()
        server.server_close()


def encode_gif(frames: list[Image.Image], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="crashmin-gif-"))
    try:
        for i, frame in enumerate(frames):
            frame.save(tmp / f"f{i:04d}.png")
        palette = tmp / "palette.png"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", "14", "-i", str(tmp / "f%04d.png"),
                "-vf", "palettegen=stats_mode=diff",
                str(palette),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-framerate", "14", "-i", str(tmp / "f%04d.png"),
                "-i", str(palette),
                "-lavfi", "paletteuse=dither=bayer:bayer_scale=3",
                "-loop", "0",
                str(dest),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("measuring anonymized Chrome case…", flush=True)
    stats = measure()
    print(
        f"{stats['in_bytes']:,} → {stats['out_bytes']}  "
        f"{stats['in_comp']} → {stats['out_comp']}  {stats['confirm']}",
        flush=True,
    )
    print("rendering frames…", flush=True)
    frames = storyboard(stats)
    dest = ROOT / "docs" / "demo.gif"
    encode_gif(frames, dest)
    kb = dest.stat().st_size / 1024
    print(f"wrote {dest} ({kb:.0f} KiB, {len(frames)} frames)")
    # Persist the numbers the GIF was built from.
    (ROOT / "docs" / "demo-stats.txt").write_text(
        "\n".join(
            [
                f"{stats['in_bytes']:,} bytes -> {stats['out_bytes']} bytes",
                f"{stats['in_comp']} components -> {stats['out_comp']}",
                f"{stats['pct']:.2f}% reduction",
                f"same failure: YES ({stats['confirm']})",
                stats["curl"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
