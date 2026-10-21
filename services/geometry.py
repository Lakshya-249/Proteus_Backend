"""Pure-Python internal-coordinate geometry (NeRF). No third-party deps."""
from __future__ import annotations

from math import cos, radians, sin, sqrt

Vec = tuple[float, float, float]


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(v: Vec, s: float) -> Vec:
    return (v[0] * s, v[1] * s, v[2] * s)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(v: Vec) -> float:
    return sqrt(dot(v, v))


def normalize(v: Vec) -> Vec:
    length = norm(v)
    if length < 1e-12:
        raise ValueError("Cannot normalize zero-length vector.")
    return scale(v, 1.0 / length)


def place_atom(
    a: Vec, b: Vec, c: Vec, length: float, angle_deg: float, dihedral_deg: float
) -> Vec:
    """Place D so that |C-D| = length, angle B-C-D = angle, dihedral A-B-C-D = dihedral
    (IUPAC sign convention)."""
    bc = normalize(sub(c, b))
    n = cross(sub(b, a), bc)
    if norm(n) < 1e-8:  # a, b, c collinear: pick any perpendicular
        helper = (0.0, 0.0, 1.0) if abs(bc[2]) < 0.9 else (0.0, 1.0, 0.0)
        n = cross(helper, bc)
    n = normalize(n)
    m = cross(n, bc)

    theta = radians(angle_deg)
    phi = radians(dihedral_deg)
    d_local = (
        -length * cos(theta),
        length * sin(theta) * cos(phi),
        length * sin(theta) * sin(phi),
    )
    return (
        c[0] + d_local[0] * bc[0] + d_local[1] * m[0] + d_local[2] * n[0],
        c[1] + d_local[0] * bc[1] + d_local[1] * m[1] + d_local[2] * n[1],
        c[2] + d_local[0] * bc[2] + d_local[1] * m[2] + d_local[2] * n[2],
    )


def place_cbeta(n: Vec, ca: Vec, c: Vec) -> Vec:
    """Ideal C-beta position from the backbone N, CA, C (standard trigonal formula)."""
    b = sub(ca, n)
    cc = sub(c, ca)
    a = cross(b, cc)
    return (
        -0.58273431 * a[0] + 0.56802827 * b[0] - 0.54067466 * cc[0] + ca[0],
        -0.58273431 * a[1] + 0.56802827 * b[1] - 0.54067466 * cc[1] + ca[1],
        -0.58273431 * a[2] + 0.56802827 * b[2] - 0.54067466 * cc[2] + ca[2],
    )


def dihedral(p0: Vec, p1: Vec, p2: Vec, p3: Vec) -> float:
    """IUPAC dihedral in degrees (used by tests and clash/Ramachandran checks)."""
    from math import atan2, degrees

    b0 = sub(p0, p1)
    b1 = normalize(sub(p2, p1))
    b2 = sub(p3, p2)
    v = sub(b0, scale(b1, dot(b0, b1)))
    w = sub(b2, scale(b1, dot(b2, b1)))
    return degrees(atan2(dot(cross(b1, v), w), dot(v, w)))
