from ursina import color

STATE_COLORS = {
    "stem": color.green,
    "worker": color.blue,
    "defender": color.red,
    "sensor": color.cyan,
    "memory": color.violet,
    "energy": color.yellow,
    "replicate": color.green.tint(-0.2),
    "signal": color.orange,
    "differentiate": color.magenta,
    "absorb": color.pink,
    "default": color.white,
    "active": color.red,
    "inactive": color.gray,
    "selected": color.azure,
    "dying": color.black,
    "generate_blocks": color.green,
    "store": color.violet,
    "conduct": color.cyan,
    "connect": color.orange,
}

CELL_TYPES = {
    "stem": {"color": color.green, "energy": 100, "replication_rate": 0.1, "signal_strength": 1.0},
    "worker": {"color": color.blue, "energy": 50, "replication_rate": 0.05, "signal_strength": 0.5},
    "defender": {"color": color.red, "energy": 150, "replication_rate": 0.02, "signal_strength": 0.8},
    "sensor": {"color": color.cyan, "energy": 30, "replication_rate": 0.03, "signal_strength": 1.5},
    "memory": {"color": color.violet, "energy": 80, "replication_rate": 0.01, "signal_strength": 0.3},
    "energy": {"color": color.yellow, "energy": 200, "replication_rate": 0.08, "signal_strength": 0.2},
}

CELL_GRID_SIZE = 30
MAX_CELLS = 500

FIELD_SHELL_DEFAULT_RADIUS = 4
FIELD_SHELL_CUBE_SCALE = 0.92
FIELD_SHELL_SHAPE = "cube"
FIELD_SHELL_COLORS = {
    "cyan": color.rgba(130, 210, 255, 75),
    "green": color.rgba(95, 220, 130, 75),
    "yellow": color.rgba(255, 235, 110, 75),
    "red": color.rgba(255, 115, 115, 75),
}
