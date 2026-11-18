"""Pure math functions for mouse kinematics and sample entropy."""

import math
from collections.abc import Sequence


def compute_sample_entropy(
    data: Sequence[float],
    m: int = 2,
    r: float | None = None,
) -> float:
    """Compute Sample Entropy (SampEn) over continuous time-series (e.g. mouse velocity)."""
    n = len(data)
    if n <= m + 1:
        return 0.0

    mean_val = sum(data) / n
    variance = sum((x - mean_val) ** 2 for x in data) / n
    std_dev = math.sqrt(variance)
    if std_dev == 0.0:
        return 0.0

    tolerance = r if r is not None else 0.2 * std_dev

    def _count_matches(template_len: int) -> int:
        count = 0
        limit = n - template_len
        for i in range(limit):
            for j in range(i + 1, limit + 1):
                diffs = [abs(data[i + k] - data[j + k]) for k in range(template_len)]
                if max(diffs) <= tolerance:
                    count += 1
        return count

    a = _count_matches(m + 1)
    b = _count_matches(m)
    if b == 0 or a == 0:
        return 0.0
    return round(-math.log(a / b), 4)


def compute_mouse_kinematics(
    points: Sequence[tuple[float, float, float]],
) -> tuple[float, int, float, int]:
    """Compute (sample_entropy, submovements, curvature_auc, x_flips) from mouse trajectory."""
    if len(points) < 4:
        return 0.0, 0, 0.0, 0

    velocities: list[float] = []
    accelerations: list[float] = []
    x_positions: list[float] = [points[0][0]]
    total_path_length = 0.0

    for i in range(1, len(points)):
        x0, y0, t0 = points[i - 1]
        x1, y1, t1 = points[i]
        dt = max(1e-4, t1 - t0)
        dist = math.hypot(x1 - x0, y1 - y0)
        total_path_length += dist
        v = dist / dt
        velocities.append(v)
        x_positions.append(x1)

    for i in range(1, len(velocities)):
        dt = max(1e-4, points[i + 1][2] - points[i][2])
        dv = velocities[i] - velocities[i - 1]
        accelerations.append(dv / dt)

    submovements = 0
    for i in range(1, len(accelerations)):
        if (accelerations[i - 1] < 0.0 <= accelerations[i]) or (
            accelerations[i - 1] > 0.0 >= accelerations[i]
        ):
            submovements += 1

    x_flips = 0
    for i in range(2, len(x_positions)):
        dx_prev = x_positions[i - 1] - x_positions[i - 2]
        dx_curr = x_positions[i] - x_positions[i - 1]
        if (dx_prev < 0.0 < dx_curr) or (dx_prev > 0.0 > dx_curr):
            x_flips += 1

    x_start, y_start, _ = points[0]
    x_end, y_end, _ = points[-1]
    straight_line_dist = math.hypot(x_end - x_start, y_end - y_start)
    curvature_auc = (
        round(total_path_length / straight_line_dist, 4) if straight_line_dist > 1e-3 else 0.0
    )
    samp_en = compute_sample_entropy(velocities, m=2)

    return samp_en, submovements, curvature_auc, x_flips
