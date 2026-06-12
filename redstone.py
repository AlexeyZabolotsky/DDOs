#!/usr/bin/env python3
"""
redstone.py — Redstone Circuit Simulator
=========================================

Every block exposes the following methods; each returns a canonical packet
for logging and signal propagation:

    generate(power, payload)   – activate block as a signal source (0-15)
    destroy()                  – permanently remove block from simulation
    save(data)                 – persist arbitrary nested dict inside block
    erase()                    – clear saved data
    transmit(data, target)     – push data packet into neighbour's inbox
    block_transmission()       – lock block; it stops forwarding signals
    unblock_transmission()     – re-enable signal forwarding
    assign_group(gid)          – join a colour-coded group
    leave_group()              – leave current group
    connect(other)             – create bidirectional signal link
    disconnect(other)          – remove signal link
    tick(grid)                 – one simulation step (called by engine)

All state changes are described by packets with this schema
(data may be nested to any depth):

    {
        "state":  str,
        "coord":  {"x": int, "y": int, "z": int},
        "data":   { ...arbitrary nesting... }
    }

Group-level operations (BlockGroup):

    add(block)                 – add block to group
    remove(block)              – remove block from group
    move_data(grid, data)      – broadcast data dict to all group members
    activate_all(grid, power)  – activate every block in the group
    deactivate_all(grid)       – deactivate every block in the group
    block_all(grid)            – lock transmission in all group members
    unblock_all(grid)          – unlock transmission in all group members

Mouse interactions (toolbar at top selects mode):
    PLACE    – left-click empty cell to place selected block type
    ERASE    – left-click block to destroy it
    SELECT   – left-click block to inspect in side panel
    ACTIVATE – left-click to toggle signal on/off (power 0 ↔ 15)
    LOCK     – left-click to toggle transmission block/unblock
    CONNECT  – click two blocks to create a signal link
    DISCNT   – click two blocks to remove their signal link
    GROUP    – click blocks to add them to the active colour group
    UNGRP    – click block to remove it from its group
    Right-click (any mode) → erase block immediately

Keyboard shortcuts:
    1–8      select block type to place
    SPACE    single simulation step
    R        toggle continuous simulation (200 ms per tick)
    G        create new group, auto-switch to GROUP mode
    Ctrl+S   save full world state to  redstone_save.json
    Ctrl+L   load world state from     redstone_save.json
    ESC      cancel pending operation / deselect block
"""

import sys
import json
import copy
import uuid
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

try:
    import pygame
except ImportError:
    print("pygame is required.  Run:  pip install pygame")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════
#  Layout constants
# ══════════════════════════════════════════════════════════════════

WIN_W, WIN_H = 1280, 820
CELL         = 36           # pixels per grid cell
COLS, ROWS   = 22, 17       # grid dimensions
GX, GY       = 10, 92       # grid top-left corner (pixels)
PANEL_X      = GX + COLS * CELL + 14   # right panel start  (818)
PANEL_W      = WIN_W - PANEL_X - 6     # right panel width  (456)
FPS          = 30
SIM_MS       = 200          # ms between automatic simulation ticks

# ── Colour palette ────────────────────────────────────────────────
C_BG      = (15,  16,  26)
C_GRID    = (30,  32,  50)
C_TOOLBAR = (24,  26,  40)
C_PANEL   = (19,  20,  33)
C_TEXT    = (210, 212, 230)
C_DIM     = ( 98, 100, 120)
C_ACCENT  = ( 78, 138, 255)
C_SEL     = (255, 240,  58)
C_PEND    = (255, 198,  38)
C_WHITE   = (255, 255, 255)

# Base colour for each block type (face fill)
BLOCK_COLOR: Dict[str, Tuple] = {
    "source":   (218,  52,  52),
    "wire":     (140, 142, 158),
    "repeater": (212, 152,  32),
    "memory":   ( 48, 172,  52),
    "blocker":  ( 52,  52, 200),
    "not":      (192,  68, 192),
    "and":      ( 68, 192, 192),
    "or":       (192, 128,  48),
}

# Glow colours matched to block states
STATE_GLOW: Dict[str, Tuple] = {
    "inactive":     ( 52,  52,  72),
    "active":       (255,  72,  72),
    "transmitting": (255, 212,  52),
    "saving":       ( 52, 212,  52),
    "locked":       ( 72,  72, 212),
    "destroyed":    ( 22,  22,  32),
}

# Colour palette for groups (cycles when > 8 groups exist)
GROUP_PALETTE: List[Tuple] = [
    (255,  72,  72),
    ( 72, 255,  72),
    ( 72, 118, 255),
    (255, 222,  42),
    (255,  72, 255),
    ( 48, 212, 212),
    (255, 152,  22),
    (172,  42, 255),
]

# Single-character symbol drawn inside each block
TYPE_SYM: Dict[str, str] = {
    "source":   "S",
    "wire":     "~",
    "repeater": "R",
    "memory":   "M",
    "blocker":  "X",
    "not":      "!",
    "and":      "&",
    "or":       "|",
}


# ══════════════════════════════════════════════════════════════════
#  Enumerations
# ══════════════════════════════════════════════════════════════════

class BlockType(Enum):
    SOURCE   = "source"
    WIRE     = "wire"
    REPEATER = "repeater"
    MEMORY   = "memory"
    BLOCKER  = "blocker"
    GATE_NOT = "not"
    GATE_AND = "and"
    GATE_OR  = "or"

