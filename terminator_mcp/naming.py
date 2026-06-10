"""Client-side terminal addressing for the MCP server.

Resolution order for a `terminal` argument:
  1. explicit UUID (urn string) that matches a live terminal
  2. friendly name — case-insensitive match against terminal titles
  3. omitted / empty -> the focused terminal (resolved by the bridge)

The bridge itself resolves an empty uuid to the focused terminal, so for the
empty case we pass '' straight through. Name resolution needs the terminal
list, so we fetch it once and match here.
"""

from . import socket_client


def list_terminals():
    """Return the bridge's list_terminals_info payload."""
    return socket_client.call('list_terminals_info', {})


def focused_uuid(terminals=None):
    """UUID of the focused terminal, or None."""
    terminals = terminals if terminals is not None else list_terminals()
    for t in terminals:
        if t.get('is_focused'):
            return t.get('uuid')
    return None


def resolve(terminal):
    """Resolve a `terminal` arg to a uuid string the bridge understands.

    Returns '' for the focused-terminal case (the bridge resolves it). Raises
    ValueError on an ambiguous or unknown friendly name.
    """
    if not terminal:
        return ''

    terminals = list_terminals()
    uuids = {t.get('uuid') for t in terminals}

    # 1. exact UUID
    if terminal in uuids:
        return terminal

    # 2. friendly name (case-insensitive) against any of the terminal's
    #    names: a custom titlebar label (set via `rename`), the VTE/OSC title,
    #    or the window title. custom_title is checked first so a renamed
    #    terminal is reliably addressable by its new name.
    needle = terminal.strip().lower()

    def _names(t):
        return [(t.get(k) or '').strip().lower()
                for k in ('custom_title', 'title', 'window_title')]

    matches = [t for t in terminals if needle in _names(t)]
    if len(matches) == 1:
        return matches[0]['uuid']
    if len(matches) > 1:
        raise ValueError('ambiguous_name: %d terminals named %r'
                         % (len(matches), terminal))

    raise ValueError('terminal_not_found: %r' % terminal)
