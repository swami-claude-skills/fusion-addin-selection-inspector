"""Small SVG helpers for the documentation diagrams (house palette, embedded as <img> data URIs)."""
import base64, html

BG, PANEL, TEXT, DIM, MUTE = '#141418', '#1a1a20', '#e8e8ec', '#9aa0aa', '#6a6f78'
CYAN, GREEN, YELLOW, ORANGE, PINK, MAGENTA, VIOLET, BLUE = ('#38dafa', '#38fa79', '#dafa38', '#fa9938',
                                                          '#fa3899', '#ea38fa', '#7938fa', '#3879fa')
MONO = "JetBrains Mono, DejaVu Sans Mono, Menlo, monospace"
SANS = "DM Sans, Helvetica Neue, Arial, sans-serif"


def esc(t):
    return html.escape(str(t), quote=True)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []
        self.parts.append('<defs>'
                          '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                          '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker></defs>' % DIM)
        self.parts.append('<rect x="0" y="0" width="%d" height="%d" rx="14" fill="%s"/>' % (w, h, BG))

    def box(self, x, y, w, h, color, title=None, note=None, fill_alpha='1a', title_size=13, rx=8, dash=False):
        self.parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="%s%s" stroke="%s" stroke-width="1.6"%s/>'
                          % (x, y, w, h, rx, color, fill_alpha, color, ' stroke-dasharray="6 4"' if dash else ''))
        if title:
            ty = y + (h / 2 + 4 if not note else h / 2 - 4)
            self.text(x + w / 2, ty, title, size=title_size, color=TEXT, mono=True, anchor='middle', bold=True)
        if note:
            self.text(x + w / 2, y + h / 2 + 13, note, size=11, color=DIM, anchor='middle')

    def text(self, x, y, t, size=12, color=TEXT, mono=False, anchor='start', bold=False):
        self.parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="%s" fill="%s" text-anchor="%s"%s>%s</text>'
                          % (x, y, MONO if mono else SANS, size, color, anchor, ' font-weight="700"' if bold else '', esc(t)))

    def arrow(self, x1, y1, x2, y2, color=DIM, dash=False):
        self.parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.6" marker-end="url(#ah)"%s/>'
                          % (x1, y1, x2, y2, color, ' stroke-dasharray="6 4"' if dash else ''))

    def path(self, d, color=DIM, dash=False):
        self.parts.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.6" marker-end="url(#ah)"%s/>'
                          % (d, color, ' stroke-dasharray="6 4"' if dash else ''))

    def badge(self, x, y, n):
        self.parts.append('<circle cx="%d" cy="%d" r="10" fill="%s"/>' % (x, y, ORANGE))
        self.text(x, y + 4, str(n), size=11, color='#0d0d0f', mono=True, anchor='middle', bold=True)

    def svg(self):
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>'
                % (self.w, self.h, self.w, self.h, ''.join(self.parts)))

    def img(self, alt):
        data = base64.b64encode(self.svg().encode('utf-8')).decode('ascii')
        return '<img src="data:image/svg+xml;base64,%s" alt="%s" style="max-width:%dpx">' % (data, esc(alt), self.w)
