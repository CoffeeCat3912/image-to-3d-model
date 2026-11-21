"""build123d template for path B. Copy, edit the numbers and shapes, keep `result`.

Units are millimetres. Z is up, the part sits on Z=0. The default example is a
box with a slip-on lid and a cable hole.
"""

from build123d import Align, Box, Cylinder, Pos, Rot

LENGTH = 80.0
WIDTH = 50.0
HEIGHT = 30.0
WALL = 2.0
FLOOR = 2.0
LID_THICKNESS = 2.0
LIP_HEIGHT = 4.0
CLEARANCE = 0.3
HOLE_DIAMETER = 6.0

BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)

outer = Box(LENGTH, WIDTH, HEIGHT, align=BOTTOM)
cavity = Pos(0, 0, FLOOR) * Box(LENGTH - 2 * WALL, WIDTH - 2 * WALL, HEIGHT, align=BOTTOM)
hole = Pos(LENGTH / 2, 0, HEIGHT / 2) * Rot(0, 90, 0) * Cylinder(HOLE_DIAMETER / 2, 4 * WALL)
body = outer - cavity - hole

lip_length = LENGTH - 2 * WALL - 2 * CLEARANCE
lip_width = WIDTH - 2 * WALL - 2 * CLEARANCE
lid = Box(LENGTH, WIDTH, LID_THICKNESS, align=BOTTOM) + Pos(0, 0, LID_THICKNESS) * Box(
    lip_length, lip_width, LIP_HEIGHT, align=BOTTOM
)

result = body + Pos(0, WIDTH + 10, 0) * lid
