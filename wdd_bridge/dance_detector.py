import math
import numpy as np
import pandas
import scipy.stats

def calculate_angle_consensus(all_angles, inlier_cutoff=np.pi/4.0, verbose=False):
    """Takes angles in radians. Performs RANSAC and returns consensus angle.
    """
    
    all_angles = np.array(all_angles)

    # Special cases.
    if all_angles.shape[0] < 2:
        # No use performing any consensus on a small set.
        return all_angles[0], 1
    
    # Normalize angles to be [0, 2 * np.pi]
    all_angles = (all_angles + 2.0 * np.pi) % (2.0 * np.pi)
    
    sample_indices = np.arange(all_angles.shape[0])
    n_samples = all_angles.shape[0] * 4
    
    max_inliers = 0
    max_inlier_consensus_angle = None
    inlier_indices = None
    
    
    for _sample_index in range(n_samples):
        
        samples = np.random.choice(sample_indices, size=2)
        consensus_angle = scipy.stats.circmean(all_angles[samples])
        
        differences0 = np.abs(all_angles - consensus_angle)
        differences1 = (2.0 * np.pi) - differences0
        inliers = (differences0 < inlier_cutoff) | (differences1 < inlier_cutoff)
        
        n_inliers = np.sum(inliers)
        if n_inliers > max_inliers:
            max_inliers = n_inliers
            max_inlier_consensus_angle = consensus_angle
            inlier_indices = inliers
            
    if max_inliers == 0:
        if verbose:
            print("Could not find consensus at all.")
        return all_angles[0], 1
    
    consensus_angle = scipy.stats.circmean(all_angles[inlier_indices])
    if verbose:
        print("Angle consensus with {} inliers ({:1.1f}° [{:1.1f}°]), {}.".format(
            max_inliers,
            consensus_angle / np.pi * 180.0,
            max_inlier_consensus_angle / np.pi * 180.0,
            list(all_angles[inlier_indices] / np.pi * 180.0)))
        
    return consensus_angle, max_inliers

class Waggle:
    def __init__(self, x, y, angle, duration, timestamp, cam_id, uuid):
        self.x = x
        self.y = y
        self.angle = angle
        self.duration = duration
        self.timestamp = timestamp
        self.cam_id = cam_id
        self.uuid = uuid


class Dance:
    def __init__(self):

        self.coords = []
        self.angles = []
        self.durations = []
        self.timestamps = []
        self.triggered = 0
        self.waggle_ids = []

        self._dance_angle = None
        self._n_inliers = None

    def get_first_timestamp(self):
        return self.timestamps[0]

    def get_last_timestamp(self):
        return self.timestamps[-1]

    def get_min_distance(self, x, y):

        min_distance = 1e1000
        for (cx, cy) in self.coords:
            distance = math.sqrt((cx - x) ** 2.0 + (cy - y) ** 2.0)

            min_distance = min(distance, min_distance)

        return min_distance

    def append(self, waggle):
        self._dance_angle, self._n_inliers = None, None

        self.coords.append((waggle.x, waggle.y))
        self.angles.append(waggle.angle)
        self.durations.append(waggle.duration)
        self.timestamps.append(waggle.timestamp)
        self.waggle_ids.append(waggle.uuid)

    def trigger(self):
        self.triggered += 1

    def __len__(self):
        return len(self.timestamps)

    def _ensure_dance_angle(self):
        if self._dance_angle is None:
            self._dance_angle, self._n_inliers = calculate_angle_consensus(self.angles)

    def get_dance_angle(self):
        self._ensure_dance_angle()
        return self._dance_angle

    def get_dance_angle_inliers(self):
        self._ensure_dance_angle()
        return self._n_inliers

    def get_waggle_duration(self):
        durations = np.array(self.durations)
        durations = durations[~pandas.isnull(durations)]
        if durations.shape[0] == 0:
            return np.nan
        return np.median(durations)
    
    def get_first_waggle_id(self):
        return self.waggle_ids[0]

class DanceDetector:
    def __init__(
        self,
        waggle_max_distance=200.0,
        waggle_max_gap=7.0,
        waggle_min_count=3,
        print_fn=None,
        log_fn=None,
    ):

        self.waggle_max_distance = waggle_max_distance
        self.waggle_max_gap = waggle_max_gap
        self.waggle_min_count = waggle_min_count

        self.open_dances = []
        self.print_fn = print_fn
        self.log_fn = log_fn

    def get_dance_positions(self):
        positions = []
        for dance in self.open_dances:
            positions.append(list(zip(dance.coords, dance.angles)))
        return positions

    def process(self, waggle):

        indices_to_delete = []

        added = False

        for idx, dance in enumerate(self.open_dances):
            last_waggle_timestamp = dance.get_last_timestamp()
            offset = (waggle.timestamp - last_waggle_timestamp).total_seconds()
            if offset > self.waggle_max_gap or offset < 0:
                indices_to_delete.append(idx)
                continue

            if dance.get_min_distance(waggle.x, waggle.y) > self.waggle_max_distance:
                continue

            dance.append(waggle)
            if len(dance) >= self.waggle_min_count:
                dance_angle = dance.get_dance_angle()
                dance_duration = dance.get_waggle_duration()
                n_inliers = dance.get_dance_angle_inliers()

                if n_inliers >= self.waggle_min_count:
                    dance.trigger()

                    self.log_fn(
                        "detected dance",
                        first_waggle=dance.get_first_timestamp(),
                        last_timestamp=dance.get_last_timestamp(),
                        dance_angle=float(dance_angle), dance_angle_inliers=int(n_inliers),
                        waggle_duration=float(dance_duration),
                        cam_id=waggle.cam_id,
                        waggle_index=len(dance),
                        waggle_ids=dance.waggle_ids
                    )

                    yield (waggle.x, waggle.y, dance_angle, dance_duration, dance.get_first_waggle_id())


            added = True
            break

        for idx in indices_to_delete[::-1]:
            del self.open_dances[idx]

        if not added:
            dance = Dance()
            dance.append(waggle)
            self.open_dances.append(dance)
