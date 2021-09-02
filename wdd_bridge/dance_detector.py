import math
import numpy as np
import scipy.stats

def calculate_angle_consensus(all_angles, inlier_cutoff=np.pi/4.0, verbose=False):
    """Takes angles in radians. Performs RANSAC and returns consensus angle.
    """
    
    # Special cases.
    if all_angles.shape[0] < 3:
        # No use performing any consensus on a small set.
        return all_angles[0]
    
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
        return all_angles[0]
    
    consensus_angle = scipy.stats.circmean(all_angles[inlier_indices])
    if verbose:
        print("Angle consensus with {} inliers ({:1.1f}° [{:1.1f}°]), {}.".format(
            max_inliers,
            consensus_angle / np.pi * 180.0,
            max_inlier_consensus_angle / np.pi * 180.0,
            list(all_angles[inlier_indices] / np.pi * 180.0)))
        
    return consensus_angle

class Waggle:
    def __init__(self, x, y, angle, timestamp, cam_id):
        self.x = x
        self.y = y
        self.angle = angle
        self.timestamp = timestamp
        self.cam_id = cam_id


class Dance:
    def __init__(self):

        self.coords = []
        self.angles = []
        self.timestamps = []
        self.triggered = 0

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
        self.coords.append((waggle.x, waggle.y))
        self.angles.append(waggle.angle)
        self.timestamps.append(waggle.timestamp)

    def trigger(self):
        self.triggered += 1

    def __len__(self):
        return len(self.timestamps)

    def get_dance_angle(self):
        return calculate_angle_consensus(self.angles)

class DanceDetector:
    def __init__(
        self,
        min_distance=200.0,
        min_delay=7.0,
        min_waggles=3,
        print_fn=None,
        log_fn=None,
    ):

        self.min_distance = min_distance
        self.min_delay = min_delay
        self.min_waggles = min_waggles

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
            if offset > self.min_delay or offset < 0:
                indices_to_delete.append(idx)
                continue

            if dance.get_min_distance(waggle.x, waggle.y) > self.min_distance:
                continue

            dance.append(waggle)
            if len(dance) >= self.min_waggles:
                dance.trigger()
                dance_angle = dance.get_dance_angle()
                yield (waggle.x, waggle.y, dance_angle)

                self.log_fn(
                    "detected dance",
                    first_waggle=dance.get_first_timestamp(),
                    last_timestamp=dance.get_last_timestamp(),
                    dance_angle=dance_angle,
                    cam_id=waggle.cam_id,
                    waggle_index=len(dance)
                )

            added = True
            break

        for idx in indices_to_delete[::-1]:
            del self.open_dances[idx]

        if not added:
            dance = Dance()
            dance.append(waggle)
            self.open_dances.append(dance)
