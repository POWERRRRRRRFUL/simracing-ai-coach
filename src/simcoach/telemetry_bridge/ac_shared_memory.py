"""
Assetto Corsa Shared Memory bridge.

AC exposes three memory-mapped files on Windows:
  Local\\acpmf_physics  — live physics data (speed, throttle, brake, etc.)
  Local\\acpmf_graphics — session state (lap count, positions, times, etc.)
  Local\\acpmf_static   — static info (car name, track name, etc.)

This implementation uses Python's ctypes to map those structures.
Only available on Windows while AC is running.

Reference: https://assettocorsa.club/forum/index.php?threads/acc-shared-memory-documentation.59965/
           https://github.com/ckendell/ACOverlaySDK/blob/master/ACHelper.py
"""

from __future__ import annotations

import configparser
import ctypes
import logging
import mmap
import os
import struct
import time
from pathlib import Path
from typing import Optional

from simcoach.models.telemetry import TelemetryFrame
from .base import TelemetrySource

log = logging.getLogger(__name__)

# Set env var SIMCOACH_DEBUG=1 to enable verbose SHM tracing.
_DEBUG = os.environ.get("SIMCOACH_DEBUG", "") == "1"


# ─── ctypes struct definitions ────────────────────────────────────────────────

class ACPhysics(ctypes.Structure):
    """Maps to Local\\acpmf_physics."""
    _pack_ = 4
    _fields_ = [
        ("packetId",            ctypes.c_int),
        ("gas",                 ctypes.c_float),    # throttle 0–1
        ("brake",               ctypes.c_float),    # brake 0–1
        ("fuel",                ctypes.c_float),
        ("gear",                ctypes.c_int),      # 0=R,1=N,2+=1st gear
        ("rpms",                ctypes.c_int),
        ("steerAngle",          ctypes.c_float),    # normalised -1 to 1
        ("speedKmh",            ctypes.c_float),
        ("velocity",            ctypes.c_float * 3),
        ("accG",                ctypes.c_float * 3),
        ("wheelSlip",           ctypes.c_float * 4),
        ("wheelLoad",           ctypes.c_float * 4),  # deprecated
        ("wheelsPressure",      ctypes.c_float * 4),
        ("wheelAngularSpeed",   ctypes.c_float * 4),
        ("tyreWear",            ctypes.c_float * 4),
        ("tyreDirtyLevel",      ctypes.c_float * 4),
        ("tyreCoreTemperature", ctypes.c_float * 4),
        ("camberRAD",           ctypes.c_float * 4),
        ("suspensionTravel",    ctypes.c_float * 4),
        ("drs",                 ctypes.c_float),
        ("tc",                  ctypes.c_float),      # TC intervention 0–1
        ("heading",             ctypes.c_float),
        ("pitch",               ctypes.c_float),
        ("roll",                ctypes.c_float),
        ("cgHeight",            ctypes.c_float),
        ("carDamage",           ctypes.c_float * 5),
        ("numberOfTyresOut",    ctypes.c_int),
        ("pitLimiterOn",        ctypes.c_int),
        ("abs",                 ctypes.c_float),      # ABS intervention 0–1
        ("kersCharge",          ctypes.c_float),
        ("kersInput",           ctypes.c_float),
        ("autoShifterOn",       ctypes.c_int),
        ("rideHeight",          ctypes.c_float * 2),
        ("turboBoost",          ctypes.c_float),
        ("ballast",             ctypes.c_float),
        ("airDensity",          ctypes.c_float),
        ("airTemp",             ctypes.c_float),
        ("roadTemp",            ctypes.c_float),
        ("localAngularVelocity",ctypes.c_float * 3),
        ("finalFF",             ctypes.c_float),
        ("performanceMeter",    ctypes.c_float),
        ("engineBrake",         ctypes.c_int),
        ("ersRecoveryLevel",    ctypes.c_int),
        ("ersPowerLevel",       ctypes.c_int),
        ("ersHeatCharging",     ctypes.c_int),
        ("ersIsCharging",       ctypes.c_int),
        ("kersCurrentKJ",       ctypes.c_float),
        ("drsAvailable",        ctypes.c_int),
        ("drsEnabled",          ctypes.c_int),
        ("brakeTemp",           ctypes.c_float * 4),
        ("clutch",              ctypes.c_float),
        ("tyreTempI",           ctypes.c_float * 4),
        ("tyreTempM",           ctypes.c_float * 4),
        ("tyreTempO",           ctypes.c_float * 4),
        ("isAIControlled",      ctypes.c_int),
        ("tyreContactPoint",    ctypes.c_float * 4 * 3),
        ("tyreContactNormal",   ctypes.c_float * 4 * 3),
        ("tyreContactHeading",  ctypes.c_float * 4 * 3),
        ("brakeBias",           ctypes.c_float),
        ("localVelocity",       ctypes.c_float * 3),
    ]


