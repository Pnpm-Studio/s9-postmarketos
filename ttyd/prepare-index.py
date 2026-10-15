#!/usr/bin/python3
import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

TTYD = "/usr/bin/ttyd"
FONT = "/usr/share/fonts/jetbrains-mono-nerd/JetBrainsMonoNLNerdFontMono-Regular.ttf"
INDEX = Path("/run/s9-ttyd/index.html")
FONT_FAMILY = "S9NerdMono"


def stock_index():
    for _ in range(3):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        proc = subprocess.Popen(
            [TTYD, "-i", "127.0.0.1", "-p", str(port), "/bin/true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        page = None
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=0.25
                    ) as response:
                        page = response.read()
                    break
                except OSError:
                    time.sleep(0.05)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        if page and b"ttyd - Terminal" in page:
            return page.decode("utf-8")
    raise RuntimeError("could not fetch ttyd's embedded index")


def main():
    page = stock_index()
    font = base64.b64encode(Path(FONT).read_bytes()).decode("ascii")
    style = (
        "<style>@font-face{font-family:"
        + FONT_FAMILY
        + ";src:url(data:font/ttf;base64,"
        + font
        + ") format('truetype');font-display:block}</style>"
    )
    if page.count("<head>") != 1 or page.count(
        '<script type="text/javascript">'
    ) != 1:
        raise RuntimeError("unexpected ttyd index structure")
    page = page.replace("<head>", "<head>" + style, 1)
    before, app = page.split('<script type="text/javascript">', 1)
    app, after = app.split("</script>", 1)
    wait_for_font = (
        "document.fonts.load('15px "
        + FONT_FAMILY
        + "').catch(function(){}).then(function(){"
    )
    terminal_controls = (
        "const s9DashboardOrigin=new URL(location.href);"
        "s9DashboardOrigin.port='8090';"
        "let s9PendingControls=null,s9ControlObserver=null;"
        "function s9ApplyControls(){const terminal=window.term;"
        "if(!terminal||!s9PendingControls)return;"
        "const settings=s9PendingControls;s9PendingControls=null;"
        "if(settings.size!==undefined)terminal.options.fontSize=settings.size;"
        "if(settings.fit||settings.size!==undefined)terminal.fit();"
        "if(s9ControlObserver){s9ControlObserver.disconnect();s9ControlObserver=null;}}"
        "function s9QueueControls(settings){"
        "s9PendingControls=Object.assign(s9PendingControls||{},settings);"
        "if(window.term){s9ApplyControls();return;}"
        "if(!s9ControlObserver){s9ControlObserver=new MutationObserver(s9ApplyControls);"
        "s9ControlObserver.observe(document.documentElement,{childList:true,subtree:true});}}"
        "window.addEventListener('message',function(event){"
        "if(event.origin!==s9DashboardOrigin.origin||event.source!==parent||!event.data)return;"
        "if(event.data.type==='s9-font-size'&&Number.isInteger(event.data.size)"
        "&&event.data.size>=9&&event.data.size<=30)"
        "s9QueueControls({size:event.data.size});"
        "else if(event.data.type==='s9-fit')s9QueueControls({fit:true});});"
    )
    page = (
        before
        + '<script type="text/javascript">'
        + wait_for_font
        + app
        + "\n"
        + terminal_controls
        + "\n});</script>"
        + after
    )
    INDEX.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=INDEX.parent, delete=False
    ) as out:
        out.write(page)
        temporary = out.name
    os.chmod(temporary, 0o644)
    os.replace(temporary, INDEX)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"s9-ttyd: could not prepare icon font: {error}", file=sys.stderr)
        sys.exit(1)
