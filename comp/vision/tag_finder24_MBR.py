# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=import-error
# pylint: disable=no-member
# type: ignore

import dataclasses
import pprint
import sys
import time
from enum import Enum

import cv2
import libcamera
import ntcore
import numpy as np
import robotpy_apriltag
from cscore import CameraServer
from picamera2 import Picamera2
from picamera2.request import _MappedBuffer
from wpimath.geometry import Transform3d
from wpiutil import wpistruct


@wpistruct.make_wpistruct
@dataclasses.dataclass
class Blip24:
    id: int
    pose: Transform3d


class Camera(Enum):
    """Keep this synchronized with java team100.config.Camera."""

    # TODO get correct serial numbers for Delta
    A = "10000000caeaae82"  # "BETA FRONT"
    # B = "1000000013c9c96c"  # "BETA BACK"
    C = "10000000a7c673d9"  # "GAMMA INTAKE"

    SHOOTER = "10000000a7a892c0"  # "DELTA SHOOTER"
    RIGHTAMP = "10000000caeaae82"  # "DELTA AMP-PLACER"
    LEFTAMP = "100000004e0a1fb9"  # "DELTA AMP-PLACER"
    GAME_PIECE = "1000000013c9c96c"  # "DELTA INTAKE"

    G = "10000000a7a892c0"  # ""
    UNKNOWN = None

    @classmethod
    def _missing_(cls, value):
        return Camera.UNKNOWN


