"""
The HTML version of every e-mail (DEC-NOTIF-02): the app's dark card and gold accent, so a message
reads as BarberSaaS at a glance. Inline styles and a table layout, because mail clients drop <style>
blocks and flexbox. Every text is escaped: a name or a reason can never inject markup. The plain-text
body is still sent next to it for clients that do not show HTML.
"""
from html import escape

GOLD = "#d4af37"
BACKGROUND = "#121212"
CARD = "#1e1e1e"
MUTED = "#9a9a9a"


def _paragraphs(text: str) -> str:
    """Blank lines split paragraphs; a single line break stays a line break."""
    return "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:22px;color:#e8e8e8;">'
        f'{escape(block.strip()).replace(chr(10), "<br>")}</p>'
        for block in text.split("\n\n") if block.strip())


def _code_box(code: str) -> str:
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 20px;">'
            f'<tr><td align="center" style="background:{BACKGROUND};border:1px solid {GOLD};border-radius:12px;'
            f'padding:18px 10px;font-family:Consolas,Menlo,monospace;font-size:34px;font-weight:700;'
            f'letter-spacing:10px;color:{GOLD};">{escape(code)}</td></tr></table>')


def render(title: str, name: str, body: str, *, code: str | None = None, after: str = "") -> str:
    """The whole message: header, greeting, title, body, the code in a box when there is one, what follows it."""
    greeting = f"Hola{' ' + name if name else ''}"
    footer = "Recibes este correo porque tienes una cuenta en BarberSaaS."
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:{BACKGROUND};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BACKGROUND};">'
        '<tr><td align="center" style="padding:28px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        f'<tr><td align="center" style="padding:0 0 18px;font-size:22px;font-weight:800;color:#ffffff;">'
        f'<span style="font-size:26px;">💈</span> Barber<span style="color:{GOLD};">SaaS</span></td></tr>'
        f'<tr><td style="background:{CARD};border-top:4px solid {GOLD};border-radius:14px;padding:28px 26px;">'
        f'<p style="margin:0 0 6px;font-size:14px;color:{MUTED};">{escape(greeting)},</p>'
        f'<h1 style="margin:0 0 18px;font-size:22px;line-height:28px;color:#ffffff;">{escape(title)}</h1>'
        f'{_paragraphs(body)}{_code_box(code) if code else ""}{_paragraphs(after)}'
        '</td></tr>'
        f'<tr><td align="center" style="padding:18px 10px 0;font-size:12px;line-height:18px;color:{MUTED};">'
        f'{escape(footer)}</td></tr>'
        '</table></td></tr></table></body></html>')
