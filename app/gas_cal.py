import math

def tank_volume_cylindrical(
    radius: float,
    length: float,
    fill_height: float,
    unit: str = "m"
) -> float:
    """Volume of a horizontal cylindrical tank for a given fill height in liters."""
    if radius <= 0 or length <= 0:
        raise ValueError("Radius and length must be positive.")

    unit = unit.lower()
    volume_to_liters = {
        "m": 1000.0,          # 1 m³ = 1000 L
        "cm": 1.0 / 1000.0,   # 1 cm³ = 0.001 L
        "mm": 1.0 / 1_000_000.0  # 1 mm³ = 1e-6 L
    }.get(unit)
    if volume_to_liters is None:
        raise ValueError("unit must be one of 'm', 'cm', or 'mm'.")

    # Clamp the fill height to the physical bounds of the tank
    h = max(0.0, min(fill_height, 2.0 * radius))

    if h == 0.0:
        return 0.0
    if abs(h - 2.0 * radius) < 1e-12:
        return math.pi * radius * radius * length * volume_to_liters

    # Segment area of the circular cross-section
    # Clamp argument to avoid domain errors from floating-point noise
    cos_arg = (radius - h) / radius
    cos_arg = max(-1.0, min(1.0, cos_arg))
    segment_area = (
        radius * radius * math.acos(cos_arg)
        - (radius - h) * math.sqrt(max(0.0, 2.0 * radius * h - h * h))
    )

    volume = segment_area * length
    return volume * volume_to_liters


def tank_volume_cylindrical_diameter(
    diameter: float,
    length: float,
    fill_height: float,
    unit: str = "cm"
) -> float:
    """Convenience wrapper that accepts diameter instead of radius and returns liters."""
    if diameter <= 0:
        raise ValueError("Diameter must be positive.")

    radius = diameter / 2.0
    return tank_volume_cylindrical(radius, length, fill_height, unit=unit)
