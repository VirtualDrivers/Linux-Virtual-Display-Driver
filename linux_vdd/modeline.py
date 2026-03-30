"""
CVT (Coordinated Video Timing) modeline generator.

Implements the VESA CVT v1.2 standard to compute video timing parameters
from a target resolution and refresh rate. Produces modeline strings
compatible with xrandr --newmode.
"""

import math


def generate_modeline(h_pixels: int, v_lines: int, refresh: float,
                      reduced_blanking: bool = False) -> dict:
    """
    Generate a CVT modeline for the given resolution and refresh rate.

    Args:
        h_pixels: Horizontal resolution in pixels.
        v_lines: Vertical resolution in lines.
        refresh: Target refresh rate in Hz.
        reduced_blanking: Use reduced blanking (lower bandwidth, for LCDs).

    Returns:
        Dict with keys: name, clock, h_disp, h_sync_start, h_sync_end,
        h_total, v_disp, v_sync_start, v_sync_end, v_total,
        h_sync_pol, v_sync_pol, modeline_args (list for xrandr --newmode).
    """
    if reduced_blanking:
        return _cvt_reduced(h_pixels, v_lines, refresh)
    else:
        return _cvt_standard(h_pixels, v_lines, refresh)


def _cvt_standard(h_pixels: int, v_lines: int, refresh: float) -> dict:
    """CVT standard (traditional) blanking computation."""

    # CVT constants
    CELL_GRAN = 8
    MIN_V_PORCH = 3
    MIN_VSYNC_BP = 550.0      # us
    H_SYNC_PER = 8.0          # %
    MIN_V_BPORCH = 6

    # Blanking formula constants
    C_PRIME = 30.0
    M_PRIME = 300.0

    # V-sync width by aspect ratio
    v_sync = _vsync_width(h_pixels, v_lines)

    # Round horizontal pixels to character cell granularity
    h_pixels_rnd = math.floor(h_pixels / CELL_GRAN) * CELL_GRAN

    # Estimate horizontal period (us)
    h_period_est = ((1.0 / refresh) - MIN_VSYNC_BP / 1000000.0) / \
                   (v_lines + MIN_V_PORCH) * 1000000.0

    # Vertical sync + back porch
    vsync_bp = max(math.floor(MIN_VSYNC_BP / h_period_est) + 1, MIN_V_BPORCH + v_sync)
    v_back_porch = vsync_bp - v_sync

    # Total vertical lines
    v_total = v_lines + MIN_V_PORCH + vsync_bp

    # Ideal blanking duty cycle (%)
    ideal_duty = C_PRIME - (M_PRIME * h_period_est / 1000.0)

    if ideal_duty < 20.0:
        # Use lower bound
        h_blank = math.floor(h_pixels_rnd * 20.0 / (100.0 - 20.0) /
                             (2.0 * CELL_GRAN)) * 2 * CELL_GRAN
    else:
        h_blank = math.floor(h_pixels_rnd * ideal_duty / (100.0 - ideal_duty) /
                             (2.0 * CELL_GRAN)) * 2 * CELL_GRAN

    # Total horizontal pixels
    h_total = h_pixels_rnd + h_blank

    # Pixel clock (MHz) - round to nearest 0.25 MHz
    pixel_clock = math.floor(h_total / h_period_est * 1000000.0) / 1000000.0
    pixel_clock = math.ceil(pixel_clock * 4.0) / 4.0

    # Recalculate actual horizontal period
    h_period = h_total / (pixel_clock * 1000000.0) * 1000000.0

    # Horizontal sync
    h_sync = math.floor(h_total * H_SYNC_PER / 100.0 / CELL_GRAN) * CELL_GRAN

    # Horizontal front porch
    h_front_porch = (h_blank / 2) - h_sync

    # Timing values
    h_sync_start = h_pixels_rnd + h_front_porch
    h_sync_end = h_sync_start + h_sync

    v_sync_start = v_lines + MIN_V_PORCH
    v_sync_end = v_sync_start + v_sync

    # Actual refresh rate
    actual_refresh = pixel_clock * 1000000.0 / (h_total * v_total)

    return _build_result(
        h_pixels_rnd, v_lines, actual_refresh, pixel_clock,
        int(h_sync_start), int(h_sync_end), int(h_total),
        int(v_sync_start), int(v_sync_end), int(v_total),
        "-HSync", "+VSync"
    )