class BlockState(Enum):
    INACTIVE     = "inactive"
    ACTIVE       = "active"
    LOCKED       = "locked"
    SAVING       = "saving"
    TRANSMITTING = "transmitting"
    DESTROYED    = "destroyed"

class EditMode(Enum):
    PLACE      = "PLACE"
    ERASE      = "ERASE"
    SELECT     = "SELECT"
    ACTIVATE   = "ACTIVATE"
    LOCK       = "LOCK"
    CONNECT    = "CONNECT"
    DISCONNECT = "DISCNT"
    GROUP      = "GROUP"
    UNGROUP    = "UNGRP"


# ══════════════════════════════════════════════════════════════════
#  Canonical packet factory
# ══════════════════════════════════════════════════════════════════

def make_packet(
    state: str,
    x: int, y: int, z: int = 0,
    data: Optional[Dict] = None,
) -> Dict:
    """
    Build a canonical data packet used for all block communications.

    Schema (data supports arbitrary nesting depth):
        {
            "state":  str,
            "coord":  {"x": int, "y": int, "z": int},
            "data":   { ...any nesting... }
        }
    """
    return {
        "state": state,
        "coord": {"x": x, "y": y, "z": z},
        "data":  data or {},
    }


# ══════════════════════════════════════════════════════════════════
#  Block — the fundamental simulation unit
# ══════════════════════════════════════════════════════════════════

class Block:
    """
    A single Redstone-like block.

    Every state-changing method returns a canonical packet so callers
    can log it and propagate it through the simulation.
    """

    def __init__(
        self,
        btype: BlockType,
        x: int, y: int, z: int = 0,
        bid: Optional[str] = None,
    ) -> None:
        self.id   = bid or uuid.uuid4().hex[:8]
        self.type = btype
        self.x, self.y, self.z = x, y, z

        self.state:                BlockState    = BlockState.INACTIVE
        self.power:                int           = 0        # 0–15
        self.saved_data:           Dict          = {}
        self.connections:          Set[str]      = set()    # IDs of linked blocks
        self.group_id:             Optional[int] = None
        self.transmission_blocked: bool          = False
        self.alive:                bool          = True
        self._inbox:               List[Dict]    = []      # incoming this tick

    # ── Generation & destruction ──────────────────────────────────

    def generate(self, power: int = 15, payload: Optional[Dict] = None) -> Dict:
        """
        Activate this block as a signal source at the given power level (0–15).
        power=0 deactivates the source.
        """
        self.power = max(0, min(15, power))
        self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"power": self.power, "payload": payload or {}},
        )

    def destroy(self) -> Dict:
        """
        Permanently destroy this block.
        Clears all state, connections, and group membership.
        """
        pkt = make_packet(
            BlockState.DESTROYED.value, self.x, self.y, self.z,
            {
                "last_power":  self.power,
                "last_state":  self.state.value,
                "saved_data":  copy.deepcopy(self.saved_data),
                "connections": list(self.connections),
                "group_id":    self.group_id,
            },
        )
        self.alive               = False
        self.power               = 0
        self.state               = BlockState.DESTROYED
        self.connections         = set()
        self.transmission_blocked = False
        return pkt

    # ── Save & erase ──────────────────────────────────────────────

    def save(self, data: Dict) -> Dict:
        """
        Persist arbitrary nested data inside the block.
        The block transitions to SAVING state while data is held.
        """
        self.saved_data = copy.deepcopy(data)
        self.state      = BlockState.SAVING
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"saved": self.saved_data},
        )

    def erase(self) -> Dict:
        """Clear all saved data from the block."""
        self.saved_data = {}
        self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"erased": True},
        )

    # ── Transmission & blocking ───────────────────────────────────

    def transmit(self, data: Dict, target: "Block") -> Optional[Dict]:
        """
        Push a data packet directly into *target*'s inbox.
        Returns None (without transmitting) when this block is locked or dead.
        """
        if self.transmission_blocked or not self.alive:
            return None
        pkt = make_packet(
            BlockState.TRANSMITTING.value, self.x, self.y, self.z,
            {
                "from_id": self.id,
                "to_id":   target.id,
                "power":   self.power,
                "payload": copy.deepcopy(data),
            },
        )
        target._inbox.append(pkt)
        self.state = BlockState.TRANSMITTING
        return pkt

    def block_transmission(self) -> Dict:
        """Lock this block — it will no longer forward signals."""
        self.transmission_blocked = True
        self.state = BlockState.LOCKED
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"blocked": True},
        )

    def unblock_transmission(self) -> Dict:
        """Re-enable signal forwarding."""
        self.transmission_blocked = False
        self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"blocked": False},
        )

    # ── Group membership ──────────────────────────────────────────

    def assign_group(self, gid: int) -> Dict:
        """Join a colour-coded group."""
        self.group_id = gid
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"group_id": gid},
        )

    def leave_group(self) -> Dict:
        """Leave the current group."""
        old           = self.group_id
        self.group_id = None
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {"left_group": old},
        )

    # ── Connections ───────────────────────────────────────────────

    def connect(self, other: "Block") -> Dict:
        """Create a bidirectional signal connection with *other*."""
        self.connections.add(other.id)
        other.connections.add(self.id)
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {
                "connected_to": other.id,
                "target_coord": {"x": other.x, "y": other.y, "z": other.z},
            },
        )

    def disconnect(self, other: "Block") -> Dict:
        """Remove bidirectional signal connection with *other*."""
        self.connections.discard(other.id)
        other.connections.discard(self.id)
        return make_packet(
            self.state.value, self.x, self.y, self.z,
            {
                "disconnected_from": other.id,
                "target_coord":      {"x": other.x, "y": other.y, "z": other.z},
            },
        )

    # ── Simulation step ───────────────────────────────────────────

    def tick(self, grid: "RedstoneGrid") -> List[Dict]:
        """
        One simulation tick:
          1. Drain inbox.
          2. Compute new power/state based on block type logic.
          3. Forward signal to connected neighbours.
          4. Return list of outgoing packets.
        """
        if not self.alive:
            return []

        incoming  = list(self._inbox)
        self._inbox.clear()
        outgoing: List[Dict] = []
        t = self.type.value

        # ── Type-specific input logic ─────────────────────────────
        if t == "source":
            pass  # Power is controlled by user (generate / destroy)

        elif t == "wire":
            pwr = max((p["data"].get("power", 0) for p in incoming), default=0)
            self.power = max(0, pwr - 1)   # signal attenuates by 1 per wire
            self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE

        elif t == "repeater":
            pwr = max((p["data"].get("power", 0) for p in incoming), default=0)
            self.power = 15 if pwr > 0 else 0   # restores signal to full strength
            self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE

        elif t == "memory":
            for p in incoming:
                payload = p["data"].get("payload", {})
                if payload:
                    self.saved_data = copy.deepcopy(payload)
                    self.state = BlockState.SAVING

        elif t == "blocker":
            # Absorbs everything; never forwards
            self.state = BlockState.LOCKED
            return []

        elif t == "not":
            pwr = max((p["data"].get("power", 0) for p in incoming), default=0)
            self.power = 15 if pwr == 0 else 0
            self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE

        elif t == "and":
            pwrs = [p["data"].get("power", 0) for p in incoming]
            self.power = 15 if len(pwrs) >= 2 and all(pw > 0 for pw in pwrs) else 0
            self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE

        elif t == "or":
            pwr = max((p["data"].get("power", 0) for p in incoming), default=0)
            self.power = 15 if pwr > 0 else 0
            self.state = BlockState.ACTIVE if self.power > 0 else BlockState.INACTIVE

        # ── Forward signal to all connected neighbours ────────────
        if not self.transmission_blocked and self.power > 0:
            for nid in self.connections:
                nb = grid.get_by_id(nid)
                if nb and nb.alive:
                    pkt = make_packet(
                        BlockState.TRANSMITTING.value, self.x, self.y, self.z,
                        {
                            "from_id": self.id,
                            "power":   self.power,
                            "payload": copy.deepcopy(self.saved_data),
                        },
                    )
                    nb._inbox.append(pkt)
                    outgoing.append(pkt)

        return outgoing

    # ── Serialisation ─────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "id":    self.id,
            "type":  self.type.value,
            "state": self.state.value,
            "coord": {"x": self.x, "y": self.y, "z": self.z},
            "power": self.power,
            "saved_data":           copy.deepcopy(self.saved_data),
            "connections":          list(self.connections),
            "group_id":             self.group_id,
            "transmission_blocked": self.transmission_blocked,
        }

    def __repr__(self) -> str:
        return (f"Block({self.type.value}@{self.x},{self.y} "
                f"pwr={self.power} {self.state.value})")


