"""Bidirectional solar net-metering maths (single phase)."""
from __future__ import annotations


def net_current(i_load: float, i_solar: float) -> float:
    """I_net = I_load - I_solar (positive = importing)."""
    return float(i_load) - float(i_solar)


def net_power_kw(v_rms: float, i_net: float) -> float:
    """P_net = V_rms * I_net / 1000, in kW (paper Eq. 1 uses /1000 -> kW)."""
    return float(v_rms) * float(i_net) / 1000.0


class EnergyMeter:
    """Integrates net power into cumulative import/export counters."""

    def __init__(self, import_kwh: float = 0.0, export_kwh: float = 0.0):
        self.import_kwh = float(import_kwh)
        self.export_kwh = float(export_kwh)

    def update(self, v_rms: float, i_load: float, i_solar: float, dt_seconds: float) -> dict[str, float]:
        dt = max(0.0, min(float(dt_seconds), 60.0))
        p_net = net_power_kw(v_rms, net_current(i_load, i_solar))
        delta_kwh = p_net * dt / 3600.0
        if delta_kwh >= 0:
            self.import_kwh += delta_kwh
        else:
            self.export_kwh += -delta_kwh
        return {
            "i_net": net_current(i_load, i_solar),
            "p_net_kw": p_net,
            "energy_import_kwh": self.import_kwh,
            "energy_export_kwh": self.export_kwh,
        }

    def snapshot(self) -> dict[str, float]:
        return {
            "energy_import_kwh": self.import_kwh,
            "energy_export_kwh": self.export_kwh,
        }
