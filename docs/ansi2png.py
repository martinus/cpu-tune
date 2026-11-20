"""Render colored terminal output (ANSI, 256 colors) to a PNG with headless Chrome.

    python3 docs/ansi2png.py IN.ansi OUT.png [WIDTH]

To make docs/show.png on this machine, use docs/screenshot.py: it runs cputune, then this.
Needs google-chrome or chromium in PATH.
"""

import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def color256(n: int) -> str:
    base = ["#000", "#c00", "#0c0", "#cc0", "#00c", "#c0c", "#0cc", "#ccc",
            "#555", "#f55", "#5f5", "#ff5", "#55f", "#f5f", "#5ff", "#fff"]
    if n < 16:
        return base[n]
    if n >= 232:
        v = 8 + (n - 232) * 10
        return f"rgb({v},{v},{v})"
    n -= 16
    level = [0, 95, 135, 175, 215, 255]
    return f"rgb({level[n // 36]},{level[n // 6 % 6]},{level[n % 6]})"


def to_html(text: str) -> str:
    out, style = [], {}
    for part in re.split(r"(\x1b\[[0-9;]*m)", text):
        if part.startswith("\x1b["):
            codes = part[2:-1].split(";")
            i = 0
            while i < len(codes):
                if codes[i] in ("0", ""):
                    style = {}
                elif codes[i] == "1":
                    style["font-weight"] = "bold"
                elif codes[i] == "38" and i + 2 < len(codes):
                    style["color"] = color256(int(codes[i + 2]))
                    i += 2
                i += 1
        elif part:
            css = ";".join(f"{k}:{v}" for k, v in style.items())
            out.append(f'<span style="{css}">{html.escape(part)}</span>' if css else html.escape(part))
    return "".join(out)


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    sys.exit("needs google-chrome or chromium in PATH")


def render(text: str, dst: Path, width: int = 1000, scale: int = 1) -> None:
    """Write text (with ANSI colors) as a PNG. width is in CSS pixels; scale 2 doubles the pixels."""
    page = (
        '<html><body style="margin:0;background:#1e1e2e;color:#cdd6f4"><pre style="'
        "font-family:'Hack Nerd Font Mono','DejaVu Sans Mono',monospace;font-size:14px;"
        f'line-height:1.12;padding:16px 20px;margin:0">{to_html(text)}</pre></body></html>'
    )
    chrome = find_chrome()
    with tempfile.NamedTemporaryFile("w", suffix=".html") as f:
        f.write(page)
        f.flush()
        height = int((text.count("\n") + 1) * 15.7 + 34)
        subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                        f"--force-device-scale-factor={scale}", f"--screenshot={dst.resolve()}", f"file://{f.name}"],
                       check=True, capture_output=True)


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    render(src.read_text(), dst, width)


if __name__ == "__main__":
    main()