# ══════════════════════════════════════════════════════════════════
#  BlockGroup — colour-coded set with broadcast operations
# ══════════════════════════════════════════════════════════════════

class BlockGroup:
    """
    A named, colour-coded collection of blocks with group-wide operations.
    move_data() implements the 'move data of connected groups' requirement.
    """

    def __init__(self, gid: int, color: Tuple) -> None:
        self.id        = gid
        self.color     = color
        self.block_ids: Set[str] = set()

    def add(self, block: Block) -> Dict:
        """Add block to group and return the generated packet."""
        self.block_ids.add(block.id)
        return block.assign_group(self.id)

    def remove(self, block: Block) -> Dict:
        """Remove block from group and return the generated packet."""
        self.block_ids.discard(block.id)
        return block.leave_group()

    def move_data(self, grid: "RedstoneGrid", data: Dict) -> List[Dict]:
        """
        Broadcast an arbitrary nested data dict to every live block in the group.
        This is the primary mechanism for migrating data across connected groups.
        """
        pkts: List[Dict] = []
        for bid in list(self.block_ids):
            b = grid.get_by_id(bid)
            if b and b.alive:
                pkts.append(b.save(data))
        return pkts

    def activate_all(self, grid: "RedstoneGrid", power: int = 15) -> List[Dict]:
        """Activate every live block in the group at the given power level."""
        pkts: List[Dict] = []
        for bid in list(self.block_ids):
            b = grid.get_by_id(bid)
            if b and b.alive:
                pkts.append(b.generate(power))
        return pkts

    def deactivate_all(self, grid: "RedstoneGrid") -> List[Dict]:
        """Deactivate every live block in the group."""
        return self.activate_all(grid, 0)

    def block_all(self, grid: "RedstoneGrid") -> List[Dict]:
        """Lock transmission in all live blocks of the group."""
        pkts: List[Dict] = []
        for bid in list(self.block_ids):
            b = grid.get_by_id(bid)
            if b and b.alive:
                pkts.append(b.block_transmission())
        return pkts

    def unblock_all(self, grid: "RedstoneGrid") -> List[Dict]:
        """Unlock transmission in all live blocks of the group."""
        pkts: List[Dict] = []
        for bid in list(self.block_ids):
            b = grid.get_by_id(bid)
            if b and b.alive:
                pkts.append(b.unblock_transmission())
        return pkts

    def to_dict(self) -> Dict:
        return {
            "id":        self.id,
            "color":     list(self.color),
            "block_ids": list(self.block_ids),
        }


