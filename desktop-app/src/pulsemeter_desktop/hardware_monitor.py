import platform
import sys
from pathlib import Path


HARDWARE_METRIC_LABELS = {
    "cpu_temp": "CPU Temp",
    "cpu_power": "CPU Power",
    "cpu_clock": "CPU Clock",
    "cpu_voltage": "CPU Voltage",
    "gpu_temp": "GPU Temp",
    "gpu_power": "GPU Power",
    "storage_temp": "SSD Temp",
    "gpu_load": "GPU Load",
    "gpu_core_clock": "GPU Core Clock",
    "gpu_memory_clock": "GPU Memory Clock",
    "gpu_memory_load": "GPU Memory Load",
    "motherboard_temp": "Mainboard Temp",
    "fan_speed": "Fan Speed",
}
HARDWARE_METRIC_KEYS = set(HARDWARE_METRIC_LABELS.keys())


class LibreHardwareMonitorProvider:
    """Windows-only hardware sensor provider backed by LibreHardwareMonitorLib."""

    def __init__(self) -> None:
        self._computer = None
        self._available = False
        self._error: str | None = None
        self._init_provider()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    def get_available_metric_keys(self) -> list[str]:
        if not self._available:
            return []
        return list(HARDWARE_METRIC_LABELS.keys())

    def get_metric_issue(self, metric_key: str, has_value: bool) -> str | None:
        if metric_key not in HARDWARE_METRIC_KEYS or has_value:
            return None
        if not self._available:
            if self._error:
                return self._error
            return "LibreHardwareMonitor is unavailable"
        return (
            f"{HARDWARE_METRIC_LABELS.get(metric_key, metric_key)} sensor unavailable. "
            "Try running PulseMeter as administrator."
        )

    def close(self) -> None:
        if self._computer is None:
            return
        try:
            self._computer.Close()
        except Exception:
            pass
        self._computer = None

    def read(self, metric_keys: list[str]) -> dict[str, float]:
        if not self._available or self._computer is None:
            return {}

        requested = set(metric_keys)
        data: dict[str, float] = {}

        try:
            for hardware in self._computer.Hardware:
                self._update_hardware(hardware)
                self._collect_hardware(hardware, requested, data)
        except Exception as exc:
            self._error = f"sensor refresh failed: {exc}"
            return {}

        return data

    def _init_provider(self) -> None:
        if platform.system() != "Windows":
            self._error = "LibreHardwareMonitor is only supported on Windows"
            return

        dll_path = self._resolve_dll_path()
        if dll_path is None:
            self._error = (
                "LibreHardwareMonitorLib.dll not found in "
                "pulsemeter_desktop/vendor/librehardwaremonitor."
            )
            return

        try:
            import clr  # type: ignore
        except ImportError:
            self._error = "pythonnet is not installed"
            return

        try:
            dll_dir = str(dll_path.parent)
            if dll_dir not in sys.path:
                sys.path.append(dll_dir)
            clr.AddReference(str(dll_path))
            from LibreHardwareMonitor.Hardware import Computer  # type: ignore
        except Exception as exc:
            self._error = f"failed to load LibreHardwareMonitorLib.dll: {exc}"
            return

        try:
            computer = Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.IsMemoryEnabled = True
            computer.IsMotherboardEnabled = True
            computer.IsControllerEnabled = True
            computer.IsStorageEnabled = True
            computer.IsNetworkEnabled = True
            computer.Open()
        except Exception as exc:
            self._error = f"failed to open hardware monitor: {exc}"
            return

        self._computer = computer
        self._available = True
        self._error = None

    def _resolve_dll_path(self) -> Path | None:
        module_root = Path(__file__).resolve().parent
        exe_root = Path(sys.executable).resolve().parent
        frozen_root = Path(getattr(sys, "_MEIPASS", module_root))
        relative_vendor_path = Path("vendor") / "librehardwaremonitor"
        candidates = [
            module_root / relative_vendor_path / "LibreHardwareMonitorLib.dll",
            exe_root / relative_vendor_path / "LibreHardwareMonitorLib.dll",
            frozen_root / relative_vendor_path / "LibreHardwareMonitorLib.dll",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _update_hardware(self, hardware) -> None:
        hardware.Update()
        for subhardware in hardware.SubHardware:
            self._update_hardware(subhardware)

    def _collect_hardware(
        self,
        hardware,
        requested: set[str],
        data: dict[str, float],
    ) -> None:
        hardware_type = str(hardware.HardwareType)
        for sensor in hardware.Sensors:
            self._collect_sensor(hardware_type, sensor, requested, data)
        for subhardware in hardware.SubHardware:
            self._collect_hardware(subhardware, requested, data)

    def _collect_sensor(
        self,
        hardware_type: str,
        sensor,
        requested: set[str],
        data: dict[str, float],
    ) -> None:
        value = sensor.Value
        if value is None:
            return

        sensor_type = str(sensor.SensorType)
        sensor_name = str(sensor.Name).lower()
        sensor_value = float(value)
        hardware_type_lc = hardware_type.lower()

        if hardware_type_lc == "cpu":
            if "cpu_temp" in requested and sensor_type == "Temperature":
                self._put_max(data, "cpu_temp", sensor_value)
            if (
                "cpu_power" in requested
                and sensor_type == "Power"
                and ("package" in sensor_name or "cpu" in sensor_name)
            ):
                self._put_max(data, "cpu_power", sensor_value)
            if "cpu_clock" in requested and sensor_type == "Clock":
                self._put_max(data, "cpu_clock", sensor_value)
            if (
                "cpu_voltage" in requested
                and sensor_type == "Voltage"
                and any(token in sensor_name for token in ("core", "vcore", "cpu"))
            ):
                self._put_max(data, "cpu_voltage", sensor_value)

        if hardware_type_lc.startswith("gpu"):
            if "gpu_temp" in requested and sensor_type == "Temperature":
                self._put_max(data, "gpu_temp", sensor_value)
            if (
                "gpu_load" in requested
                and sensor_type == "Load"
                and ("core" in sensor_name or "gpu" in sensor_name)
            ):
                self._put_max(data, "gpu_load", sensor_value)
            if (
                "gpu_power" in requested
                and sensor_type == "Power"
                and any(token in sensor_name for token in ("package", "board", "gpu"))
            ):
                self._put_max(data, "gpu_power", sensor_value)
            if (
                "gpu_core_clock" in requested
                and sensor_type == "Clock"
                and any(token in sensor_name for token in ("core", "graphics", "gpu"))
            ):
                self._put_max(data, "gpu_core_clock", sensor_value)
            if (
                "gpu_memory_clock" in requested
                and sensor_type == "Clock"
                and "memory" in sensor_name
            ):
                self._put_max(data, "gpu_memory_clock", sensor_value)
            if (
                "gpu_memory_load" in requested
                and sensor_type == "Load"
                and "memory" in sensor_name
            ):
                self._put_max(data, "gpu_memory_load", sensor_value)

        if (
            "storage_temp" in requested
            and hardware_type_lc == "storage"
            and sensor_type == "Temperature"
        ):
            self._put_max(data, "storage_temp", sensor_value)

        if (
            "motherboard_temp" in requested
            and hardware_type_lc == "motherboard"
            and sensor_type == "Temperature"
        ):
            self._put_max(data, "motherboard_temp", sensor_value)

        if "fan_speed" in requested and sensor_type == "Fan":
            self._put_max(data, "fan_speed", sensor_value)

    @staticmethod
    def _put_max(data: dict[str, float], key: str, value: float) -> None:
        data[key] = max(value, data.get(key, value))
