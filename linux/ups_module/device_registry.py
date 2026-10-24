"""
ups_module/device_registry.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Central device registry — loads device profiles from ``meta.json``.

Usage::

    from ups_module.device_registry import DeviceRegistry

    registry = DeviceRegistry()

    # List all registered devices
    for dev in registry.devices:
        print(f"{dev.id}: VID=0x{dev.vid:04X} PID=0x{dev.pid:04X}")

    # Look up by id
    profile = registry.get_by_id("phoenixtec_innova_unity")

    # Look up by VID/PID
    profile = registry.get_by_vid_pid(0x06DA, 0xFFFF)

    # Auto-detect connected device (requires hidapi)
    profile = registry.detect_connected()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default path: meta.json sits alongside this file
_DEFAULT_META_PATH = Path(__file__).parent / "meta.json"


# ---------------------------------------------------------------------------
# DeviceProfile dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeviceProfile:
    """Immutable profile for a single UPS model."""

    id: str
    manufacturer: str
    model: str
    vid: int
    pid: int
    protocol: str = "phoenixtec_hid"
    report_ids: List[int] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceProfile":
        """Create a DeviceProfile from a meta.json device entry."""
        return cls(
            id=d["id"],
            manufacturer=d["manufacturer"],
            model=d["model"],
            vid=int(d["vid"], 0),
            pid=int(d["pid"], 0),
            protocol=d.get("protocol", "phoenixtec_hid"),
            report_ids=[int(r, 0) for r in d.get("report_ids", [])],
            features=d.get("features", {}),
            notes=d.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# DeviceRegistry
# ---------------------------------------------------------------------------

class DeviceRegistry:
    """
    Loads and provides access to the device profiles defined in ``meta.json``.

    Parameters
    ----------
    meta_path : Path | None
        Path to the ``meta.json`` file.  Defaults to the one bundled with
        the package (``ups_module/meta.json``).
    """

    def __init__(self, meta_path: Optional[Path] = None) -> None:
        self._meta_path = meta_path or _DEFAULT_META_PATH
        self._profiles: List[DeviceProfile] = []
        self._load()

    # -- Loading -------------------------------------------------------------

    def _load(self) -> None:
        """Parse meta.json and populate the profile list."""
        try:
            with self._meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load %s: %s", self._meta_path, e)
            return

        version = data.get("version", "unknown")
        logger.debug("Loaded meta.json v%s from %s", version, self._meta_path)

        for entry in data.get("devices", []):
            try:
                self._profiles.append(DeviceProfile.from_dict(entry))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping invalid device entry: %s (%s)", entry.get("id", "?"), e)

    # -- Query methods -------------------------------------------------------

    @property
    def devices(self) -> List[DeviceProfile]:
        """Return all registered device profiles."""
        return list(self._profiles)

    def get_by_id(self, device_id: str) -> Optional[DeviceProfile]:
        """Look up a device profile by its unique ``id``."""
        for p in self._profiles:
            if p.id == device_id:
                return p
        return None

    def get_by_vid_pid(self, vid: int, pid: int) -> Optional[DeviceProfile]:
        """Look up a device profile by USB VID/PID pair."""
        for p in self._profiles:
            if p.vid == vid and p.pid == pid:
                return p
        return None

    def get_all_vid_pid_pairs(self) -> List[Tuple[int, int]]:
        """Return a list of ``(vid, pid)`` tuples for all registered devices."""
        return [(p.vid, p.pid) for p in self._profiles]

    def detect_connected(self) -> Optional[DeviceProfile]:
        """
        Auto-detect a connected UPS by scanning all registered VID/PID pairs.

        Returns the profile of the first connected device found, or ``None``
        if no registered device is detected.

        Requires ``hidapi`` to be installed.
        """
        try:
            import hid
        except ImportError:
            logger.warning("hidapi not available — cannot auto-detect device")
            return None

        for profile in self._profiles:
            devices = hid.enumerate(profile.vid, profile.pid)
            if devices:
                logger.info(
                    "Detected %s (%s) — VID=0x%04X PID=0x%04X",
                    profile.model, profile.id, profile.vid, profile.pid,
                )
                return profile

        logger.debug("No registered UPS device detected")
        return None

    # -- Convenience ---------------------------------------------------------

    def get_default(self) -> DeviceProfile:
        """
        Return the first registered device profile as the default.

        Raises ``RuntimeError`` if the registry is empty.
        """
        if not self._profiles:
            raise RuntimeError(
                f"No devices registered in {self._meta_path}. "
                f"Please add at least one device entry to meta.json."
            )
        return self._profiles[0]

    def __len__(self) -> int:
        return len(self._profiles)

    def __repr__(self) -> str:
        ids = [p.id for p in self._profiles]
        return f"DeviceRegistry({ids})"
