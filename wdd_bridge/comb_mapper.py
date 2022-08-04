import cv2
import math
import numpy as np


class CombMapper:
    def __init__(self, config, azimuth_updater, print_fn):
        
        self.print_fn = print_fn
        self.actuators = []
        for conf in config["actuators"]:
            actuator_index = int(conf["name"][-1])
            self.actuators.append((actuator_index, (conf["x"], conf["y"])))
        self.actuators = [xy for (_, xy) in sorted(self.actuators)]
        
        self.pixel_coordinates = np.array(config["homography"]["pixels"]).reshape(4, 2)
        self.unit_coordinates = np.array(config["homography"]["units"]).reshape(4, 2)

        origin = config["origin"]
        if "top" in origin:
            self.origin_y = "top"
        else:
            assert "bottom" in origin
            self.origin_y = "bottom"
        
        if "left" in origin:
            self.origin_x = "left"
        else:
            assert "right" in origin
            self.origin_x = "right"

        self.homography, _ = cv2.findHomography(
            self.pixel_coordinates, self.unit_coordinates
        )

        self.azimuth_updater = azimuth_updater

    def get_origin(self):
        return self.origin_x, self.origin_y

    def get_actuator_count(self):
        return len(self.actuators)

    def get_comb_rectangle(self):
        return (
            self.unit_coordinates[:, 0].min(),
            self.unit_coordinates[:, 1].min(),
            self.unit_coordinates[:, 0].max(),
            self.unit_coordinates[:, 1].max(),
        )

    def get_sensor_coordinates(self):
        return self.actuators

    def map_to_comb(self, x, y, waggle_angle, find_sensor=True):
        
        waggle_offset_x = np.cos(waggle_angle)
        waggle_offset_y = np.sin(waggle_angle)
        if self.origin_y == "bottom":
            waggle_offset_y *= -1
        if self.origin_x == "right":
            waggle_offset_x *= -1
        # Note that it's -sin because the angle is currently in image coordinates (origin: top left).
        xy = np.array([[x, y],[x + waggle_offset_x, y + waggle_offset_y ]]).reshape(2, 1, 2)
        xy = cv2.perspectiveTransform(
            xy, self.homography
        )
        
        # Rotate angle, accounting for homography.
        waggle_angle = xy[1] - xy[0]
        wx, wy = list(waggle_angle.flatten())
        waggle_angle = np.arctan2(wy, wx)
        # To gravity-angle. (0 top, counter-clockwise).
        waggle_angle -= np.pi / 2.0

        waggle_angle = waggle_angle % (2.0 * np.pi)
        world_angle = (self.azimuth_updater.get_azimuth() + waggle_angle) % (2.0 * np.pi)

        xy = xy[:1].flatten()

        if not find_sensor:
            return xy, (waggle_angle, world_angle), None

        x, y = xy
        min_distance = np.inf
        sensor_index = None
        for idx, (ax, ay) in enumerate(self.actuators):
            distance = math.sqrt((ax - x) ** 2.0 + (ay - y) ** 2.0)
            if distance < min_distance:
                min_distance = distance
                sensor_index = idx

        return xy, (waggle_angle, world_angle), (sensor_index, min_distance)