class ACGraphics(ctypes.Structure):
    """Maps to Local\\acpmf_graphics."""
    _pack_ = 4
    _fields_ = [
        ("packetId",            ctypes.c_int),
        ("status",              ctypes.c_int),   # 0=OFF,1=REPLAY,2=LIVE,3=PAUSE
        ("session",             ctypes.c_int),
        ("currentTime",         ctypes.c_wchar * 15),
        ("lastTime",            ctypes.c_wchar * 15),
        ("bestTime",            ctypes.c_wchar * 15),
        ("split",               ctypes.c_wchar * 15),
        ("completedLaps",       ctypes.c_int),
        ("position",            ctypes.c_int),
        ("iCurrentTime",        ctypes.c_int),   # ms
        ("iLastTime",           ctypes.c_int),   # ms
        ("iBestTime",           ctypes.c_int),   # ms
        ("sessionTimeLeft",     ctypes.c_float),
        ("distanceTraveled",    ctypes.c_float),
        ("isInPit",             ctypes.c_int),
        ("currentSectorIndex",  ctypes.c_int),
        ("lastSectorTime",      ctypes.c_int),
        ("numberOfLaps",        ctypes.c_int),
        ("tyreCompound",        ctypes.c_wchar * 33),
        ("replayTimeMultiplier",ctypes.c_float),
        ("normalizedCarPosition",ctypes.c_float),  # 0–1 track position
        ("carCoordinates",      ctypes.c_float * 3),
        ("penaltyTime",         ctypes.c_float),
        ("flag",                ctypes.c_int),
        ("idealLineOn",         ctypes.c_int),
        ("isInPitLane",         ctypes.c_int),
        ("surfaceGrip",         ctypes.c_float),
        ("mandatoryPitDone",    ctypes.c_int),
        ("windSpeed",           ctypes.c_float),
        ("windDirection",       ctypes.c_float),
    ]


class ACStatic(ctypes.Structure):
    """Maps to Local\\acpmf_static."""
    _pack_ = 4
    _fields_ = [
        ("smVersion",           ctypes.c_wchar * 15),
        ("acVersion",           ctypes.c_wchar * 15),
        ("numberOfSessions",    ctypes.c_int),
        ("numCars",             ctypes.c_int),
        ("carModel",            ctypes.c_wchar * 33),
        ("track",               ctypes.c_wchar * 33),
        ("playerName",          ctypes.c_wchar * 33),
        ("playerSurname",       ctypes.c_wchar * 33),
        ("playerNick",          ctypes.c_wchar * 33),
        ("sectorCount",         ctypes.c_int),
        ("maxTorque",           ctypes.c_float),
        ("maxPower",            ctypes.c_float),
        ("maxRpm",              ctypes.c_int),
        ("maxFuel",             ctypes.c_float),
        ("suspensionMaxTravel", ctypes.c_float * 4),
        ("tyreRadius",          ctypes.c_float * 4),
        ("maxTurboBoost",       ctypes.c_float),
        ("deprecated_1",        ctypes.c_float),
        ("deprecated_2",        ctypes.c_float),
        ("penaltiesEnabled",    ctypes.c_int),
        ("aidFuelRate",         ctypes.c_float),
        ("aidTireRate",         ctypes.c_float),
        ("aidMechanicalDamage", ctypes.c_float),
        ("aidAllowTyreBlankets",ctypes.c_int),
        ("aidStability",        ctypes.c_float),
        ("aidAutoClutch",       ctypes.c_int),
        ("aidAutoBlip",         ctypes.c_int),
        ("hasDRS",              ctypes.c_int),
        ("hasERS",              ctypes.c_int),
        ("hasKERS",             ctypes.c_int),
        ("kersMaxJ",            ctypes.c_float),
        ("engineBrakeSettingsCount", ctypes.c_int),
        ("ersPowerControllerCount",  ctypes.c_int),
        ("trackSplineLength",   ctypes.c_float),
        ("trackConfiguration",  ctypes.c_wchar * 33),
        ("ersMaxJ",             ctypes.c_float),
        ("isTimedRace",         ctypes.c_int),
        ("hasExtraLap",         ctypes.c_int),
        ("tyreWearRate",        ctypes.c_float),
    ]


