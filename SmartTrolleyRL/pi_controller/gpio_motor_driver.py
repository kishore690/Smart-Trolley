"""Raspberry Pi BCM GPIO to two L298N channels; each channel is one trolley side."""
from gpiozero import Button, DigitalOutputDevice, PWMOutputDevice


class L298Channel:
    """One H-bridge with direction pins plus an enable/PWM pin."""
    def __init__(self, forward_pin, backward_pin, enable_pin):
        self.forward = DigitalOutputDevice(forward_pin, initial_value=False)
        self.backward = DigitalOutputDevice(backward_pin, initial_value=False)
        self.enable = PWMOutputDevice(enable_pin, frequency=1000, initial_value=0.0)

    def set(self, speed):
        speed=max(-1.0,min(1.0,float(speed)))
        self.enable.value=abs(speed)
        self.forward.value=speed > 0
        self.backward.value=speed < 0

    def stop(self):
        self.enable.value=0.0
        self.forward.off(); self.backward.off()

    def close(self):
        self.stop(); self.forward.close(); self.backward.close(); self.enable.close()


class GPIOMotorDriver:
    def __init__(self, left_forward=17, left_backward=27, left_enable=18,
                 right_forward=22, right_backward=23, right_enable=19,
                 emergency_stop_pin=24):
        self.left = L298Channel(left_forward, left_backward, left_enable)
        self.right = L298Channel(right_forward, right_backward, right_enable)
        # Use a normally-closed E-stop loop from BCM GPIO24 (physical pin 18) to GND.
        # Opening the loop (pressed button or broken wire) reads as stop.
        self.emergency_stop = Button(emergency_stop_pin, pull_up=True,
                                     active_state=True, bounce_time=0.05)
        self._estop_latched = False
        self.stop()

    @staticmethod
    def _set(motor, speed):
        speed=max(-1.0,min(1.0,float(speed)))
        motor.set(speed)

    def drive(self, left_speed, right_speed):
        self._set(self.left,left_speed); self._set(self.right,right_speed)

    def stop(self):
        self.left.stop(); self.right.stop()

    def estop_pressed(self):
        self._estop_latched = self._estop_latched or self.emergency_stop.is_pressed
        return self._estop_latched

    def close(self):
        self.stop(); self.left.close(); self.right.close(); self.emergency_stop.close()
