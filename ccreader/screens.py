"""Base screen with the global key handling shared by every view."""

from __future__ import annotations

from time import monotonic

from textual import events
from textual.screen import Screen

ESC_WINDOW = 0.45  # seconds between two Esc presses to count as "Esc Esc"


class BaseScreen(Screen, inherit_bindings=False):
    """Detects `Esc Esc` (boss key) and `Ctrl+\\` (panic quit) on every screen.

    A single Esc is delivered to `on_single_escape` after a short delay, once it
    is clear that no second Esc follows.
    """

    AUTO_FOCUS = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_esc = 0.0
        self._esc_timer = None

    async def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if event.key in ("ctrl+backslash", "ctrl+4"):
            self.app.panic_quit()
            return
        if event.key == "escape":
            now = monotonic()
            if self._esc_timer is not None:
                self._esc_timer.stop()
                self._esc_timer = None
            if now - self._last_esc < ESC_WINDOW:
                self._last_esc = 0.0
                self.app.boss_key()
                return
            self._last_esc = now
            self._esc_timer = self.set_timer(ESC_WINDOW, self._fire_single_escape)
            return
        await self.handle_key(event)

    def _fire_single_escape(self) -> None:
        self._esc_timer = None
        self.on_single_escape()

    async def handle_key(self, event: events.Key) -> None:
        """Handle any key other than Esc / Ctrl+\\."""

    def on_single_escape(self) -> None:
        """Called for a lone Esc press."""
