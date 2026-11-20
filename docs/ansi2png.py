"""Render colored terminal output (ANSI, 256 colors) to a PNG with headless Chrome.

    python3 docs/ansi2png.py IN.ansi OUT.png [WIDTH]

To make docs/show.png on this machine, use docs/screenshot.py: it runs cputune, then this.
Needs Chrome or Chromium: in PATH, or as flatpak (com.google.Chrome, org.chromium.Chromium).
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


CHROME_PROGRAMS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
CHROME_FLATPAKS = ("com.google.Chrome", "org.chromium.Chromium")


def find_chrome() -> list[str]:
    """The command that starts Chrome: a program in PATH, else a flatpak app ("flatpak run APP")."""
    for name in CHROME_PROGRAMS:
        if path := shutil.which(name):
            return [path]
    if shutil.which("flatpak"):
        for app in CHROME_FLATPAKS:
            if subprocess.run(["flatpak", "info", app], capture_output=True).returncode == 0:
                return ["flatpak", "run", app]
    sys.exit(f"needs Chrome or Chromium: {' or '.join(CHROME_PROGRAMS)} in PATH, "
             f"or the flatpak {' or '.join(CHROME_FLATPAKS)}")


def render(text: str, dst: Path, width: int = 1000, scale: int = 1) -> None:
    """Write text (with ANSI colors) as a PNG. width is in CSS pixels; scale 2 doubles the pixels."""
    page = (
        '<html><head><meta charset="utf-8"></head><body style="margin:0;background:#1e1e2e;color:#cdd6f4"><pre style="'
        "font-family:'Hack Nerd Font Mono','DejaVu Sans Mono',monospace;font-size:14px;"
        f'line-height:1.12;padding:16px 20px;margin:0">{to_html(text)}</pre></body></html>'
    )
    chrome = find_chrome()
    dst = dst.resolve()
    # Next to dst, not in /tmp: a flatpak Chrome sees only this directory (--filesystem), and
    # flatpak has its own /tmp.
    with tempfile.TemporaryDirectory(dir=dst.parent, prefix=".ansi2png-") as tmp:
        if chrome[0] == "flatpak":
            chrome.insert(2, f"--filesystem={tmp}")
        page_file, shot = Path(tmp) / "page.html", Path(tmp) / "shot.png"
        page_file.write_text(page, encoding="utf-8")
        height = int((text.count("\n") + 1) * 15.7 + 34)
        result = subprocess.run([*chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
                                 f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
                                 f"--screenshot={shot}", page_file.as_uri()], capture_output=True, text=True)
        if not shot.exists():
            sys.exit(f"{' '.join(chrome)} wrote no screenshot (exit code {result.returncode}):\n{result.stderr}")
        shutil.move(str(shot), str(dst))


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    render(src.read_text(encoding="utf-8"), dst, width)


if __name__ == "__main__":
    main()
