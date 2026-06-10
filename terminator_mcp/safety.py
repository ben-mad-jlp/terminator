"""Safety policy for write/command tools.

All enforcement lives here in the MCP server, not in the bridge. The bridge is
a thin primitive; this module decides what is allowed to reach it.

Three layers:
  1. HARD password/confirm-prompt gate — never type into a prompt that looks
     like it wants a secret or a destructive yes/no. NON-OVERRIDABLE: no
     confirm_token can bypass it. (The probe signal comes from the bridge;
     PASSWORD_RE here is a server-side backstop on the same last line.)
  2. Denylist — destructive command patterns require an explicit confirmation
     round-trip (dry-run -> single-use, short-TTL token bound to command+uuid).
  3. Tokens — single-use, ~60s TTL, bound to the exact (command, uuid).
"""

import os
import time

# Backstop password/confirm-prompt heuristic (mirrors the bridge's).
import re

PASSWORD_RE = re.compile(
    r'(?i)(password.*:|passphrase|sudo.*password|verification code'
    r'|\(yes/no\)|are you sure|permission denied, please try again)')

# Destructive-command denylist: (name, compiled regex). A match forces a
# confirmation round-trip; it does NOT hard-block (that is the password gate).
_DENY_SOURCE = [
    ('rm_rf',        r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?-?[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r'),
    ('rm_rf_simple', r'\brm\s+-\w*r\w*f|\brm\s+-\w*f\w*r'),
    ('mkfs',         r'\bmkfs\b'),
    ('dd_of',        r'\bdd\b.*\bof='),
    ('fork_bomb',    r':\(\)\s*\{'),
    ('write_block',  r'>\s*/dev/(sd|nvme|disk)'),
    ('power',        r'\b(shutdown|reboot|halt|poweroff)\b'),
    ('force_push',   r'\bgit\s+push\b.*--force|\bgit\s+push\b.*\s-f\b'),
    ('sudo',         r'\bsudo\b'),
    ('chmod_r',      r'\bchmod\s+-\w*R'),
    ('chown_r',      r'\bchown\s+-\w*R'),
    ('truncate',     r'\btruncate\b'),
    ('mv_dev_null', r'>\s*/dev/null\s*2>&1\s*&\s*$'),
]
DENYLIST = [(name, re.compile(pat)) for name, pat in _DENY_SOURCE]

TOKEN_TTL_SECONDS = 60.0


def looks_like_password_prompt(last_line):
    """Server-side backstop on the last visible line."""
    return bool(PASSWORD_RE.search(last_line or ''))


# Control bytes blocked on the raw send path (unless raw=True). Allows the
# benign whitespace TAB (0x09), LF (0x0a), CR (0x0d); blocks ESC (0x1b) and
# the other C0 controls that could drive escape sequences / signals.
_ALLOWED_CONTROL = {0x09, 0x0a, 0x0d}


def has_blocked_control_bytes(text):
    """True if text contains a C0 control byte we refuse to send literally."""
    for ch in text or '':
        o = ord(ch)
        if o < 0x20 and o not in _ALLOWED_CONTROL:
            return True
    return False


def match_denylist(command):
    """Return the name of the first denylist pattern the command matches, else None."""
    for name, rx in DENYLIST:
        if rx.search(command or ''):
            return name
    return None


class ConfirmStore:
    """Single-use, TTL-bound confirmation tokens.

    A token authorises exactly one (command, uuid) execution and expires.
    Stateless across process restarts (in-memory) — acceptable for a local,
    single-user tool; a stale token simply fails closed.
    """

    def __init__(self, ttl=TOKEN_TTL_SECONDS):
        self.ttl = ttl
        self._pending = {}   # token -> {command, uuid, timeout_ms, expires}

    def _now(self):
        return time.monotonic()

    def _sweep(self):
        now = self._now()
        for tok in [t for t, r in self._pending.items() if r['expires'] < now]:
            self._pending.pop(tok, None)

    def issue(self, command, uuid, timeout_ms, kind='run', extra=None):
        """Issue a token for a deferred action.

        kind: 'run' (run_command_capture) or 'send' (send_text). extra carries
        action-specific params (e.g. {enter, raw} for a send).
        """
        self._sweep()
        token = os.urandom(16).hex()
        self._pending[token] = {
            'command': command, 'uuid': uuid, 'timeout_ms': timeout_ms,
            'kind': kind, 'extra': extra or {},
            'expires': self._now() + self.ttl,
        }
        return token

    def consume(self, token, command=None, uuid=None):
        """Return the pending record and invalidate the token, or None.

        If command/uuid are supplied they must match what the token was issued
        for (prevents replaying a token against a different command).
        """
        self._sweep()
        record = self._pending.pop(token, None)
        if record is None:
            return None
        if command is not None and record['command'] != command:
            return None
        if uuid is not None and record['uuid'] != uuid:
            return None
        return record


# Process-wide store shared by the tools.
STORE = ConfirmStore()
