"""Evaluate the estimation model for gyro measurements."""

# pylint: disable=C0301,E0611,E1101,R0903

import unittest

import gtsam
import numpy as np
from gtsam import noiseModel  # type:ignore
from gtsam.symbol_shorthand import X  # type:ignore

from app.pose_estimator.estimate import Estimate

PRIOR_NOISE = noiseModel.Diagonal.Sigmas(np.array([0.3, 0.3, 0.1]))


class EstimateGyroTest(unittest.TestCase):
    def test_gyro_0(self) -> None:
        """motionless"""
        est = Estimate()
        est.init()

        prior_mean = gtsam.Pose2(0, 0, 0)
        est.add_state(0, prior_mean)
        est.prior(0, prior_mean, PRIOR_NOISE)

        est.gyro(0, 0)
        est.update()
        print(est.result)
        self.assertEqual(1, est.result.size())
        p0: gtsam.Pose2 = est.result.atPose2(X(0))
        self.assertAlmostEqual(0, p0.x(), 3)
        self.assertAlmostEqual(0, p0.y(),3 )
        self.assertAlmostEqual(0, p0.theta(), 5)


    def test_gyro_1(self) -> None:
        """rotating"""
        est = Estimate()
        est.init()

        prior_mean = gtsam.Pose2(0, 0, 0)
        est.add_state(0, prior_mean)
        est.prior(0, prior_mean, PRIOR_NOISE)

        est.gyro(0, 1)
        est.update()
        print(est.result)
        self.assertEqual(1, est.result.size())
        p0: gtsam.Pose2 = est.result.atPose2(X(0))
        self.assertAlmostEqual(0, p0.x(), 3)
        self.assertAlmostEqual(0, p0.y(), 3)
        self.assertAlmostEqual(1, p0.theta(), 5)

