# pylint: disable=C0103,C0114,C0115,C0116,R0902,W0201

import dataclasses
import time
import pprint

from enum import Enum

import sys
import cv2
import libcamera
import numpy as np
import ntcore
import robotpy_apriltag

from cscore import CameraServer
from picamera2 import Picamera2
from wpimath.geometry import Transform3d
from wpiutil import wpistruct


@wpistruct.make_wpistruct
@dataclasses.dataclass
class Blip24:
    id: int
    pose: Transform3d


class Camera(Enum):
    """Keep this synchronized with java team100.config.Camera."""

    A = "10000000caeaae82"  # "BETA FRONT"
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


class CameraData:
    def __init__(self, id) -> None:
        self.camera = Picamera2(id)
        model = self.camera.camera_properties["Model"]
        print("\nMODEL " + model)
        self.id = id

        if model == "imx708_wide":
            print("V3 Wide Camera")
            # full frame is 4608x2592; this is 2x2
            fullwidth = 2304
            fullheight = 1296
            # medium detection resolution, compromise speed vs range
            self.width = 1152
            self.height = 648
        elif model == "imx219":
            print("V2 Camera")
            # full frame, 2x2, to set the detector mode to widest angle possible
            fullwidth = 1664  # slightly larger than the detector, to match stride
            fullheight = 1232
            # medium detection resolution, compromise speed vs range
            self.width = 832
            self.height = 616
        elif model == "imx296":
            print("GS Camera")
            # full frame, 2x2, to set the detector mode to widest angle possible
            fullwidth = 1408  # slightly larger than the detector, to match stride
            fullheight = 1088
            # medium detection resolution, compromise speed vs range
            self.width = 1408
            self.height = 1088
        else:
            print("UNKNOWN CAMERA: " + model)
            fullwidth = 100
            fullheight = 100
            self.width = 100
            self.height = 100

        camera_config = self.camera.create_still_configuration(
            # 2 buffers => low latency (32-48 ms), low fps (15-20)
            # 5 buffers => mid latency (40-55 ms), high fps (22-28)
            # 3 buffers => high latency (50-70 ms), mid fps (20-23)
            # robot goes at 50 fps, so roughly a frame every other loop
            # fps doesn't matter much, so minimize latency
            buffer_count=5,
            main={
                "format": "YUV420",
                "size": (fullwidth, fullheight),
            },
            lores={"format": "YUV420", "size": (self.width, self.height)},
            controls={
                # these manual controls are useful sometimes but turn them off for now
                # because auto mode seems fine
                # fast shutter means more gain
                # "AnalogueGain": 8.0,
                # try faster shutter to reduce blur.  with 3ms, 3 rad/s seems ok.
                # 3/23/24, reduced to 2ms, even less blur.
                "ExposureTime": 300,
                "AnalogueGain": 8,
                # "AeEnable": True,
                # limit auto: go as fast as possible but no slower than 30fps
                # without a duration limit, we slow down in the dark, which is fine
                # "FrameDurationLimits": (5000, 33333),  # 41 fps
                # noise reduction takes time, don't need it.
                "NoiseReductionMode": libcamera.controls.draft.NoiseReductionModeEnum.Off,
                # "ScalerCrop":(0,0,width/2,height/2),
            },
        )
        print("SENSOR MODES AVAILABLE")
        pprint.pprint(self.camera.sensor_modes)
        # if identity == Camera.FRONT:
        #     camera_config["transform"] = libcamera.Transform(hflip=1, vflip=1)

        print("\nREQUESTED CONFIG")
        print(camera_config)
        self.camera.align_configuration(camera_config)
        print("\nALIGNED CONFIG")
        print(camera_config)
        self.camera.configure(camera_config)
        print("\nCONTROLS")
        print(self.camera.camera_controls)
        if model == "imx708_wide":
            print("V3 WIDE CAMERA")
            fx = 498
            fy = 498
            cx = 584
            cy = 316
            k1 = 0.01
            k2 = -0.0365
        elif model == "imx219":
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
        tag_size = 0.1651
        p1 = 0
        p2 = 0
        self.mtx = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        self.dist = np.array([[k1, k2, p1, p2]])
        self.output_stream = CameraServer.putVideo(str(id), self.width, self.height)
        self.estimator = robotpy_apriltag.AprilTagPoseEstimator(
            robotpy_apriltag.AprilTagPoseEstimator.Config(
                tag_size,
                fx,
                fy,
                cx,
                cy,
            )
        )
        self.camera.start()
        self.frame_time = time.time()

    def setFPSPublisher(self, FPSPublisher: ntcore.DoublePublisher) -> None:
        self.FPSPublisher = FPSPublisher

    def setLatencyPublisher(self, LatencyPublisher: ntcore.DoublePublisher) -> None:
        self.LatencyPublisher = LatencyPublisher


