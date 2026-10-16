"""Convert calibrated sensor signals into WBGT-ready environmental inputs."""
import math


def wind_voltage_to_ms(voltage, cfg):
    """Convert cup-anemometer voltage to speed at sensor height (m/s)."""
    voltage = float(voltage)
    if voltage < 0 or not math.isfinite(voltage):
        raise ValueError("Invalid anemometer voltage")
    if voltage < cfg["wind_voltage_min"]:
        return 0.0
    return max(0.0, cfg["wind_k"] * voltage + cfg["wind_b"])


def wind_to_10m(speed_at_sensor, sensor_height, cfg):
    """Apply the logarithmic wind profile to estimate standard 10-m wind."""
    z0 = cfg["surface_roughness_m"]
    if sensor_height <= z0 or z0 <= 0 or z0 >= 10:
        raise ValueError("Invalid sensor height or roughness length")
    return speed_at_sensor * math.log(10.0 / z0) / math.log(sensor_height / z0)


def lux_to_solar_wm2(lux, cfg):
    """Approximate global solar irradiance from illuminance (calibration required)."""
    lux = float(lux)
    if not math.isfinite(lux) or lux < 0:
        raise ValueError("Invalid illuminance")
    return lux / cfg["lux_per_wm2"]
