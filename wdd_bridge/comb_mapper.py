import cv2
import math
import numpy as np


class CombMapper:
    def __init__(self, config, azimuth_updater):

        self.actuators = []
        for conf in config["actuators"]:
            self.actuators.append((conf["x"], conf["y"]))

        self.pixel_coordinates = np.array(config["homography"]["pixels"]).reshape(4, 2)
        self.unit_coordinates = np.array(config["homography"]["units"]).reshape(4, 2)

        self.homography, _ = cv2.findHomography(
            self.pixel_coordinates, self.unit_coordinates
        )

        self.azimuth_updater = azimuth_updater

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

        xy = np.array([[x, y],[x + np.cos(waggle_angle), y + np.sin(waggle_angle)]]).reshape(2, 1, 2)
        xy = cv2.perspectiveTransform(
            xy, self.homography
        )

        # Rotate angle, accounting for homography.
        waggle_angle = xy[1] - xy[0]
        waggle_angle = np.arctan2(*list(waggle_angle.flatten()))
        world_angle = self.azimuth_updater.get_azimuth() + waggle_angle

        xy = xy.flatten()

        if not find_sensor:
            return xy, (waggle_angle, world_angle), None

        min_distance = np.inf
        sensor_index = None
        for idx, (ax, ay) in enumerate(self.actuators):
            distance = math.sqrt((ax - x) ** 2.0 + (ay - y) ** 2.0)
            if distance < min_distance:
                min_distance = distance
                sensor_index = idx

        return xy, (waggle_angle, world_angle), (sensor_index, min_distance)