class TagFinder:
    def __init__(self, serial: str, camList: list[CameraData]) -> None:
        # the cpu serial number
        self.serial = serial
        self.initialize_nt(camList)
        self.blips = []
        self.at_detector = robotpy_apriltag.AprilTagDetector()

        config = self.at_detector.Config()
        config.numThreads = 4
        self.at_detector.setConfig(config)
        self.at_detector.addFamily("tag36h11")

    def analyze(self, request, camera): list[CameraData] -> None:
        # potentialTags = self.estimatedTagPose.get()
        # potentialArray = []
        # z = []
        # for Blip24s in potentialTags:
        #     translation = Blip24s.pose.translation()
        #     if translation.Z() < 0:
        #         continue
        #     rvec = np.zeros((3, 1), np.float32)
        #     tvec = np.zeros((3, 1), np.float32)
        #     object_points = np.array(
        #         [translation.X(), translation.Y(), translation.Z()], np.float32
        #     )
        #     (point2D, _) = cv2.projectPoints(
        #         object_points, rvec, tvec, camera.mtx, camera.dist
        #     )
        #     if (
        #         point2D[0][0][0] > 0
        #         and point2D[0][0][0] < 1456
        #         and point2D[0][0][1] > 0
        #         and point2D[0][0][1] < 1088
        #     ):
        # print(Blip24s.id)
        # print(object_points)
        # print(point2D[0][0])
        # z.append(translation.Z())
        # potentialArray.append(point2D[0][0])
        buffer = request.make_buffer("lores")
        metadata = request.get_metadata()

        y_len = camera.width * camera.height

        # truncate, ignore chrominance. this makes a view, very fast (300 ns)
        img = np.frombuffer(buffer, dtype=np.uint8, count=y_len)

        # this  makes a view, very fast (150 ns)
        img = img.reshape((camera.height, camera.width))
        # TODO: crop regions that never have targets
        # this also makes a view, very fast (150 ns)
        # img = img[int(self.height / 4) : int(3 * self.height / 4), : self.width]
        # for now use the full frame
        # if len(potentialArray) == 1:
        #     offset = 100 / z[0]
        #     if (
        #         potentialArray[0][1] - offset > 0
        #         and potentialArray[0][0] - offset > 0
        #         and potentialArray[0][0] + offset < camera.width
        #         and potentialArray[0][1] + offset < camera.height
        #     ):
        #         img = img[
        #             int(potentialArray[0][1] - offset) : int(
        #                 potentialArray[0][1] + offset
        #             ),
        #             int(potentialArray[0][0] - offset) : int(
        #                 potentialArray[0][0] + offset
        #             ),
        #         ]

        img = cv2.undistort(img, camera.mtx, camera.dist)

        result = self.at_detector.detect(img)

        for result_item in result:
            if result_item.getHamming() > 0:
                continue
            pose = camera.estimator.estimate(result_item)
            self.blips.append(Blip24(result_item.getId(), pose))
            # TODO: turn this off for prod
            self.draw_result(img, result_item, pose)

        # compute time since last frame
        current_time = time.time()
        total_et = current_time - camera.frame_time
        camera.frame_time = current_time

        fps = 1 / total_et

        camera.fps = fps
        camera.FPSPublisher.set(fps)

        # sensor timestamp is the boottime when the first byte was received from the sensor
        sensor_timestamp = metadata["SensorTimestamp"]
        # include all the work above in the latency
        system_time_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        time_delta_ms = (system_time_ns - sensor_timestamp) // 1000000
        camera.LatencyPublisher.set(time_delta_ms)

        # must flush!  otherwise 100ms update rate.
        self.inst.flush()

        # now do the drawing (after the NT payload is written)
        # none of this is particularly fast or important for prod,
        # TODO: consider disabling it after dev is done
        self.draw_text(img, f"fps {fps:.1f}", (5, 65))
        # self.draw_text(img, f"latency(ms) {time_delta_ms:.0f}", (5, 105))

        # shrink the driver view to avoid overloading the radio
        # TODO: turn this back on for prod!!
        # driver_img = cv2.resize(img, (self.view_width, self.view_height))
        # self.output_stream.putFrame(driver_img)

        # for now put big images
        # TODO: turn this off for prod!!
        img_output = cv2.resize(img, (416, 308))
        camera.output_stream.putFrame(img_output)

    def draw_result(self, image, result_item, pose: Transform3d) -> None:
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
    def draw_text(self, image, msg: str, loc) -> None:
        cv2.putText(image, msg, loc, cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 6)
        cv2.putText(image, msg, loc, cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)

    def accept(self, estimatedTagPose):
        print("ay" + str(estimatedTagPose.readQueue()))

    def initialize_nt(self, camList: list[CameraData]) -> None:
        """Start NetworkTables with Rio as server, set up publisher."""
        self.inst = ntcore.NetworkTableInstance.getDefault()
        self.inst.startClient4("tag_finder24")
        # roboRio address. windows machines can impersonate this for simulation.
        self.inst.setServer("10.1.0.2")

        topic_name = "vision/" + self.serial
        for camera in camList:
            camera.setFPSPublisher(
                self.inst.getDoubleTopic(
                    topic_name + "/" + str(camera.id) + "/fps"
                ).publish()
            )
            camera.setLatencyPublisher(
                self.inst.getDoubleTopic(
                    topic_name + "/" + str(camera.id) + "/latency"
                ).publish()
            )

        # work around https://github.com/robotpy/mostrobotpy/issues/60
        self.inst.getStructTopic("bugfix", Blip24).publish().set(
            Blip24(0, Transform3d())
        )
        # blip array topic
        self.vision_nt_struct = self.inst.getStructArrayTopic(
            topic_name + "/blips", Blip24
        ).publish()

        self.estimatedTagPose = self.inst.getStructArrayTopic(
            topic_name + "/estimatedTagPose", Blip24
        ).subscribe([], ntcore.PubSubOptions())


def getserial():
    with open("/proc/cpuinfo", "r", encoding="ascii") as cpuinfo:
        for line in cpuinfo:
            if line[0:6] == "Serial":
                return line[10:26]
    return ""


def main() -> None:
    print("main")
    print(Picamera2.global_camera_info())
    camList: list[CameraData] = []
    if len(Picamera2.global_camera_info()) == 0:
        print("NO CAMERAS DETECTED, PLEASE TURN OFF PI AND CHECK CAMERA PORT(S)")
    for cameraData in Picamera2.global_camera_info():
        camera = CameraData(cameraData["Num"])
        camList.append(camera)
    serial: str = getserial()
    print(serial)
    output = TagFinder(serial, camList)
    # output.startListening()
    try:
        while True:
            for camera in camList:
                request = camera.camera.capture_request()
                try:
                    output.analyze(request, camera)
                finally:
                    request.release()
            output.vision_nt_struct.set(output.blips)
            output.blips = []
    finally:
        for camera in camList:
            camera.camera.stop()


main()
