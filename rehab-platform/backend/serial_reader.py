"""Thread-based serial reader for the Arduino sensor node."""

import argparse
import logging
import os
import serial
import threading
import time
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SensorReading:
    angle_sensor: float
    pressure: float
    arduino_ts: int
    pc_ts: float
    bend_percent: float
    pressure_percent: float
    pir: int


class SerialReader:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self.bend_sensitivity = float(os.getenv("BEND_SENSITIVITY", "2.4"))
        self.pressure_sensitivity = float(os.getenv("PRESSURE_SENSITIVITY", "1.6"))
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest: SensorReading | None = None
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=1)
        except serial.SerialException as exc:
            logger.error("Serial port unavailable on %s: %s", self.port, exc)
            self._set_connected(False)
            self._serial = None
            return

        self._set_connected(True)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        serial_port = self._serial
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._close_serial()
        self._set_connected(False)

    def get_latest(self) -> SensorReading | None:
        with self._lock:
            return self._latest

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            serial_port = self._serial
            if serial_port is None:
                self._set_connected(False)
                return

            try:
                raw_line = serial_port.readline()
            except serial.SerialException as exc:
                logger.error("Serial read failed on %s: %s", self.port, exc)
                self._set_connected(False)
                return

            if not raw_line:
                continue

            line = raw_line.decode("utf-8", errors="replace").strip()
            reading = self._parse_line(line)
            if reading is None:
                continue

            with self._lock:
                self._latest = reading

        self._set_connected(False)

    def _parse_line(self, line: str) -> SensorReading | None:
        parts = line.split(",")
        if len(parts) != 3:
            logger.warning("Skipping malformed serial line: %r", line)
            return None

        try:
            bend_percent = float(parts[0])
            pressure_percent = float(parts[1])
            pir = int(parts[2])
        except ValueError:
            logger.warning("Skipping malformed serial line: %r", line)
            return None

        bend_percent = max(0.0, min(100.0, bend_percent))
        pressure_percent = max(0.0, min(100.0, pressure_percent))
        pc_ts = time.time()

        angle_sensor = (bend_percent / 100.0) * 90.0 * self.bend_sensitivity

        pressure = (pressure_percent / 100.0) * 10.0 * self.pressure_sensitivity

        return SensorReading(
            angle_sensor=max(0.0, min(90.0, angle_sensor)),
            pressure=max(0.0, min(10.0, pressure)),
            arduino_ts=int(pc_ts * 1000),
            pc_ts=pc_ts,
            bend_percent=bend_percent,
            pressure_percent=pressure_percent,
            pir=pir,
        )

    def _set_connected(self, connected: bool) -> None:
        with self._lock:
            self._is_connected = connected

    def _close_serial(self) -> None:
        serial_port = self._serial
        self._serial = None

        if serial_port is None:
            return

        try:
            if serial_port.is_open:
                serial_port.close()
        except serial.SerialException as exc:
            logger.warning("Failed to close serial port: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read live Arduino sensor data.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM3")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    reader = SerialReader(port=args.port, baud=args.baud)
    reader.start()

    if not reader.is_connected:
        raise SystemExit(1)

    last_seen: SensorReading | None = None

    try:
        while reader.is_connected:
            reading = reader.get_latest()
            if reading is not None and reading != last_seen:
                print(reading)
                last_seen = reading
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
