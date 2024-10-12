""" This is a wrapper for the AprilTag detector. """

# pylint: disable=no-name-in-module, protected-access

from mmap import mmap
from typing import Any

import numpy as np
from numpy.typing import NDArray

import ntcore

from cv2 import undistortImagePoints
from robotpy_apriltag import AprilTagDetection, AprilTagDetector, AprilTagPoseEstimator
from app.camera import Camera, Request
from app.display import Display
from app.config.identity import Identity
from app.network import Blip24, Network
from app.timer import Timer

Mat = NDArray[np.uint8]


class TagDetector:
    def __init__(
        self,
        identity: Identity,
        width: int,
        height: int,
        cam: Camera,
        display: Display,
        network: Network,
    ) -> None:
        self.identity: Identity = identity
        self.width: int = width
        self.height: int = height
        self.display: Display = display
        self.network: Network = network

        self.y_len = self.width * self.height

        self.frame_time = Timer.time_ns()

        self.at_detector: AprilTagDetector = AprilTagDetector()

        config = self.at_detector.Config()
        config.numThreads = 4
        self.at_detector.setConfig(config)
        self.at_detector.addFamily("tag36h11")

        tag_size = 0.1651  # tagsize 6.5 inches

        self.mtx: Mat = cam.get_intrinsic()
        self.dist: Mat = cam.get_dist()

        self.estimator = AprilTagPoseEstimator(
            AprilTagPoseEstimator.Config(
                tag_size,
                self.mtx[0, 0],
                self.mtx[1, 1],
                self.mtx[0, 2],
                self.mtx[1, 2],
            )
        )

    def analyze(self, req: Request) -> None:
        metadata: dict[str, Any] = req.metadata()
        with req.buffer() as buffer:
            self.analyze2(metadata, buffer)

    def analyze2(self, metadata: dict[str, Any], buffer: mmap) -> None:
        # how old is the frame when we receive it?
        received_time: int = Timer.time_ns()
        # truncate, ignore chrominance. this makes a view, very fast (300 ns)
        img: Mat = np.frombuffer(buffer, dtype=np.uint8, count=self.y_len)

        # this  makes a view, very fast (150 ns)
        img = img.reshape((self.height, self.width))

        # TODO: crop regions that never have targets
        # this also makes a view, very fast (150 ns)
        # img = img[int(self.height / 4) : int(3 * self.height / 4), : self.width]
        # for now use the full frame
        # TODO: probably remove this
        if self.identity == Identity.SHOOTER:
            img = img[62:554, : self.width]
        else:
            img = img[: self.height, : self.width]

        undistort_time: int = Timer.time_ns()
        result: list[AprilTagDetection] = self.at_detector.detect(img.data)
        detect_time: int = Timer.time_ns()

        blips = []
        result_item: AprilTagDetection
        for result_item in result:
            if result_item.getHamming() > 0:
                continue

            # UNDISTORT EACH ITEM
            # undistortPoints is at least 10X faster than undistort on the whole image.
            corners: tuple[float, float, float, float, float, float, float, float] = (
                result_item.getCorners((0, 0, 0, 0, 0, 0, 0, 0))
            )
            # undistortPoints wants [[x0,y0],[x1,y1],...]
            pairs = np.reshape(corners, [4, 2])
            pairs = undistortImagePoints(pairs, self.mtx, self.dist)
            # the estimator wants [x0, y0, x1, y1, ...]
            # corners = np.reshape(pairs, [8])
            # pairs has an extra dimension
            corners = (
                pairs[0][0][0],
                pairs[0][0][1],
                pairs[1][0][0],
                pairs[1][0][1],
                pairs[2][0][0],
                pairs[2][0][1],
                pairs[3][0][0],
                pairs[3][0][1],
            )

            homography = result_item.getHomography()
            pose = self.estimator.estimate(homography, corners)

            blips.append(Blip24(result_item.getId(), pose))
            # TODO: turn this off for prod
            self.display.draw_result(img, result_item, pose)

        estimate_time = Timer.time_ns()

        # compute time since last frame
        current_time = Timer.time_ns()
        total_time_ms = (current_time - self.frame_time) // 1000000
        # total_et = current_time - self.frame_time
        self.frame_time = current_time

        # first row
        sensor_timestamp_ns = metadata["SensorTimestamp"]
        # how long for all the rows
        frame_duration_ns = metadata["FrameDuration"] * 1000
        # time of the middle row in the sensor
        # note this assumes a continuously rolling shutter
        # and will be completely wrong for a global shutter
        # TODO: global shutter case
        sensor_midpoint_ns = sensor_timestamp_ns + frame_duration_ns / 2
        image_age_ms = (received_time - sensor_timestamp_ns) // 1000000
        undistort_time_ms = (undistort_time - received_time) // 1000000
        detect_time_ms = (detect_time - undistort_time) // 1000000
        estimate_time_ms = (estimate_time - detect_time) // 1000000
        # oldest_pixel_ms = (system_time_ns - (sensor_timestamp - 1000 * metadata["ExposureTime"])) // 1000000
        # sensor timestamp is the boottime when the first byte was received from the sensor

        delay_ns: int = Timer.time_ns() - sensor_midpoint_ns
        delay_us = delay_ns // 1000

        self.network.vision_nt_struct.set(blips)
        self.network.vision_capture_time_ms.set(ntcore._now() - delay_us)
        self.network.vision_total_time_ms.set(total_time_ms)
        self.network.vision_image_age_ms.set(image_age_ms)
        self.network.vision_detect_time_ms.set(detect_time_ms)

        # must flush!  otherwise 100ms update rate.
        self.network.flush()

        # now do the drawing (after the NT payload is written)
        # none of this is particularly fast or important for prod,

        # self.draw_text(img, f"fps {fps:.1f}", (5, 65))
        self.display.draw_text(img, f"total (ms) {total_time_ms:.0f}", (5, 65))
        self.display.draw_text(img, f"age (ms) {image_age_ms:.0f}", (5, 105))
        self.display.draw_text(img, f"undistort (ms) {undistort_time_ms:.0f}", (5, 145))
        self.display.draw_text(img, f"detect (ms) {detect_time_ms:.0f}", (5, 185))
        self.display.draw_text(img, f"estimate (ms) {estimate_time_ms:.0f}", (5, 225))

        self.display.put_frame(img)
