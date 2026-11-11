"""Optional serial abstraction for a future motor controller; no Arduino required."""
class SerialMotorLink:
    def __init__(self, port=None, baudrate=115200):
        self.connection = None
        if port:
            try:
                import serial
            except ImportError as exc:
                raise RuntimeError("Install pyserial to use a serial motor controller") from exc
            self.connection = serial.Serial(port, baudrate=baudrate, timeout=0.1)

    def send_velocity(self, linear_m_s, angular_rad_s):
        if self.connection is None:
            raise RuntimeError("No serial port configured; simulation/inference can run without hardware")
        self.connection.write(f"V,{linear_m_s:.3f},{angular_rad_s:.3f}\n".encode("ascii"))

    def close(self):
        if self.connection is not None:
            self.connection.close()
