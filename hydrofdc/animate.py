"""Matplotlib animation of one year: hydrograph with a moving marker, the flow split and the energy counter.
It is a schematic aid for understanding, not a to-scale model."""
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter, FFMpegWriter
from matplotlib.patches import Patch

from .data import HydroError
from .plant import simulate
from .plots import C_ENV, C_SPILL, C_USE


def make_animation(rec, plant, q_design, path, year=None, frame_step=None, fps=12, dpi=80):
    path = str(path)
    if not path.lower().endswith((".gif", ".mp4")):
        raise HydroError("Animation file name must end in .gif or .mp4.")
    if path.lower().endswith(".mp4") and not matplotlib.animation.writers.is_available("ffmpeg"):
        raise HydroError("Saving MP4 needs the free program ffmpeg. Save as .gif instead, or install ffmpeg.")
    sim = simulate(rec, plant, q_design)
    years = rec.dates.year.to_numpy()
    expected = 365 if rec.step == "daily" else 12
    if year is None:
        for y in np.unique(years):
            if np.sum((years == y) & rec.valid) >= 0.9 * expected:
                year = int(y)
                break
        if year is None:
            raise HydroError("No calendar year in the record is nearly complete, so I cannot animate a whole year.")
    idx = np.flatnonzero(years == year)
    if len(idx) == 0:
        raise HydroError(f"The record has no data for {year}.")
    dates = rec.dates[idx].to_pydatetime()
    q, env, turb, spill, power = (a[idx] for a in (sim.q, sim.env, sim.turb, sim.spill, sim.power_kw))
    cum = np.cumsum(sim.energy_kwh[idx])
    vh = np.cumsum(np.where(rec.valid[idx], rec.hours[idx], 0.0))
    cf = np.divide(cum, sim.installed_kw * vh, out=np.zeros_like(cum), where=(vh > 0) & (sim.installed_kw > 0))
    ymax = float(np.nanmax(q)) * 1.08
    if frame_step is None:
        frame_step = max(1, len(idx) // 90)
    frames = list(range(0, len(idx), frame_step))
    if frames[-1] != len(idx) - 1:
        frames.append(len(idx) - 1)

    fig = plt.figure(figsize=(9, 6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.1, 1], width_ratios=[1, 1.4])
    ax1, ax2, ax3 = fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])
    ax1.plot(dates, q, color="black", lw=1.2, label="River flow")
    rq = plant.river_flow_at_design(q_design)
    if np.isfinite(rq) and rq < ymax:
        ax1.axhline(rq, color="black", ls="--", lw=0.9, label=f"River flow at which turbine is full ({rq:.1f} m3/s)")
    (mark,) = ax1.plot([], [], "o", color="red", ms=9, label="Current day" if rec.step == "daily" else "Current month")
    ax1.set_ylabel("River flow (m3/s)")
    ax1.set_title(f"Simulation playback, {year} (schematic, not to scale)")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8, loc="upper right")

    bars = [ax2.bar([0], [0], color=C_ENV, hatch="..", edgecolor="white", width=0.6)[0],
            ax2.bar([0], [0], color=C_USE, edgecolor="white", width=0.6)[0],
            ax2.bar([0], [0], color=C_SPILL, hatch="//", edgecolor="white", width=0.6)[0]]
    ax2.set_ylim(0, ymax)
    ax2.set_xlim(-0.6, 0.6)
    ax2.set_xticks([])
    ax2.set_ylabel("Flow (m3/s)")
    ax2.set_title("Flow split at the intake", fontsize=10)
    ax2.legend(handles=[Patch(facecolor=C_ENV, hatch="..", label="Environmental (stays in river)"),
                        Patch(facecolor=C_USE, label="Turbine (penstock)"),
                        Patch(facecolor=C_SPILL, hatch="//", label="Spill over weir")], fontsize=7, loc="upper right")
    ax3.axis("off")
    txt = ax3.text(0, 1, "", va="top", ha="left", family="monospace", fontsize=10)

    def update(k):
        mark.set_data([dates[k]], [q[k]])
        lows = (0.0, env[k], env[k] + turb[k])
        highs = (env[k], turb[k], spill[k])
        for b, y0, h in zip(bars, lows, highs):
            b.set_y(0 if np.isnan(y0) else y0)
            b.set_height(0 if np.isnan(h) else h)
        if np.isnan(q[k]):
            state = "NO DATA for this step"
        elif turb[k] <= 0:
            state = "BELOW MINIMUM FLOW, NOT GENERATING"
        else:
            state = "Generating"
        txt.set_text(
            f"Date:               {dates[k]:%d %b %Y}\n"
            f"River flow:         {q[k]:8.2f} m3/s\n"
            f"Environmental flow: {env[k]:8.2f} m3/s\n"
            f"Turbine flow:       {turb[k]:8.2f} m3/s\n"
            f"Spill flow:         {spill[k]:8.2f} m3/s\n"
            f"Power:              {0 if np.isnan(power[k]) else power[k]:8.0f} kW (installed {sim.installed_kw:,.0f})\n"
            f"Energy this year:   {cum[k] / 1000:8.1f} MWh\n"
            f"Running cap. factor:{100 * cf[k]:7.1f} %\n\n"
            f"Status: {state}")
        return ()

    fig.tight_layout()
    anim = FuncAnimation(fig, update, frames=frames, interval=1000 / fps, blit=False)
    writer = FFMpegWriter(fps=fps) if path.lower().endswith(".mp4") else PillowWriter(fps=fps)
    anim.save(path, writer=writer, dpi=dpi)
    plt.close(fig)
    return path
