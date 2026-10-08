"""Flow duration curve and run-of-river hydropower calculator (pre-feasibility)."""
from .data import HydroError, Record, build_record, load_csv, parse_values, HOURS_PER_YEAR
from .fdc import POSITIONS, plotting_positions, fdc, flow_at, percentile_table
from .turbines import TURBINES, Turbine, constant_turbine
from .plant import Plant, flow_split, simulate, summarize, design_from_exceedance
from .economics import Economics, compute_economics
from .optimum import sweep, find_knee, cost_optimum, design_range

__version__ = "1.0.0"