class TagFinder:
    def __init__(self, serial, width, height, model):
        self.frame_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        # the cpu serial number
        self.serial = serial
        self.width = width
        self.height = height
        self.model = model

        # for the driver view
        scale = 0.25
        self.view_width = int(width * scale)
        self.view_height = int(height * scale)

        self.initialize_nt()

        self.at_detector = robotpy_apriltag.AprilTagDetector()
        config = self.at_detector.Config()
        config.numThreads = 4
        self.at_detector.setConfig(config)
        self.at_detector.addFamily("tag36h11")

        # from testing on 3/22/24, k1 and k2 only

        if self.model == "imx708_wide":
            print("V3 WIDE CAMERA")
            fx = 498
            fy = 498
            cx = 584
            cy = 316
            k1 = 0.01
            k2 = -0.0365
        elif self.model == "imx219":
            print("V2 CAMERA (NOT WIDE ANGLE)")
            fx = 660
            fy = 660
            cx = 426
            cy = 303
            k1 = -0.003
            k2 = 0.04
        # TODO get these real distortion values
        elif model == "imx296":
            fx = 1680
            fy = 1680
            cx = 728
            cy = 544
            k1 = 0
            k2 = 0
        else:
            print("UNKNOWN CAMERA MODEL")
            sys.exit()

        tag_size = 0.1651  # tagsize 6.5 inches
        p1 = 0
        p2 = 0

        self.mtx = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        self.dist = np.array([[k1, k2, p1, p2]])
        self.estimator = robotpy_apriltag.AprilTagPoseEstimator(
            robotpy_apriltag.AprilTagPoseEstimator.Config(
                tag_size,
                fx,
                fy,
                cx,
                cy,
            )
        )

        self.output_stream = CameraServer.putVideo("Processed", width, height)

    def analyze(self, metadata, buffer):
        # how old is the frame when we receive it?
        received_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

        y_len = self.width * self.height

        # truncate, ignore chrominance. this makes a view, very fast (300 ns)
        img = np.frombuffer(buffer, dtype=np.uint8, count=y_len)

        # this  makes a view, very fast (150 ns)
        img = img.reshape((self.height, self.width))
        # TODO: crop regions that never have targets
        # this also makes a view, very fast (150 ns)
        # img = img[int(self.height / 4) : int(3 * self.height / 4), : self.width]
        # for now use the full frame
        # TODO: probably remove this
        serial = getserial()
        identity = Camera(serial)
        if identity == Camera.SHOOTER:
            img = img[62:554, : self.width]
        else:
            img = img[: self.height, : self.width]

        undistort_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

        result = self.at_detector.detect(img.data)

        detect_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

        blips = []
        for result_item in result:
            if result_item.getHamming() > 0:
                continue

            # UNDISTORT EACH ITEM
            # undistortPoints is at least 10X faster than undistort on the whole image.
            corners = result_item.getCorners(np.zeros(8))
            # undistortPoints wants [[x0,y0],[x1,y1],...]
            pairs = np.reshape(corners, [4, 2])
            pairs = cv2.undistortImagePoints(pairs, self.mtx, self.dist)
            # the estimator wants [x0, y0, x1, y1, ...]
            corners = np.reshape(pairs, [8])

            homography = result_item.getHomography()
            pose = self.estimator.estimate(homography, corners)

            blips.append(Blip24(result_item.getId(), pose))
            # TODO: turn this off for prod
            self.draw_result(img, result_item, pose)

        estimate_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

        # compute time since last frame
        current_time = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        total_time_ms = (current_time - self.frame_time) // 1000000
        # total_et = current_time - self.frame_time
        self.frame_time = current_time

        sensor_timestamp = metadata["SensorTimestamp"]
        image_age_ms = (received_time - sensor_timestamp) // 1000000
        undistort_time_ms = (undistort_time - received_time) // 1000000
        detect_time_ms = (detect_time - undistort_time) // 1000000
        estimate_time_ms = (estimate_time - detect_time) // 1000000
        # oldest_pixel_ms = (system_time_ns - (sensor_timestamp - 1000 * metadata["ExposureTime"])) // 1000000
        # sensor timestamp is the boottime when the first byte was received from the sensor

        self.vision_nt_struct.set(blips)
        self.vision_total_time_ms.set(total_time_ms)
        self.vision_image_age_ms.set(image_age_ms)
        self.vision_detect_time_ms.set(detect_time_ms)

        # must flush!  otherwise 100ms update rate.
        self.inst.flush()

        # now do the drawing (after the NT payload is written)
        # none of this is particularly fast or important for prod,

        # self.draw_text(img, f"fps {fps:.1f}", (5, 65))
        self.draw_text(img, f"total (ms) {total_time_ms:.0f}", (5, 65))
        self.draw_text(img, f"age (ms) {image_age_ms:.0f}", (5, 105))
        self.draw_text(img, f"undistort (ms) {undistort_time_ms:.0f}", (5, 145))
        self.draw_text(img, f"detect (ms) {detect_time_ms:.0f}", (5, 185))
        self.draw_text(img, f"estimate (ms) {estimate_time_ms:.0f}", (5, 225))

        # shrink the driver view to avoid overloading the radio
        # TODO: turn this back on for prod!!
        # driver_img = cv2.resize(img, (self.view_width, self.view_height))
        # self.output_stream.putFrame(driver_img)

        # for now put big images
        # TODO: turn this off for prod!!
        img_output = cv2.resize(img, (416, 308))
        self.output_stream.putFrame(img_output)

    def draw_result(self, image, result_item, pose: Transform3d):
        color = (255, 255, 255)

        # Draw lines around the tag
        for i in range(4):
            j = (i + 1) % 4
            point1 = (int(result_item.getCorner(i).x), int(result_item.getCorner(i).y))
            point2 = (int(result_item.getCorner(j).x), int(result_item.getCorner(j).y))
            cv2.line(image, point1, point2, color, 2)

        (c_x, c_y) = (int(result_item.getCenter().x), int(result_item.getCenter().y))
        cv2.circle(image, (c_x, c_y), 10, (255, 255, 255), -1)

        tag_id = result_item.getId()
        self.draw_text(image, f"id {tag_id}", (c_x, c_y))

        # type the translation into the image, in WPI coords (x-forward)
        if pose is not None:
            t = pose.translation()
            self.draw_text(
                image,
                f"t: {t.z:4.1f},{-t.x:4.1f},{-t.y:4.1f}",
                (c_x - 50, c_y + 40),
            )

    # these are white with black outline
    def draw_text(self, image, msg, loc):
        cv2.putText(image, msg, loc, cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 6)
        cv2.putText(image, msg, loc, cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)

    def log_capture_time(self, ms):
        self.vision_capture_time_ms.set(ms)

    def initialize_nt(self):
        """Start NetworkTables with Rio as server, set up publisher."""
        self.inst = ntcore.NetworkTableInstance.getDefault()
        self.inst.startClient4("tag_finder24")

        # roboRio address. windows machines can impersonate this for simulation.
        self.inst.setServer("10.1.0.2")

        topic_name = "vision/" + self.serial
        self.vision_capture_time_ms = self.inst.getDoubleTopic(
            topic_name + "/capture_time_ms"
        ).publish()
        self.vision_image_age_ms = self.inst.getDoubleTopic(
            topic_name + "/image_age_ms"
        ).publish()
        self.vision_total_time_ms = self.inst.getDoubleTopic(
            topic_name + "/total_time_ms"
        ).publish()
        self.vision_detect_time_ms = self.inst.getDoubleTopic(
            topic_name + "/detect_time_ms"
        ).publish()

        # work around https://github.com/robotpy/mostrobotpy/issues/60
        self.inst.getStructTopic("bugfix", Blip24).publish().set(
            Blip24(0, Transform3d())
        )

        # blip array topic
        self.vision_nt_struct = self.inst.getStructArrayTopic(
            topic_name + "/blips", Blip24
        ).publish()