def _cvt_reduced(h_pixels: int, v_lines: int, refresh: float) -> dict:
    """CVT reduced blanking computation (v1)."""

    # Reduced blanking constants
    RB_H_BLANK = 160
    RB_H_SYNC = 32
    RB_H_FPORCH = 48
    RB_V_FPORCH = 3
    RB_MIN_V_BLANK = 460.0  # us
    CELL_GRAN = 8

    v_sync = _vsync_width(h_pixels, v_lines)

    # Round horizontal pixels
    h_pixels_rnd = math.floor(h_pixels / CELL_GRAN) * CELL_GRAN

    # Estimate horizontal period
    h_period_est = ((1000000.0 / refresh) - RB_MIN_V_BLANK) / v_lines

    # Vertical blank lines
    vbi_lines = math.floor(RB_MIN_V_BLANK / h_period_est) + 1
    rb_min_vbi = RB_V_FPORCH + v_sync + 1
    act_vbi_lines = max(vbi_lines, rb_min_vbi)

    v_total = v_lines + act_vbi_lines
    h_total = h_pixels_rnd + RB_H_BLANK

    # Pixel clock
    pixel_clock = math.ceil(refresh * h_total * v_total / 1000000.0 * 4.0) / 4.0

    actual_refresh = pixel_clock * 1000000.0 / (h_total * v_total)

    h_sync_start = h_pixels_rnd + RB_H_FPORCH
    h_sync_end = h_sync_start + RB_H_SYNC

    v_sync_start = v_lines + RB_V_FPORCH
    v_sync_end = v_sync_start + v_sync

    return _build_result(
        h_pixels_rnd, v_lines, actual_refresh, pixel_clock,
        int(h_sync_start), int(h_sync_end), int(h_total),
        int(v_sync_start), int(v_sync_end), int(v_total),
        "+HSync", "-VSync"
    )


def _vsync_width(h_pixels: int, v_lines: int) -> int:
    """Determine vertical sync width from aspect ratio (CVT table)."""
    aspect = h_pixels / v_lines
    if abs(aspect - 4.0 / 3.0) < 0.02:
        return 4
    elif abs(aspect - 16.0 / 9.0) < 0.02:
        return 5
    elif abs(aspect - 16.0 / 10.0) < 0.02:
        return 6
    elif abs(aspect - 5.0 / 4.0) < 0.02:
        return 7
    elif abs(aspect - 15.0 / 9.0) < 0.02:
        return 7
    elif abs(aspect - 21.0 / 9.0) < 0.1:
        return 5
    else:
        return 10  # safe default


def _build_result(h_disp, v_disp, refresh, clock,
                  h_sync_start, h_sync_end, h_total,
                  v_sync_start, v_sync_end, v_total,
                  h_sync_pol, v_sync_pol) -> dict:
    """Build the result dict and modeline string."""

    name = f"{h_disp}x{v_disp}_{refresh:.2f}"
    clock_rounded = round(clock, 2)

    modeline_args = [
        name,
        str(clock_rounded),
        str(h_disp), str(h_sync_start), str(h_sync_end), str(h_total),
        str(v_disp), str(v_sync_start), str(v_sync_end), str(v_total),
        h_sync_pol, v_sync_pol,
    ]

    return {
        "name": name,
        "clock": clock_rounded,
        "h_disp": h_disp,
        "h_sync_start": h_sync_start,
        "h_sync_end": h_sync_end,
        "h_total": h_total,
        "v_disp": v_disp,
        "v_sync_start": v_sync_start,
        "v_sync_end": v_sync_end,
        "v_total": v_total,
        "h_sync_pol": h_sync_pol,
        "v_sync_pol": v_sync_pol,
        "refresh": round(refresh, 2),
        "modeline_args": modeline_args,
    }
