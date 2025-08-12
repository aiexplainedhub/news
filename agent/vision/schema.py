from dataclasses import dataclass

@dataclass
class Detection:
    name: str
    center_x: int
    center_y: int
    width: int
    height: int
    conf: float
