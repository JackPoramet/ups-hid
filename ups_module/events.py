"""
ups_module/events.py
~~~~~~~~~~~~~~~~~~~~
NUT-style event / notification system.

Mirrors the behaviour of ``upsmon``'s NOTIFYMSG / NOTIFYCMD mechanism:
  https://networkupstools.org/docs/man/upsmon.conf.html

Events are fired when UPS state transitions occur (e.g. ONLINE -> ONBATT).
Subscribers register callables that are invoked in a dedicated background thread
so they never block the polling loop.

Usage::

    from ups_module.events import EventBus, NotifyType

    bus = EventBus()

    @bus.on(NotifyType.ONBATT)
    def handle_onbatt(event):
        print(f"Power failed! {event}")

    # Or subscribe to all events:
    bus.subscribe(lambda e: print(e))
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Dict, List, Optional

from .models import NotifyType, UPSData, UPSEvent

logger = logging.getLogger(__name__)

# Type alias for event handler callables
EventHandler = Callable[[UPSEvent], None]


class EventBus:
    """
    Asynchronous event bus for UPS state-change notifications.

    Events are dispatched in a dedicated daemon thread so that
    slow handlers do not affect the polling loop.
    """

    def __init__(self, maxsize: int = 64) -> None:
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._queue: queue.Queue[Optional[UPSEvent]] = queue.Queue(maxsize=maxsize)
        self._thread = threading.Thread(target=self._dispatch_loop, daemon=True, name="UPSEventBus")
        self._thread.start()

    # -------------------------------------------------------------------------
    # Subscription API
    # -------------------------------------------------------------------------

    def on(self, notify_type: str) -> Callable[[EventHandler], EventHandler]:
        """
        Decorator to register a handler for a specific event type.

        Example::

            @bus.on(NotifyType.ONBATT)
            def handle(event: UPSEvent) -> None:
                ...
        """
        def decorator(fn: EventHandler) -> EventHandler:
            self.subscribe(fn, notify_type=notify_type)
            return fn
        return decorator

    def subscribe(
        self,
        handler: EventHandler,
        notify_type: Optional[str] = None,
    ) -> None:
        """
        Register *handler* to receive events.

        If *notify_type* is given, the handler is called only for events
        of that type.  Otherwise it is called for **all** events.
        """
        if notify_type is None:
            self._global_handlers.append(handler)
        else:
            self._handlers.setdefault(notify_type, []).append(handler)

    def unsubscribe(self, handler: EventHandler, notify_type: Optional[str] = None) -> None:
        """Remove a previously registered handler."""
        if notify_type is None:
            try:
                self._global_handlers.remove(handler)
            except ValueError:
                pass
        else:
            lst = self._handlers.get(notify_type, [])
            try:
                lst.remove(handler)
            except ValueError:
                pass

    # -------------------------------------------------------------------------
    # Publish API (used by EventDetector)
    # -------------------------------------------------------------------------

    def publish(self, event: UPSEvent) -> None:
        """Enqueue *event* for asynchronous dispatch."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("EventBus queue full, dropping event: %s", event.notify_type)

    def stop(self) -> None:
        """Signal the dispatch thread to stop."""
        self._queue.put(None)  # sentinel

    # -------------------------------------------------------------------------
    # Internal dispatch loop
    # -------------------------------------------------------------------------

    def _dispatch_loop(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break  # sentinel -> stop
            self._invoke(event)

    def _invoke(self, event: UPSEvent) -> None:
        handlers = (
            self._global_handlers
            + self._handlers.get(event.notify_type, [])
        )
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Error in event handler for %s", event.notify_type)


class EventDetector:
    """
    Detects UPS state transitions and fires events on an :class:`EventBus`.

    Call :meth:`process` on every new :class:`UPSData` snapshot.
    It compares with the previous snapshot and fires the appropriate
    NUT-compatible events.

    Mirrors the transition logic in ``upsmon``:
      - COMMOK / COMMBAD  — connection state changes
      - ONLINE / ONBATT   — power source transitions
      - LOWBATT / REPLBATT — battery condition changes
      - CHARGING          — charging state changes
      - OVERLOAD          — overload flag
      - OVER_TEMP         — temperature flag
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._prev: Optional[UPSData] = None
        self._was_connected: bool = False

    def process(self, data: UPSData, connected: bool) -> None:
        """
        Compare *data* with the previous snapshot and publish events.

        Call this from the poller on every successful (or failed) poll.
        *connected* should be ``True`` when the poll succeeded.
        """
        # Connection state
        if connected and not self._was_connected:
            self._emit(NotifyType.COMMOK, "Communication with UPS established.", data)
        elif not connected and self._was_connected:
            self._emit(NotifyType.COMMBAD, "Lost communication with UPS.", data)

        self._was_connected = connected

        if not connected or data is None:
            self._prev = None
            return

        prev = self._prev

        # Power source transitions
        now_on_batt = data.is_on_battery()
        prev_on_batt = prev.is_on_battery() if prev else False

        if now_on_batt and not prev_on_batt:
            self._emit(NotifyType.ONBATT, "UPS is on battery power.", data)
        elif not now_on_batt and prev_on_batt:
            self._emit(NotifyType.ONLINE, "UPS is back on line power.", data)

        # Low battery
        now_lb = data.is_low_battery()
        prev_lb = prev.is_low_battery() if prev else False
        if now_lb and not prev_lb:
            self._emit(NotifyType.LOWBATT, "Battery charge is low.", data)

        # Battery needs replacement
        now_replbatt = bool(data.need_replacement)
        prev_replbatt = bool(prev.need_replacement) if prev else False
        if now_replbatt and not prev_replbatt:
            self._emit(NotifyType.REPLBATT, "Battery needs to be replaced.", data)

        # Charging state
        now_chrg = data.is_charging()
        prev_chrg = prev.is_charging() if prev else False
        if now_chrg and not prev_chrg:
            self._emit(NotifyType.CHARGING, "Battery is charging.", data)

        # Overload
        now_over = bool(data.overload)
        prev_over = bool(prev.overload) if prev else False
        if now_over and not prev_over:
            self._emit(NotifyType.OVERLOAD, "UPS is overloaded.", data)

        # Over temperature
        now_temp = bool(data.over_temperature)
        prev_temp = bool(prev.over_temperature) if prev else False
        if now_temp and not prev_temp:
            self._emit(NotifyType.OVER_TEMP, "UPS over temperature.", data)

        # Shutdown imminent
        now_fsd = bool(data.shutdown_imminent)
        prev_fsd = bool(prev.shutdown_imminent) if prev else False
        if now_fsd and not prev_fsd:
            self._emit(NotifyType.FSD, "Shutdown imminent.", data)

        self._prev = data

    def _emit(self, notify_type: str, message: str, data: UPSData) -> None:
        event = UPSEvent(notify_type=notify_type, message=message, data=data)
        logger.info("UPS Event: %s", event)
        self._bus.publish(event)
