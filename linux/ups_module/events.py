"""
Async EventBus and EventDetector for UPS state-change notifications.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Dict, List, Optional

from .models import NotifyType, UPSData, UPSEvent

logger = logging.getLogger(__name__)
EventHandler = Callable[[UPSEvent], None]


class EventBus:
    """Asynchronous event bus for UPS notifications."""

    def __init__(self, maxsize: int = 64) -> None:
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []
        self._queue: queue.Queue[Optional[UPSEvent]] = queue.Queue(maxsize=maxsize)
        self._thread = threading.Thread(target=self._dispatch_loop, daemon=True, name="UPSEventBus")
        self._thread.start()

    def on(self, notify_type: str) -> Callable[[EventHandler], EventHandler]:
        def decorator(fn: EventHandler) -> EventHandler:
            self.subscribe(fn, notify_type=notify_type)
            return fn
        return decorator

    def subscribe(self, handler: EventHandler, notify_type: Optional[str] = None) -> None:
        if notify_type is None:
            self._global_handlers.append(handler)
        else:
            self._handlers.setdefault(notify_type, []).append(handler)

    def unsubscribe(self, handler: EventHandler, notify_type: Optional[str] = None) -> None:
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

    def publish(self, event: UPSEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("EventBus queue full: %s", event.notify_type)

    def stop(self) -> None:
        self._queue.put(None)

    def _dispatch_loop(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break
            self._invoke(event)

    def _invoke(self, event: UPSEvent) -> None:
        handlers = self._global_handlers + self._handlers.get(event.notify_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Error in event handler for %s", event.notify_type)


class EventDetector:
    """Detects UPS state transitions and publishes events to EventBus."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._prev: Optional[UPSData] = None
        self._was_connected: bool = False

    def process(self, data: UPSData, connected: bool) -> None:
        if connected and not self._was_connected:
            self._emit(NotifyType.COMMOK, "Communication with UPS established.", data)
        elif not connected and self._was_connected:
            self._emit(NotifyType.COMMBAD, "Lost communication with UPS.", data)

        self._was_connected = connected
        if not connected or data is None:
            self._prev = None
            return

        prev = self._prev
        now_on_batt = data.is_on_battery()
        prev_on_batt = prev.is_on_battery() if prev else False

        if now_on_batt and not prev_on_batt:
            self._emit(NotifyType.ONBATT, "UPS is on battery power.", data)
        elif not now_on_batt and prev_on_batt:
            self._emit(NotifyType.ONLINE, "UPS is back on line power.", data)

        if data.is_low_battery() and not (prev.is_low_battery() if prev else False):
            self._emit(NotifyType.LOWBATT, "Battery charge is low.", data)

        if bool(data.need_replacement) and not (bool(prev.need_replacement) if prev else False):
            self._emit(NotifyType.REPLBATT, "Battery needs to be replaced.", data)

        if data.is_charging() and not (prev.is_charging() if prev else False):
            self._emit(NotifyType.CHARGING, "Battery is charging.", data)

        if bool(data.overload) and not (bool(prev.overload) if prev else False):
            self._emit(NotifyType.OVERLOAD, "UPS is overloaded.", data)

        if bool(data.over_temperature) and not (bool(prev.over_temperature) if prev else False):
            self._emit(NotifyType.OVER_TEMP, "UPS over temperature.", data)

        if bool(data.shutdown_imminent) and not (bool(prev.shutdown_imminent) if prev else False):
            self._emit(NotifyType.FSD, "Shutdown imminent.", data)

        self._prev = data

    def _emit(self, notify_type: str, message: str, data: UPSData) -> None:
        event = UPSEvent(notify_type=notify_type, message=message, data=data)
        logger.info("UPS Event: %s", event)
        self._bus.publish(event)
