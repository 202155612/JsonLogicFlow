# constant.py
from enum import Enum, auto

class FrameType(Enum):
    SCRIPT = auto()
    BLOCK = auto()
    LOOP = auto()

class ScopeType(str, Enum):
    LOCAL = "local"
    FRAME = "frame"
    KWARGS = "kwargs"
    GLOBAL = "global"

MAX_LOOP_ITERATIONS = 10000