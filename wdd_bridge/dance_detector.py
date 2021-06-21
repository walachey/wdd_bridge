import math


class Waggle:
    def __init__(self, x, y, angle, timestamp):
        self.x = x
        self.y = y
        self.angle = angle
        self.timestamp = timestamp


class Dance:
    def __init__(self):

        self.coords = []
        self.angles = []
        self.timestamps = []
        self.triggered = 0

    def get_last_timestamp(self):
        return self.timestamps[-1]

    def get_min_distance(self, x, y):

        min_distance = 1e1000
        for (cx, cy) in self.coords:
            distance = math.sqrt((cx - x) ** 2.0 + (cy - y) ** 2.0)

            min_distance = min(distance, min_distance)

        return min_distance

    def append(self, waggle):
        self.coords.append((waggle.x, waggle.y))
        self.angles.append(waggle.angle)
        self.timestamps.append(waggle.timestamp)

    def trigger(self):
        self.triggered += 1

    def __len__(self):
        return len(self.timestamps)


class DanceDetector:
    def __init__(self, min_distance=200.0, min_delay=5.0, min_waggles=3, print_fn=None):

        self.min_distance = min_distance
        self.min_delay = min_delay
        self.min_waggles = min_waggles

        self.open_dances = []
        self.print_fn = print_fn

    def get_dance_positions(self):
        positions = []
        for dance in self.open_dances:
            positions.append(list(zip(dance.coords, dance.angles)))
        return positions

    def process(self, waggle):

        indices_to_delete = []
        result_coordinates = []

        added = False

        for idx, dance in enumerate(self.open_dances):
            offset = (waggle.timestamp - dance.get_last_timestamp()).total_seconds()
            if offset > self.min_delay or offset < 0:
                indices_to_delete.append(idx)
                continue

            if dance.get_min_distance(waggle.x, waggle.y) > self.min_distance:
                continue

            dance.append(waggle)
            if len(dance) >= self.min_waggles:
                dance.trigger()
                result_coordinates.append((waggle.x, waggle.y))

            added = True
            break

        for idx in indices_to_delete[::-1]:
            del self.open_dances[idx]

        if not added:
            dance = Dance()
            dance.append(waggle)
            self.open_dances.append(dance)

        return result_coordinates