# ══════════════════════════════════════════════════════════════════
#  RedstoneGrid — world manager + simulation engine
# ══════════════════════════════════════════════════════════════════

class RedstoneGrid:
    """
    Owns all blocks and groups.
    Drives simulation ticks and serialises/deserialises the world state.
    """

    def __init__(self, cols: int = COLS, rows: int = ROWS) -> None:
        self.cols = cols
        self.rows = rows
        self._cells:  Dict[Tuple[int, int], Block] = {}
        self._by_id:  Dict[str, Block]             = {}
        self.groups:  Dict[int, BlockGroup]        = {}
        self._next_gid = 0
        self.log: List[Dict] = []   # rolling event log (last 400 packets)

    # ── Block placement / removal ─────────────────────────────────

    def place(self, btype: BlockType, x: int, y: int) -> Optional[Block]:
        """Place a new block of *btype* at grid position (x, y)."""
        if (x, y) in self._cells or not (0 <= x < self.cols and 0 <= y < self.rows):
            return None
        b = Block(btype, x, y)
        self._cells[(x, y)] = b
        self._by_id[b.id]   = b
        self._log(make_packet("placed", x, y, data={"type": btype.value, "id": b.id}))
        return b

    def remove(self, x: int, y: int) -> Optional[Dict]:
        """Remove and destroy the block at (x, y)."""
        b = self._cells.pop((x, y), None)
        if not b:
            return None
        # Clean up group membership
        if b.group_id is not None:
            g = self.groups.get(b.group_id)
            if g:
                g.block_ids.discard(b.id)
        # Sever all connections
        for nid in list(b.connections):
            nb = self._by_id.get(nid)
            if nb:
                nb.connections.discard(b.id)
        pkt = b.destroy()
        self._by_id.pop(b.id, None)
        self._log(pkt)
        return pkt

    def get(self, x: int, y: int) -> Optional[Block]:
        return self._cells.get((x, y))

    def get_by_id(self, bid: str) -> Optional[Block]:
        return self._by_id.get(bid)

    def all_blocks(self) -> List[Block]:
        return list(self._cells.values())

    # ── Group management ─────────────────────────────────────────

    def new_group(self) -> BlockGroup:
        """Create a new colour-coded group and register it."""
        gid   = self._next_gid
        self._next_gid += 1
        color = GROUP_PALETTE[gid % len(GROUP_PALETTE)]
        g     = BlockGroup(gid, color)
        self.groups[gid] = g
        self._log(make_packet("group_created", 0, 0,
                              data={"group_id": gid, "color": color}))
        return g

    def add_to_group(self, block: Block, gid: int) -> Optional[Dict]:
        """Add *block* to group *gid*."""
        g = self.groups.get(gid)
        if not g:
            return None
        pkt = g.add(block)
        self._log(pkt)
        return pkt

    def remove_from_group(self, block: Block) -> Optional[Dict]:
        """Remove *block* from its current group."""
        if block.group_id is None:
            return None
        g   = self.groups.get(block.group_id)
        pkt = g.remove(block) if g else block.leave_group()
        self._log(pkt)
        return pkt

    # ── Connection management ────────────────────────────────────

    def connect(self, b1: Block, b2: Block) -> Dict:
        pkt = b1.connect(b2)
        self._log(pkt)
        return pkt

    def disconnect(self, b1: Block, b2: Block) -> Dict:
        pkt = b1.disconnect(b2)
        self._log(pkt)
        return pkt

    # ── Simulation engine ─────────────────────────────────────────

    def tick(self) -> None:
        """Advance every live block by one simulation step."""
        for b in list(self._cells.values()):
            for pkt in b.tick(self):
                self._log(pkt)

    # ── Persistence ───────────────────────────────────────────────

    def save(self, path: str = "redstone_save.json") -> Dict:
        """Serialise full world state to JSON."""
        state = {
            "cols":   self.cols,
            "rows":   self.rows,
            "blocks": [b.to_dict() for b in self._cells.values()],
            "groups": {str(gid): g.to_dict() for gid, g in self.groups.items()},
        }
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        self._log(make_packet("saved", 0, 0, data={"path": path}))
        return state

    def load(self, path: str = "redstone_save.json") -> None:
        """Deserialise world state from JSON, replacing current state."""
        with open(path) as f:
            state = json.load(f)
        self._cells.clear()
        self._by_id.clear()
        self.groups.clear()

        for bd in state.get("blocks", []):
            b = Block(
                BlockType(bd["type"]),
                bd["coord"]["x"], bd["coord"]["y"], bd["coord"]["z"],
                bd["id"],
            )
            b.state               = BlockState(bd["state"])
            b.power               = bd["power"]
            b.saved_data          = bd.get("saved_data", {})
            b.connections         = set(bd.get("connections", []))
            b.group_id            = bd.get("group_id")
            b.transmission_blocked = bd.get("transmission_blocked", False)
            b.alive               = b.state != BlockState.DESTROYED
            if b.alive:
                self._cells[(b.x, b.y)] = b
                self._by_id[b.id]       = b

        for gid_s, gd in state.get("groups", {}).items():
            gid = int(gid_s)
            g   = BlockGroup(gid, tuple(gd["color"]))
            g.block_ids = set(gd.get("block_ids", []))
            self.groups[gid] = g

        self._next_gid = max((g.id for g in self.groups.values()), default=-1) + 1
        self._log(make_packet("loaded", 0, 0, data={"path": path}))

    # ── Internal ──────────────────────────────────────────────────

    def _log(self, pkt: Dict) -> None:
        self.log.append(pkt)
        if len(self.log) > 400:
            self.log.pop(0)


