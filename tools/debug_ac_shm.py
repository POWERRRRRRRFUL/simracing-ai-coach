"""
Diagnostic tool: dump Assetto Corsa shared memory content.

Run this script WHILE Assetto Corsa is running to see exactly what is in
the static, graphics, and physics shared memory regions.

Usage:
    python tools/debug_ac_shm.py

Output includes:
  - Exact field offsets in the ACStatic struct
  - Raw hex bytes at carModel and track offsets
  - UTF-16LE decoded value for every string field
  - Integer field values
  - The race.ini fallback value (if available)
"""
from __future__ import annotations

import configparser
import ctypes
import mmap
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simcoach.telemetry_bridge.ac_shared_memory import (
    ACGraphics,
    ACPhysics,
    ACStatic,
)

SHM_PHYSICS  = "Local\\acpmf_physics"
SHM_GRAPHICS = "Local\\acpmf_graphics"
SHM_STATIC   = "Local\\acpmf_static"


def hexdump(data: bytes, offset: int, length: int) -> str:
    chunk = data[offset : offset + length]
    hex_part = " ".join(f"{b:02x}" for b in chunk[:40])
    if len(chunk) > 40:
        hex_part += " ..."
    return hex_part


def decode_wchar_field(data: bytes, offset: int, n_chars: int) -> str:
    chunk = data[offset : offset + n_chars * 2]
    try:
        return chunk.decode("utf-16-le", errors="replace").rstrip("\x00")
    except Exception as e:
        return f"<decode error: {e}>"


def open_shm(name: str, size: int) -> mmap.mmap | None:
    try:
        m = mmap.mmap(-1, size, name)
        return m
    except Exception as e:
        print(f"  [WARN] Cannot open {name}: {e}")
        return None


def read_race_ini() -> dict[str, str]:
    path = Path(os.path.expandvars(r"%USERPROFILE%\Documents\Assetto Corsa\cfg\race.ini"))
    if not path.exists():
        return {}
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8-sig")
    result = {}
    if cfg.has_option("RACE", "model"):
        result["model"] = cfg.get("RACE", "model")
    if cfg.has_option("RACE", "track"):
        result["track"] = cfg.get("RACE", "track")
    if cfg.has_option("RACE", "config_track"):
        result["config_track"] = cfg.get("RACE", "config_track")
    return result


def main() -> None:
    print("=" * 70)
    print("simcoach — AC shared memory diagnostic")
    print("=" * 70)
    print()

    # ── race.ini ──────────────────────────────────────────────────────────────
    print("=== race.ini (ground truth) ===")
    race = read_race_ini()
    if race:
        for k, v in race.items():
            print(f"  {k} = {v!r}")
    else:
        print("  (not found or empty)")
    print()

    # ── ACStatic field layout ─────────────────────────────────────────────────
    print("=== ACStatic field offsets ===")
    display_fields = [
        "smVersion", "acVersion", "numberOfSessions", "numCars",
        "carModel", "track", "playerName", "playerSurname", "playerNick",
        "sectorCount", "trackSplineLength", "trackConfiguration",
    ]
    for f in display_fields:
        desc = getattr(ACStatic, f)
        print(f"  {f:30s}  offset={desc.offset:4d}  size={desc.size}")
    print(f"\n  sizeof(ACStatic) = {ctypes.sizeof(ACStatic)}")
    print()

    # ── Open SHM ─────────────────────────────────────────────────────────────
    static_map = open_shm(SHM_STATIC, ctypes.sizeof(ACStatic))
    if static_map is None:
        print("ERROR: Cannot open static SHM. Is Assetto Corsa running?")
        return

    static_map.seek(0)
    raw = static_map.read(ctypes.sizeof(ACStatic))
    static_map.close()

    # ── ctypes struct parse ───────────────────────────────────────────────────
    obj = ACStatic()
    ctypes.memmove(ctypes.addressof(obj), raw, len(raw))

    print("=== ctypes struct values ===")
    print(f"  smVersion        = {obj.smVersion!r}")
    print(f"  acVersion        = {obj.acVersion!r}")
    print(f"  numberOfSessions = {obj.numberOfSessions}")
    print(f"  numCars          = {obj.numCars}")
    print(f"  carModel         = {obj.carModel!r}   ← this is the broken field")
    print(f"  track            = {obj.track!r}")
    print(f"  playerName       = {obj.playerName!r}")
    print(f"  playerSurname    = {obj.playerSurname!r}")
    print(f"  playerNick       = {obj.playerNick!r}")
    print(f"  sectorCount      = {obj.sectorCount}")
    print(f"  trackConfiguration = {obj.trackConfiguration!r}")
    print()

    # ── Raw byte analysis at carModel ─────────────────────────────────────────
    cm_off = ACStatic.carModel.offset
    tr_off = ACStatic.track.offset

    print("=== Raw bytes at carModel (offset {}) ===".format(cm_off))
    print(f"  hex      : {hexdump(raw, cm_off, 66)}")
    print(f"  utf-16le : {decode_wchar_field(raw, cm_off, 33)!r}")
    # Also try reading as Latin-1 / ASCII (in case AC stores 8-bit strings)
    ascii_val = raw[cm_off : cm_off + 33].split(b"\x00")[0]
    print(f"  ascii    : {ascii_val!r}")
    print()

    print("=== Raw bytes at track (offset {}) ===".format(tr_off))
    print(f"  hex      : {hexdump(raw, tr_off, 66)}")
    print(f"  utf-16le : {decode_wchar_field(raw, tr_off, 33)!r}")
    ascii_tr = raw[tr_off : tr_off + 33].split(b"\x00")[0]
    print(f"  ascii    : {ascii_tr!r}")
    print()

    # ── Compare 4 bytes before carModel (= numCars int) ──────────────────────
    nc_off = ACStatic.numCars.offset
    nc_val = struct.unpack_from("<i", raw, nc_off)[0]
    print(f"=== numCars at offset {nc_off} ===")
    print(f"  raw hex  : {hexdump(raw, nc_off, 4)}")
    print(f"  int value: {nc_val}")
    print()

    # ── Graphics SHM ─────────────────────────────────────────────────────────
    gfx_map = open_shm(SHM_GRAPHICS, ctypes.sizeof(ACGraphics))
    if gfx_map:
        gfx_map.seek(0)
        graw = gfx_map.read(ctypes.sizeof(ACGraphics))
        gfx_map.close()
        gobj = ACGraphics()
        ctypes.memmove(ctypes.addressof(gobj), graw, len(graw))
        status_names = {0: "OFF", 1: "REPLAY", 2: "LIVE", 3: "PAUSE"}
        print("=== ACGraphics status ===")
        print(f"  status           = {gobj.status} ({status_names.get(gobj.status, '?')})")
        print(f"  completedLaps    = {gobj.completedLaps}")
        print(f"  normalizedCarPos = {gobj.normalizedCarPosition:.4f}")
        print(f"  tyreCompound     = {gobj.tyreCompound!r}")
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("=== Summary ===")
    race_model = race.get("model", "(not in race.ini)")
    shm_model  = obj.carModel
    print(f"  race.ini model : {race_model!r}")
    print(f"  SHM carModel   : {shm_model!r}")
    print(f"  SHM track      : {obj.track!r}")
    if shm_model in ("0", "", "unknown") or not shm_model:
        print()
        print("  DIAGNOSIS: carModel is invalid in SHM.")
        print("  The race.ini fallback WILL be used for car identification.")
    else:
        print("  carModel reads correctly from SHM.")


if __name__ == "__main__":
    main()
