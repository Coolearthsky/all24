""" The LSM6DSOX gyro.

The deployment mode for this hardware would be
using the I2C of one or more Raspberry Pi's,
and doing the integration there.

the uncorrected drift of this sensor is high,
so there will need to be a "calibration" process
of some kind, e.g. notice when the robot is not
moving, and measure the offset, or do it once
at startup, or something.

TODO: watch the accelerometers;
spikes in acceleration can decalibrate the gyro.


windows installation
python3 -m pip install hidapi
python3 -m pip install adafruit-blinka
python3 -m pip install adafruit-circuitpython-lsm6ds
 """

#pylint: disable=E1101

import board  # type:ignore
from adafruit_lsm6ds import Rate  # type:ignore
from adafruit_lsm6ds.lsm6dsox import LSM6DSOX  # type:ignore
from app.gyro import Gyro
from app.network import Network
from app.timer import Timer

# this is just experimentally measured.
# TODO: automatic calibration at startup
# TODO: or per-identity offset
_OFFSET = -0.014935  # for 100hz
# TODO: measure this
_SCALE = 1.0

# at 100hz output data rate, each sample represents
# the average signal over the previous 10 ms (with a bit
# of delay due to i2c, maybe 0.1 ms?) so treat it as
# a point estimate of 5 ms ago.
_DELAY_US = 5000


class RealGyro(Gyro):
    def __init__(self, network: Network) -> None:
        self.network = network
        i2c = board.I2C()
        self.imu = LSM6DSOX(i2c)
        # see adafruit_lsm6ds/__init__.py
        self.imu.gyro_data_rate = Rate.RATE_104_HZ
        self.yaw_rad = 0
        self.prev_time_ns = Timer.time_ns()
        self.prev_rate_rad_s = None

    def sample(self) -> None:
        """NWU counterclockwise-positive."""
        rate_rad_s = (self.imu.gyro[2] - _OFFSET) * _SCALE
        if self.prev_rate_rad_s is None:
            self.prev_rate_rad_s = rate_rad_s
        endtime_ns = Timer.time_ns()
        duration_ns = endtime_ns - self.prev_time_ns
        self.prev_time_ns = endtime_ns
        # use the midpoint rule Riemann sum
        # https://en.wikipedia.org/wiki/Riemann_sum#Midpoint_rule
        mid_rate_rad_s = 0.5 * (rate_rad_s + self.prev_rate_rad_s)
        d_yaw_rad = mid_rate_rad_s * duration_ns / 1e9
        self.yaw_rad += d_yaw_rad
        self.network.set_gyro_yaw(self.yaw_rad, _DELAY_US)
        self.network.set_gyro_rate(rate_rad_s, _DELAY_US)