# ══════════════════════════════════════════════════════════════════
#  Pygame UI helpers
# ══════════════════════════════════════════════════════════════════

def draw_rounded(
    surf: pygame.Surface,
    color: Tuple,
    rect: pygame.Rect,
    radius: int = 5,
    border: int = 0,
    border_color: Optional[Tuple] = None,
) -> None:
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, border, border_radius=radius)


def cell_rect(x: int, y: int) -> pygame.Rect:
    return pygame.Rect(GX + x * CELL, GY + y * CELL, CELL, CELL)


def px_to_cell(px: int, py: int) -> Optional[Tuple[int, int]]:
    cx = (px - GX) // CELL
    cy = (py - GY) // CELL
    if 0 <= cx < COLS and 0 <= cy < ROWS:
        return cx, cy
    return None


class Btn:
    """Simple toggle/push button for the toolbar and panel."""

    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        color: Tuple      = C_TOOLBAR,
        active_color: Tuple = C_ACCENT,
        font: Optional[pygame.font.Font] = None,
        toggle: bool = False,
    ) -> None:
        self.rect         = rect
        self.label        = label
        self.color        = color
        self.active_color = active_color
        self.font         = font
        self.toggle       = toggle
        self.active       = False
        self.hovered      = False

    def draw(self, surf: pygame.Surface) -> None:
        bg = self.active_color if self.active else self.color
        if self.hovered:
            bg = tuple(min(255, c + 18) for c in bg)
        draw_rounded(surf, bg, self.rect, radius=5)
        if self.active:
            pygame.draw.rect(surf, C_SEL, self.rect, 2, border_radius=5)
        if self.font:
            t = self.font.render(self.label, True, C_WHITE)
            surf.blit(t, t.get_rect(center=self.rect.center))

    def update(self, ev: pygame.event.Event) -> bool:
        """Process event; return True if button was clicked."""
        if ev.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                if self.toggle:
                    self.active = not self.active
                return True
        return False


# ══════════════════════════════════════════════════════════════════
#  Main Application
# ══════════════════════════════════════════════════════════════════

