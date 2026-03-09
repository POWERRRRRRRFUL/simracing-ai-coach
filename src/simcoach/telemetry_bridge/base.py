"""Abstract interface for telemetry sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from simcoach.models.telemetry import TelemetryFrame


class TelemetrySource(ABC):
    """
    Abstract base class for all telemetry sources.

    Implementations:
      - MockTelemetrySource   — synthetic data for testing
      - ACSharedMemorySource  — real Assetto Corsa shared memory (Windows only)

    The recorder calls `read_frame()` in a polling loop.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Open the telemetry source.
        Returns True on success, False if unavailable (e.g. game not running).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close / release the telemetry source."""

    @abstractmethod
    def read_frame(self) -> TelemetryFrame | None:
        """
        Read the current telemetry state.
        Returns None if data is not yet available (e.g. game is in menus).
        """

    @property
    @abstractmethod
    def car_id(self) -> str:
        """Current car identifier."""

    @property
    @abstractmethod
    def track_id(self) -> str:
        """Current track identifier."""

    @property
    @abstractmethod
    def is_session_active(self) -> bool:
        """True when the game is in an active driving session (not in menus/replay)."""
