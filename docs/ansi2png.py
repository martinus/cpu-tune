"""Render colored terminal output (ANSI, 256 colors) to a PNG with headless Chrome.

Makes docs/show.png:

    for c in 1 3 5; do timeout 3 taskset -c $c python3 -c 'while 1: pass' & done; sleep 0.5
    COLUMNS=104 ./cputune --now --color always > /tmp/show.ansi; wait
    python3 docs/ansi2png.py /tmp/show.ansi docs/show.png 940

Needs google-chrome (or chromium) in PATH.
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


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    text = src.read_text()
    page = (
        '<html><body style="margin:0;background:#1e1e2e;color:#cdd6f4"><pre style="'
        "font-family:'Hack Nerd Font Mono','DejaVu Sans Mono',monospace;font-size:14px;"
        f'line-height:1.12;padding:16px 20px;margin:0">{to_html(text)}</pre></body></html>'
    )
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome"
    with tempfile.NamedTemporaryFile("w", suffix=".html") as f:
        f.write(page)
        f.flush()
        height = int((text.count("\n") + 1) * 15.7 + 34)
        subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                        "--force-device-scale-factor=1", f"--screenshot={dst}", f"file://{f.name}"],
                       check=True, capture_output=True)


if __name__ == "__main__":
    main()