class App:
    """Pygame application: renders the grid, handles all input, drives sim."""

    ALL_MODES  = list(EditMode)
    ALL_TYPES  = list(BlockType)

    MODE_LABELS: Dict[EditMode, str] = {
        EditMode.PLACE:      "PLACE",
        EditMode.ERASE:      "ERASE",
        EditMode.SELECT:     "SELECT",
        EditMode.ACTIVATE:   "ACTIVATE",
        EditMode.LOCK:       "LOCK",
        EditMode.CONNECT:    "CONNECT",
        EditMode.DISCONNECT: "DISCNT",
        EditMode.GROUP:      "GROUP",
        EditMode.UNGROUP:    "UNGRP",
    }

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Redstone Simulator")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock  = pygame.time.Clock()

        self.fn_sm = pygame.font.SysFont("monospace", 11)
        self.fn_md = pygame.font.SysFont("monospace", 13)
        self.fn_lg = pygame.font.SysFont("monospace", 15, bold=True)

        self.grid = RedstoneGrid()

        self.running    = False     # continuous sim on/off
        self._sim_acc   = 0         # ms accumulator
        self.mode       = EditMode.PLACE
        self.sel_type   = BlockType.SOURCE
        self.sel_block: Optional[Block] = None
        self.pend:      Optional[Block] = None    # first block in CONNECT/DISCNT op
        self.act_group: Optional[int]   = None    # group being built
        self._status    = "Ready — left-click to place a SOURCE block"

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self) -> None:
        # Row 1: mode selector buttons
        bw, bh, gap = 84, 28, 4
        x0, y0 = 8, 6
        self.mode_btns: List[Btn] = []
        for i, m in enumerate(self.ALL_MODES):
            r = pygame.Rect(x0 + i * (bw + gap), y0, bw, bh)
            b = Btn(r, self.MODE_LABELS[m], C_TOOLBAR, C_ACCENT,
                    font=self.fn_md, toggle=True)
            b.active = (m == self.mode)
            self.mode_btns.append(b)

        # Row 2: block type palette
        bw2, bh2 = 76, 24
        x0, y0 = 8, 42
        self.type_btns: List[Btn] = []
        for i, bt in enumerate(self.ALL_TYPES):
            r  = pygame.Rect(x0 + i * (bw2 + 4), y0, bw2, bh2)
            ac = BLOCK_COLOR.get(bt.value, C_ACCENT)
            b  = Btn(r, f"{bt.value[:3].upper()}[{i+1}]",
                     C_TOOLBAR, ac, font=self.fn_sm, toggle=True)
            b.active = (bt == self.sel_type)
            self.type_btns.append(b)

        # Panel action buttons (bottom of right panel)
        px = PANEL_X + 4
        bw3, bh3, gap3 = PANEL_W - 8, 26, 4
        n_btns = 6
        py_base = WIN_H - n_btns * (bh3 + gap3) - 6
        specs = [
            ("step",      "STEP  [SPACE]",   C_ACCENT),
            ("run",       "RUN   [R]",        (48, 168, 58)),
            ("new_group", "NEW GROUP  [G]",   (148, 48, 198)),
            ("save",      "SAVE  [Ctrl+S]",   (48, 128, 198)),
            ("load",      "LOAD  [Ctrl+L]",   (48, 128, 198)),
            ("clear",     "CLEAR ALL",        (198, 68, 48)),
        ]
        self.panel_btns: Dict[str, Btn] = {}
        for i, (k, lbl, col) in enumerate(specs):
            r = pygame.Rect(px, py_base + i * (bh3 + gap3), bw3, bh3)
            self.panel_btns[k] = Btn(r, lbl, col, col, font=self.fn_md)

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        while True:
            dt = self.clock.tick(FPS)
            self._process_events()
            self._update(dt)
            self._render()
            pygame.display.flip()

    # ── Event processing ──────────────────────────────────────────

    def _process_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

            for i, btn in enumerate(self.mode_btns):
                if btn.update(ev):
                    self._set_mode(self.ALL_MODES[i])

            for i, btn in enumerate(self.type_btns):
                if btn.update(ev):
                    self._set_type(self.ALL_TYPES[i])

            for k, btn in self.panel_btns.items():
                if btn.update(ev):
                    self._panel_action(k)

            if ev.type == pygame.KEYDOWN:
                self._on_key(ev)

            if ev.type == pygame.MOUSEBUTTONDOWN:
                cell = px_to_cell(*ev.pos)
                if cell:
                    self._on_grid_click(cell[0], cell[1], ev.button)

    def _on_key(self, ev: pygame.event.Event) -> None:
        k    = ev.key
        mods = pygame.key.get_mods()
        if k == pygame.K_SPACE:
            self.grid.tick()
            self._status = "Single tick"
        elif k == pygame.K_r:
            self._panel_action("run")
        elif k == pygame.K_g:
            self._panel_action("new_group")
        elif k == pygame.K_ESCAPE:
            self.pend      = None
            self.sel_block = None
            self._status   = "Cancelled"
        elif k == pygame.K_s and (mods & pygame.KMOD_CTRL):
            self._panel_action("save")
        elif k == pygame.K_l and (mods & pygame.KMOD_CTRL):
            self._panel_action("load")
        elif pygame.K_1 <= k <= pygame.K_8:
            idx = k - pygame.K_1
            if idx < len(self.ALL_TYPES):
                self._set_type(self.ALL_TYPES[idx])

    def _on_grid_click(self, x: int, y: int, button: int) -> None:
        b = self.grid.get(x, y)

        # Right-click always erases (any mode)
        if button == 3:
            if b:
                self.grid.remove(x, y)
                if self.sel_block and self.sel_block.id == b.id:
                    self.sel_block = None
                if self.pend and self.pend.id == b.id:
                    self.pend = None
                self._status = f"Destroyed block at ({x},{y})"
            return

        if button != 1:
            return

        if self.mode == EditMode.PLACE:
            if not b:
                nb = self.grid.place(self.sel_type, x, y)
                if nb:
                    self._status = f"Placed {self.sel_type.value} at ({x},{y})"

        elif self.mode == EditMode.ERASE:
            if b:
                self.grid.remove(x, y)
                if self.sel_block and self.sel_block.id == b.id:
                    self.sel_block = None
                if self.pend and self.pend.id == b.id:
                    self.pend = None
                self._status = f"Erased ({x},{y})"

        elif self.mode == EditMode.SELECT:
            self.sel_block = b
            self._status = repr(b) if b else f"Empty ({x},{y})"

        elif self.mode == EditMode.ACTIVATE:
            if b:
                if b.state == BlockState.ACTIVE:
                    pkt = b.generate(0)
                    self._status = f"Deactivated {b.id}"
                else:
                    pkt = b.generate(15)
                    self._status = f"Activated {b.id} at power 15"
                self.grid._log(pkt)
                self.sel_block = b

        elif self.mode == EditMode.LOCK:
            if b:
                if b.transmission_blocked:
                    pkt = b.unblock_transmission()
                    self._status = f"Unblocked {b.id}"
                else:
                    pkt = b.block_transmission()
                    self._status = f"Locked {b.id} — transmission blocked"
                self.grid._log(pkt)
                self.sel_block = b

        elif self.mode == EditMode.CONNECT:
            if b:
                if self.pend is None:
                    self.pend = b
                    self._status = f"Click second block to connect to {b.id}"
                elif self.pend.id != b.id:
                    self.grid.connect(self.pend, b)
                    self._status = f"Connected {self.pend.id} <-> {b.id}"
                    self.pend = None
                else:
                    self.pend = None; self._status = "Cancelled"

        elif self.mode == EditMode.DISCONNECT:
            if b:
                if self.pend is None:
                    self.pend = b
                    self._status = f"Click second block to disconnect from {b.id}"
                elif self.pend.id != b.id:
                    self.grid.disconnect(self.pend, b)
                    self._status = f"Disconnected {self.pend.id} x {b.id}"
                    self.pend = None
                else:
                    self.pend = None; self._status = "Cancelled"

        elif self.mode == EditMode.GROUP:
            if b and self.act_group is not None:
                self.grid.add_to_group(b, self.act_group)
                g = self.grid.groups[self.act_group]
                self.sel_block = b
                self._status = (f"Added {b.id} to group {self.act_group} "
                                f"({len(g.block_ids)} members)")
            elif self.act_group is None:
                self._status = "Create a group first (press G)"

        elif self.mode == EditMode.UNGROUP:
            if b:
                self.grid.remove_from_group(b)
                self.sel_block = b
                self._status = f"Removed {b.id} from group"

    # ── Panel actions ─────────────────────────────────────────────

    def _panel_action(self, key: str) -> None:
        if key == "step":
            self.grid.tick()
            self._status = "Tick"
        elif key == "run":
            self.running = not self.running
            self.panel_btns["run"].label = (
                "PAUSE [R]" if self.running else "RUN   [R]"
            )
            self._status = "Simulation running" if self.running else "Simulation paused"
        elif key == "new_group":
            g = self.grid.new_group()
            self.act_group = g.id
            self._set_mode(EditMode.GROUP)
            self._status = f"Group {g.id} created — click blocks to add"
        elif key == "save":
            try:
                self.grid.save()
                self._status = "Saved -> redstone_save.json"
            except Exception as exc:
                self._status = f"Save error: {exc}"
        elif key == "load":
            try:
                self.grid.load()
                self.sel_block = self.pend = None
                self._status = "Loaded <- redstone_save.json"
            except FileNotFoundError:
                self._status = "redstone_save.json not found"
            except Exception as exc:
                self._status = f"Load error: {exc}"
        elif key == "clear":
            self.grid      = RedstoneGrid()
            self.sel_block = self.pend = None
            self.act_group = None
            self._status   = "Grid cleared"

    # ── Mode / type helpers ───────────────────────────────────────

    def _set_mode(self, m: EditMode) -> None:
        self.mode = m
        self.pend = None
        for i, btn in enumerate(self.mode_btns):
            btn.active = (self.ALL_MODES[i] == m)

    def _set_type(self, t: BlockType) -> None:
        self.sel_type = t
        for i, btn in enumerate(self.type_btns):
            btn.active = (self.ALL_TYPES[i] == t)
        self._status = f"Selected type: {t.value}"

    # ── Simulation update ─────────────────────────────────────────

    def _update(self, dt: int) -> None:
        if self.running:
            self._sim_acc += dt
            while self._sim_acc >= SIM_MS:
                self._sim_acc -= SIM_MS
                self.grid.tick()

    # ── Rendering ─────────────────────────────────────────────────

    def _render(self) -> None:
        self.screen.fill(C_BG)
        self._r_toolbar()
        self._r_grid_lines()
        self._r_connections()
        self._r_blocks()
        self._r_pending_wire()
        self._r_panel()
        self._r_statusbar()

    def _r_toolbar(self) -> None:
        pygame.draw.rect(self.screen, C_TOOLBAR, (0, 0, WIN_W, GY - 6))
        for btn in self.mode_btns:
            btn.draw(self.screen)
        for btn in self.type_btns:
            btn.draw(self.screen)

    def _r_grid_lines(self) -> None:
        for row in range(ROWS + 1):
            y0 = GY + row * CELL
            pygame.draw.line(self.screen, C_GRID,
                             (GX, y0), (GX + COLS * CELL, y0))
        for col in range(COLS + 1):
            x0 = GX + col * CELL
            pygame.draw.line(self.screen, C_GRID,
                             (x0, GY), (x0, GY + ROWS * CELL))

    def _r_connections(self) -> None:
        drawn: Set[FrozenSet] = set()
        for b in self.grid.all_blocks():
            for nid in b.connections:
                key: FrozenSet = frozenset([b.id, nid])
                if key in drawn:
                    continue
                drawn.add(key)
                nb = self.grid.get_by_id(nid)
                if not nb:
                    continue
                p1    = cell_rect(b.x, b.y).center
                p2    = cell_rect(nb.x, nb.y).center
                hot   = b.power > 0 or nb.power > 0
                color = (78, 218, 78) if hot else (38, 88, 38)
                pygame.draw.line(self.screen, color, p1, p2, 2)
                # midpoint marker
                mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
                pygame.draw.circle(self.screen, color, mid, 3)

    def _r_blocks(self) -> None:
        for b in self.grid.all_blocks():
            r = cell_rect(b.x, b.y)

            # Draw group border around the full cell
            if b.group_id is not None:
                g = self.grid.groups.get(b.group_id)
                if g:
                    pygame.draw.rect(self.screen, g.color, r, border_radius=5)

            inner = r.inflate(-6, -6)

            # Compute face colour: blend block base with state glow by power
            base = BLOCK_COLOR.get(b.type.value, (100, 100, 100))
            glow = STATE_GLOW.get(b.state.value, base)
            t    = b.power / 15.0
            face = tuple(int(base[i] * (1.0 - t) + glow[i] * t) for i in range(3))
            if b.transmission_blocked:
                face = (32, 32, 108)   # dark blue = locked

            draw_rounded(self.screen, face, inner, radius=4)

            # Selection highlight
            if self.sel_block and self.sel_block.id == b.id:
                draw_rounded(self.screen, C_SEL, inner, radius=4,
                             border=2, border_color=C_SEL)

            # Pending-connection highlight
            if self.pend and self.pend.id == b.id:
                draw_rounded(self.screen, C_PEND, inner, radius=4,
                             border=2, border_color=C_PEND)

            # Type symbol centred in block
            sym = TYPE_SYM.get(b.type.value, "?")
            st  = self.fn_md.render(sym, True, C_WHITE)
            self.screen.blit(st, st.get_rect(center=inner.center))

            # Power level (top-right corner)
            if b.power > 0:
                pw = self.fn_sm.render(str(b.power), True, C_SEL)
                self.screen.blit(pw, (inner.right - 11, inner.top + 1))

            # Locked indicator (bottom-left corner)
            if b.transmission_blocked:
                lk = self.fn_sm.render("[L]", True, (148, 148, 255))
                self.screen.blit(lk, (inner.left + 1, inner.bottom - 13))

    def _r_pending_wire(self) -> None:
        if self.pend and self.mode in (EditMode.CONNECT, EditMode.DISCONNECT):
            p1  = cell_rect(self.pend.x, self.pend.y).center
            p2  = pygame.mouse.get_pos()
            col = (78, 198, 78) if self.mode == EditMode.CONNECT else (198, 78, 78)
            pygame.draw.line(self.screen, col, p1, p2, 1)
            pygame.draw.circle(self.screen, col, p1, 5, 2)

    def _r_panel(self) -> None:
        panel = pygame.Rect(PANEL_X, GY - 8, PANEL_W, WIN_H - GY + 8)
        draw_rounded(self.screen, C_PANEL, panel, radius=7)

        # Use a mutable Y cursor for sequential text rendering
        yc = [GY - 2]

        def ln(text: str, color: Tuple = C_TEXT, font=None, indent: int = 6) -> None:
            f = font or self.fn_sm
            s = f.render(text, True, color)
            self.screen.blit(s, (PANEL_X + indent, yc[0]))
            yc[0] += s.get_height() + 2

        ln("── INSPECTOR ──", C_ACCENT, self.fn_lg)

        b = self.sel_block
        if b and b.alive:
            sc = STATE_GLOW.get(b.state.value, C_TEXT)
            ln(f"id      {b.id}",                              C_DIM)
            ln(f"type    {b.type.value}")
            ln(f"state   {b.state.value}",                     sc)
            ln(f"pos     ({b.x}, {b.y}, {b.z})")
            ln(f"power   {b.power}")
            ln(f"group   {b.group_id if b.group_id is not None else '-'}")
            ln(f"locked  {b.transmission_blocked}")
            ln(f"conns   {len(b.connections)}")
            if b.connections:
                for cid in list(b.connections)[:4]:
                    ln(f"  -> {cid}", C_DIM)
                if len(b.connections) > 4:
                    ln(f"  ... +{len(b.connections)-4} more", C_DIM)
            if b.saved_data:
                ln("saved data:", C_DIM)
                for line in self._wrap(json.dumps(b.saved_data, indent=None),
                                       PANEL_W - 16):
                    ln(line, (138, 218, 138))
        else:
            ln("(nothing selected)", C_DIM)

        yc[0] += 8

        # Active group info
        if self.act_group is not None:
            g = self.grid.groups.get(self.act_group)
            if g:
                ln(f"── GROUP {g.id} ──", g.color, self.fn_lg)
                ln(f"  members  {len(g.block_ids)}")
                ln(f"  color    RGB{g.color}")
        yc[0] += 8

        # Packet event log
        ln("── PACKET LOG ──", C_ACCENT, self.fn_md)
        log_top    = yc[0]
        # bottom boundary = first panel button
        log_bottom = self.panel_btns["step"].rect.top - 4
        for pkt in reversed(self.grid.log[-30:]):
            if yc[0] >= log_bottom:
                break
            hdr = (f"[{pkt['state'][:8]:8s}] "
                   f"({pkt['coord']['x']},{pkt['coord']['y']})")
            dat = str(pkt["data"])[:36]
            col = STATE_GLOW.get(pkt["state"], C_DIM)
            for line in self._wrap(hdr + " " + dat, PANEL_W - 14):
                if yc[0] >= log_bottom:
                    break
                ln(line, col)

        # Panel action buttons
        for btn in self.panel_btns.values():
            btn.draw(self.screen)

        # Current mode label at the very bottom of the panel
        ml = self.fn_lg.render(f"MODE: {self.mode.value}", True, C_ACCENT)
        self.screen.blit(ml, (PANEL_X + 4, WIN_H - 20))

    def _r_statusbar(self) -> None:
        y = WIN_H - 20
        sim_col = (48, 208, 48) if self.running else (198, 68, 48)
        sim_lbl = "RUN" if self.running else "STOP"
        sim_txt = self.fn_md.render(f"[{sim_lbl}]", True, sim_col)
        self.screen.blit(sim_txt, (GX, y))

        info = self.fn_md.render(
            f"  blocks:{len(self.grid.all_blocks())}  "
            f"groups:{len(self.grid.groups)}  "
            f"| {self._status[:72]}",
            True, C_DIM,
        )
        self.screen.blit(info, (GX + 58, y))

    # ── Text-wrap helper ──────────────────────────────────────────

    def _wrap(self, text: str, max_w: int) -> List[str]:
        words  = text.split()
        lines: List[str] = []
        cur    = ""
        for w in words:
            test = (cur + " " + w).strip()
            if self.fn_sm.size(test)[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [text[:50]]


# ══════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════

def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
