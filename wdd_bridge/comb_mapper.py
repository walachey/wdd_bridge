import cv2
import json
import math
import numpy as np


class CombMapper:
    def __init__(self, config_path):

        with open(config_path, "r") as f:
            config = json.load(f)

        self.actuators = []
        for conf in config["actuators"]:
            self.actuators.append((conf["x"], conf["y"]))

        self.pixel_coordinates = np.array(config["homography"]["pixels"]).reshape(4, 2)
        self.unit_coordinates = np.array(config["homography"]["units"]).reshape(4, 2)

        self.homography, _ = cv2.findHomography(
            self.pixel_coordinates, self.unit_coordinates
        )

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

    def map_to_comb(self, x, y, find_sensor=True):

        xy = cv2.perspectiveTransform(
            np.array([x, y]).reshape(1, 1, 2), self.homography
        )
        xy = xy.flatten()

        if not find_sensor:
            return xy, None

        min_distance = np.inf
        sensor_index = None
        for idx, (ax, ay) in enumerate(self.actuators):
            distance = math.sqrt((ax - x) ** 2.0 + (ay - y) ** 2.0)
            if distance < min_distance:
                min_distance = distance
                sensor_index = idx

        return xy, (sensor_index, min_distance)
