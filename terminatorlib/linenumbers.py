# Terminator line-number gutter
# GPL v2 only
"""linenumbers.py - a row-number gutter drawn to the left of the terminal.

Shows the absolute buffer row number for each visible terminal line, as a
5-digit zero-padded hex number (no 0x prefix, to stay narrow), right-aligned,
with a thin separator between the gutter and the terminal output. The numbers
match the rows used elsewhere (the MCP scroll_to / read_raw / find_in_scrollback
and the minimap), so a user can read a row off the gutter and refer to it.

Per-terminal and session-only; hidden by default, toggled from the right-click
menu (Terminal.do_linenumbers_toggle).
"""

from gi.repository import Gtk

PAD = 6                      # px padding either side of the numbers
DIGITS = 5                   # zero-padded hex width (~1M rows)
_FMT = '%0{}X'.format(DIGITS)


class LineNumbers(Gtk.DrawingArea):
    """A row-number gutter aligned with the terminal's visible lines."""

    def __init__(self, terminal):
        Gtk.DrawingArea.__init__(self)
        self.terminal = terminal
        self.vte = terminal.vte
        self.set_no_show_all(True)          # hidden until toggled on
        self.set_size_request(56, -1)       # refined on first draw

        self._adj = self.vte.get_vadjustment()
        self.connect('draw', self._on_draw)
        self._cid_value = self._adj.connect('value-changed',
                                            lambda *a: self.queue_draw())
        self._cid_contents = self.vte.connect('contents-changed',
                                              lambda *a: self.queue_draw())

    def _on_draw(self, _widget, cr):
        alloc = self.get_allocation()
        width, height = alloc.width, alloc.height
        cr.set_source_rgb(0.10, 0.10, 0.12)
        cr.paint()

        char_h = self.vte.get_char_height() or 1
        rows = self.vte.get_row_count()
        top_row = int(self._adj.get_value())

        cr.select_font_face('monospace', 0, 0)
        cr.set_font_size(max(8.0, char_h - 2.0))

        # Size the gutter to exactly fit DIGITS hex chars (fixed width).
        ext = cr.text_extents(_FMT % 0)
        need = int(ext.width) + PAD * 2 + 2
        if need != width:
            self.set_size_request(need, -1)

        cr.set_source_rgba(0.50, 0.52, 0.58, 0.95)
        for r in range(rows):
            label = _FMT % (top_row + r)
            le = cr.text_extents(label)
            x = (width - PAD - 2) - le.width
            y = r * char_h + char_h - 2          # text baseline for the row
            if y > height + char_h:
                break
            cr.move_to(x, y)
            cr.show_text(label)

        # separator between the gutter and the terminal output
        cr.set_source_rgba(1, 1, 1, 0.14)
        cr.set_line_width(1)
        cr.move_to(width - 0.5, 0)
        cr.line_to(width - 0.5, height)
        cr.stroke()
        return False

    def disconnect_hooks(self):
        for owner, cid in ((self._adj, self._cid_value),
                           (self.vte, self._cid_contents)):
            try:
                owner.disconnect(cid)
            except Exception:
                pass