# ─── Source implementation ────────────────────────────────────────────────────

AC_STATUS_OFF    = 0
AC_STATUS_REPLAY = 1
AC_STATUS_LIVE   = 2
AC_STATUS_PAUSE  = 3


class ACSharedMemorySource(TelemetrySource):
    """
    Reads telemetry directly from Assetto Corsa's shared memory.
    Only works on Windows when AC is running.
    """

    SHM_PHYSICS  = "Local\\acpmf_physics"
    SHM_GRAPHICS = "Local\\acpmf_graphics"
    SHM_STATIC   = "Local\\acpmf_static"

    def __init__(self) -> None:
        self._physics_map:  Optional[mmap.mmap] = None
        self._graphics_map: Optional[mmap.mmap] = None
        self._static_map:   Optional[mmap.mmap] = None
        self._car_id: str = "unknown"
        self._track_id: str = "unknown"
        self._prev_lap_count: int = -1
        self._current_lap_id: int = 0
        self._connected: bool = False

    # ── TelemetrySource interface ────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            import mmap as _mmap
            self._physics_map  = _mmap.mmap(-1, ctypes.sizeof(ACPhysics),  self.SHM_PHYSICS)
            self._graphics_map = _mmap.mmap(-1, ctypes.sizeof(ACGraphics), self.SHM_GRAPHICS)
            self._static_map   = _mmap.mmap(-1, ctypes.sizeof(ACStatic),   self.SHM_STATIC)

            # Read static info once; AC may not have populated carModel yet
            # (it can be "0" or empty during loading), so we re-try in read_frame().
            static = self._read_struct(ACStatic, self._static_map)
            shm_car   = self._clean_static_str(static.carModel)
            shm_track = self._clean_static_str(static.track)

            if _DEBUG:
                log.debug("[SHM connect] raw carModel=%r  raw track=%r",
                          static.carModel, static.track)
                log.debug("[SHM connect] cleaned car=%r  track=%r",
                          shm_car, shm_track)

            self._car_id   = shm_car
            self._track_id = shm_track

            # carModel is often "0" or blank at session start in some AC versions.
            # Fall back to race.ini which AC always writes before entering a session.
            if self._car_id == "unknown":
                ini_car, ini_track = self._read_race_ini()
                if ini_car:
                    self._car_id = ini_car
                    log.info("[SHM] carModel not in SHM — using race.ini: %s", ini_car)
                if self._track_id == "unknown" and ini_track:
                    self._track_id = ini_track

            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        for m in (self._physics_map, self._graphics_map, self._static_map):
            if m:
                try:
                    m.close()
                except Exception:
                    pass
        self._connected = False

    def read_frame(self) -> Optional[TelemetryFrame]:
        if not self._connected:
            return None

        try:
            phy = self._read_struct(ACPhysics,  self._physics_map)
            gfx = self._read_struct(ACGraphics, self._graphics_map)

            if gfx.status not in (AC_STATUS_LIVE, AC_STATUS_PAUSE):
                return None

            # If carModel wasn't populated at connect() time, retry from SHM
            # and then from race.ini as a last resort.
            if self._car_id == "unknown":
                self._try_refresh_static()
                if self._car_id == "unknown":
                    ini_car, _ = self._read_race_ini()
                    if ini_car:
                        self._car_id = ini_car
                        log.info("[SHM] carModel resolved from race.ini mid-session: %s", ini_car)

            # Detect lap boundary
            if self._prev_lap_count == -1:
                self._prev_lap_count = gfx.completedLaps
            if gfx.completedLaps > self._prev_lap_count:
                self._current_lap_id += 1
                self._prev_lap_count = gfx.completedLaps

            # AC gear encoding: 0=Reverse, 1=Neutral, 2+=1st gear onwards
            # Convert to: -1=R, 0=N, 1+=1st gear
            gear = phy.gear - 1

            return TelemetryFrame(
                timestamp=time.time(),
                lap_id=self._current_lap_id,
                normalized_track_position=max(0.0, min(1.0, gfx.normalizedCarPosition)),
                speed_kmh=phy.speedKmh,
                throttle=max(0.0, min(1.0, phy.gas)),
                brake=max(0.0, min(1.0, phy.brake)),
                steering=max(-1.0, min(1.0, phy.steerAngle)),
                gear=gear,
                rpm=float(phy.rpms),
                clutch=max(0.0, min(1.0, phy.clutch)),
                g_lat=phy.accG[0],
                g_lon=phy.accG[2],
                tyre_slip_fl=phy.wheelSlip[0],
                tyre_slip_fr=phy.wheelSlip[1],
                tyre_slip_rl=phy.wheelSlip[2],
                tyre_slip_rr=phy.wheelSlip[3],
                abs_active=phy.abs > 0.1,
                tc_active=phy.tc > 0.1,
            )

        except Exception:
            return None

    # ── Static refresh ───────────────────────────────────────────────────────

    _INVALID_CAR_IDS = {"", "0", "unknown"}

    def _clean_static_str(self, value: str) -> str:
        """Strip and validate a static SHM string; return 'unknown' if unusable."""
        s = (value or "").strip()
        return s if s and s not in self._INVALID_CAR_IDS else "unknown"

    def _try_refresh_static(self) -> None:
        """Re-read static SHM to pick up carModel if AC populated it after connect()."""
        if self._static_map is None:
            return
        try:
            static = self._read_struct(ACStatic, self._static_map)
            car   = self._clean_static_str(static.carModel)
            track = self._clean_static_str(static.track)
            if _DEBUG:
                log.debug("[SHM refresh] raw carModel=%r → cleaned=%r", static.carModel, car)
            if car != "unknown":
                log.info("[SHM] carModel resolved from SHM refresh: %s", car)
                self._car_id = car
            if track != "unknown":
                self._track_id = track
        except Exception as exc:
            log.debug("[SHM refresh] exception: %s", exc)

    @staticmethod
    def _read_race_ini() -> tuple[str, str]:
        """
        Read car model and track from AC's race.ini config file.

        AC always writes this file before loading a session, so it is a
        reliable fallback when the static SHM field has not been populated.

        Returns (car_model, track_id), either may be "" if not found.
        """
        ini_path = Path(os.path.expandvars(
            r"%USERPROFILE%\Documents\Assetto Corsa\cfg\race.ini"
        ))
        if not ini_path.exists():
            return "", ""
        try:
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding="utf-8-sig")
            car   = cfg.get("RACE", "model",  fallback="").strip()
            track = cfg.get("RACE", "track",  fallback="").strip()
            if _DEBUG:
                log.debug("[race.ini] model=%r  track=%r", car, track)
            return car, track
        except Exception as exc:
            log.debug("[race.ini] read failed: %s", exc)
            return "", ""

    @property
    def car_id(self) -> str:
        return self._car_id

    @property
    def track_id(self) -> str:
        return self._track_id

    @property
    def is_session_active(self) -> bool:
        if not self._connected or not self._graphics_map:
            return False
        try:
            gfx = self._read_struct(ACGraphics, self._graphics_map)
            return gfx.status == AC_STATUS_LIVE
        except Exception:
            return False

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _read_struct(struct_cls, mmap_obj: mmap.mmap):
        mmap_obj.seek(0)
        data = mmap_obj.read(ctypes.sizeof(struct_cls))
        obj = struct_cls()
        ctypes.memmove(ctypes.addressof(obj), data, ctypes.sizeof(struct_cls))
        return obj