def getserial():
    with open("/proc/cpuinfo", "r", encoding="ascii") as cpuinfo:
        for line in cpuinfo:
            if line[0:6] == "Serial":
                return line[10:26]
    return ""


def main():

    camera = Picamera2()

    model = camera.camera_properties["Model"]
    print("\nMODEL " + model)

    if model == "imx708_wide":
        print("V3 Wide Camera")
        # full frame is 4608x2592; this is 2x2
        fullwidth = 2304
        fullheight = 1296
        # medium detection resolution, compromise speed vs range
        width = 1152
        height = 648
    elif model == "imx219":
        print("V2 Camera")
        # full frame, 2x2, to set the detector mode to widest angle possible
        fullwidth = 1664  # slightly larger than the detector, to match stride
        fullheight = 1232
        # medium detection resolution, compromise speed vs range
        width = 832
        height = 616
    elif model == "imx296":
        print("GS Camera")
        # full frame, 2x2, to set the detector mode to widest angle possible
        fullwidth = 1472  # slightly larger than the detector, to match stride
        fullheight = 1088
        # medium detection resolution, compromise speed vs range
        width = 1472
        height = 1088
    else:
        print("UNKNOWN CAMERA: " + model)
        fullwidth = 100
        fullheight = 100
        width = 100
        height = 100

    camera_config = camera.create_still_configuration(
        # more buffers seem to make the pipeline a little smoother
        buffer_count=5,
        # hang on to one camera buffer (zero copy) and leave one
        # other for the camera to fill.
        queue=True,
        main={
            "format": "YUV420",
            "size": (fullwidth, fullheight),
        },
        lores={"format": "YUV420", "size": (width, height)},
        controls={
            # these manual controls are useful sometimes but turn them off for now
            # because auto mode seems fine
            # fast shutter means more gain
            # "AnalogueGain": 8.0,
            # try faster shutter to reduce blur.  with 3ms, 3 rad/s seems ok.
            # 3/23/24, reduced to 2ms, even less blur.
            "ExposureTime": 3000,
            "AnalogueGain": 8,
            # limit auto: go as fast as possible but no slower than 30fps
            # without a duration limit, we slow down in the dark, which is fine
            # "FrameDurationLimits": (5000, 33333),  # 41 fps
            # noise reduction takes time, don't need it.
            # "NoiseReductionMode": libcamera.controls.draft.NoiseReductionModeEnum.Off,
            "NoiseReductionMode": 0,
            # "ScalerCrop":(0,0,width/2,height/2),
        },
    )
    print("SENSOR MODES AVAILABLE")
    pprint.pprint(camera.sensor_modes)
    serial = getserial()
    identity = Camera(serial)
    # if identity == Camera.FRONT:
    #     camera_config["transform"] = libcamera.Transform(hflip=1, vflip=1)

    print("\nREQUESTED CONFIG")
    print(camera_config)
    camera.align_configuration(camera_config)
    print("\nALIGNED CONFIG")
    print(camera_config)
    camera.configure(camera_config)
    print("\nCONTROLS")
    print(camera.camera_controls)
    print(serial)
    output = TagFinder(serial, width, height, model)

    camera.start()
    try:
        while True:
            # the most recent completed frame, from the recent past
            capture_start = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            request = camera.capture_request()
            capture_end = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            # capture time is how long we wait for the camera
            capture_time_ms = (capture_end - capture_start) // 1000000
            output.log_capture_time(capture_time_ms)
            try:
                metadata = request.get_metadata()
                # avoid copying the buffer
                with _MappedBuffer(request, "lores") as buffer:
                    output.analyze(metadata, buffer)
            finally:
                # the frame is owned by the camera so remember to release it
                request.release()
    finally:
        camera.stop()


main()
