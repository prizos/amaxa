"""
Every part on cpu1, as data.

The same shape as every board's part list: `PartSpec` from
`hw/tools/partspec.py`, a KiCad symbol, a footprint in this board's own
`parts/` tree, and the datasheet figures the checks reason about. Each value
comes from the part's review note in `parts/<LIB>/<LIB>.md`.

cpu1 is being built one block at a time, so this list grows with it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from partspec import PartSpec, between, collect, exact, pm  # noqa: E402,F401


# --- the MCU -----------------------------------------------------------------

MCU_H743 = PartSpec(
    symbol="MCU_ST_STM32H7:STM32H743ZITx", footprint="LQFP144:LQFP-144_20x20mm_P0.5mm",
    prefix="U", manufacturer="STMicroelectronics", mpn="STM32H743ZIT6", lcsc="C114408",
    value="STM32H743ZIT6",
    params={"supply_voltage": between(1.62, 3.6)},
)


ALL: dict[str, PartSpec] = collect(globals())
"""Every part, by the name it is known by here. Used by the parts checks."""
