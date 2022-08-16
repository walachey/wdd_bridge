from .wdd_listener import WDDListener
from .dance_detector import DanceDetector
from .comb_connector import CombConnector, ActuatorSignalSelectionMessage, TriggerMessage
from .comb_mapper import CombMapper
from .experimental_control import ExperimentalControl
from .statistics import Statistics
from .azimuth import AzimuthUpdater

import asciimatics
import asciimatics.screen
import collections
import datetime
import json
import numpy as np

def world_angle_to_direction_string(world_angle):
    world_directions = [
                            "E", "NEE", "NE", "NNE",
                            "N", "NNW", "NW", "NWW",
                            "W", "SWW", "SW", "SSW",
                            "S", "SSE", "SE", "SEE"
                            ]
    world_direction_step_size = (360.0 / len(world_directions))
    # Make sure to round to nearest by adding 0.5 * world_direction_step_size
    angle = (2.0 * np.pi + world_angle + (world_direction_step_size / 180.0 * np.pi) / 2.0) % (2.0 * np.pi)
    world_direction = world_directions[int((angle / np.pi * 180.0) / world_direction_step_size)]
    return world_direction

class HiveSide:
    """In case a single frame is recorded from both sides, they need separate dance clustering and homography mappings."""

    def __init__(self, cam_id, log_fn, print_fn, comb_config, azimuth_updater,
                    suppression_soundfile_index,
                    suppression_signal_index,
                    suppression_signal_duration,
                    use_all_actuators,
                    use_hardwired_signals,
                    use_soundboard=(0,),
                    detector_kws={}):
        self.cam_id = cam_id
        self.log_fn = log_fn
        self.print_fn = print_fn
        self.azimuth_updater = azimuth_updater
        self.suppression_soundfile_index = suppression_soundfile_index
        self.suppression_signal_index = suppression_signal_index
        self.suppression_signal_duration = suppression_signal_duration
        self.use_all_actuators = use_all_actuators
        self.use_hardwired_signals = use_hardwired_signals
        self.use_soundboard = use_soundboard

        self.dance_detector = DanceDetector(print_fn=print_fn, log_fn=self.log_fn, **detector_kws)
        self.comb_mapper = CombMapper(config=comb_config, azimuth_updater=azimuth_updater, print_fn=self.print_fn)

        self.hardwired_signals = []

        signal_groups = collections.defaultdict(list)

        if self.use_hardwired_signals:
            for idx, config in enumerate(self.comb_mapper.get_actuator_metadata()):
                soundboard_set = "soundboard_index" in config
                sound_set = "sound_index" in config

                # Either both or non have to be set.
                if soundboard_set != sound_set:
                    raise ValueError("In hardwired mode, both 'soundboard_index' and 'sound_index' have to be set for an actuator (or none of both). Check config for actuator {}.".format(idx))

                if not soundboard_set:
                    self.hardwired_signals.append(None)
                    continue

                try:
                    soundboard_index = int(config["soundboard_index"])
                    sound_index = int(config["sound_index"])
                    trigger_message = [None, None]
                    trigger_message[soundboard_index] = sound_index
                except Exception as e:
                    raise ValueError("'soundboard_index' or 'sound_index' got invalid value for actuator {}.".format(idx))
                
                self.hardwired_signals.append(TriggerMessage(*trigger_message,
                            duration=self.suppression_signal_duration,
                            manual_actuator_index=idx))

                signal_groups[tuple(trigger_message)].append(idx)
            
            if len(signal_groups) > 0:
                max_actuators_in_group = max([len(g) for g in signal_groups.values()])
                if max_actuators_in_group > 1:
                    groups_label = []
                    for signal, indices in signal_groups.items():
                        groups_label.append("+".join(map(str, indices)) + " " + str(signal))
                        for index in indices:
                            self.hardwired_signals[index].set_actuator_index(indices)
                    self.print_fn("Found {} actuator groups: {}.".format(len(signal_groups), ", ".join(groups_label)))
                
    def close(self):
        pass
    
    def get_activation_message(self, actuator_index):

        if self.use_hardwired_signals:
            return self.hardwired_signals[actuator_index]

        if self.use_all_actuators:
            indices = [None, None]
            for i in self.use_soundboard:
                indices[i] = self.suppression_soundfile_index
            return TriggerMessage(*indices, duration=self.suppression_signal_duration)

        return ActuatorSignalSelectionMessage(
                actuator_index=actuator_index,
                signal_index=self.suppression_signal_index,
                duration=self.suppression_signal_duration
        )

    def process(self, waggle_info):
        coordinates = self.dance_detector.process(waggle_info)

        for (x, y, waggle_angle, waggle_duration) in coordinates:
            
            waggle_angle_orig = waggle_angle
            xy, (waggle_angle, world_angle), (idx, distance) = self.comb_mapper.map_to_comb(x, y, waggle_angle)

            world_direction = world_angle_to_direction_string(world_angle)

            self.print_fn("Dance for {} ({:1.1f}°), {:1.2f}s ('{}', grav. {:1.1f}° [raw {:1.1f}°, az. {:1.1f}°])".format(
                world_direction, world_angle / np.pi * 180.0, waggle_duration, self.cam_id,
                waggle_angle / np.pi * 180.0, waggle_angle_orig / np.pi * 180.0, self.azimuth_updater.get_azimuth() / np.pi * 180.0))

            yield world_angle, self.get_activation_message(idx)


class Bridge:
    def __init__(
        self, wdd_port, wdd_authkey, comb_port, comb_config, draw_arrows, stats_file, no_gui=False,
        sound_index=0, signal_index=1, all_actuators=False, hardwired_signals=False, signal_duration=1.0,
        waggle_max_gap=7.0, waggle_min_count=3, waggle_max_distance=200.0, use_soundboard=[]
    ):
        if use_soundboard is None or len(use_soundboard) == 0:
            use_soundboard = (0,)

        self.wdd_port = wdd_port
        self.wdd_authkey = wdd_authkey
        self.comb_port = comb_port
        self.draw_arrows = draw_arrows
        self.no_gui = no_gui

        # Advanced logging.
        if stats_file:
            self.statistics = Statistics(filename=stats_file)
            self.log_fn = self.statistics.log
        else:
            self.statistics = None
            self.log_fn = lambda _, **_kwargs: None

        # Printing in the UI.
        self.log = []

        def print_fn(x, **kwargs):
            self.log.append(
                "[{}] {}".format(datetime.datetime.utcnow().time().isoformat(), x)
            )
            if self.statistics is not None:
                self.log_fn("log", text=x, **kwargs)

        self.print_fn = print_fn

        self.running = True

        with open(comb_config, "r") as f:
            config = json.load(f)
        
        if "experiment" in config:
            self.experimental_control = ExperimentalControl(config["experiment"], print_fn=self.print_fn, log_fn=self.log_fn)
        else:
            self.experimental_control = None

        self.azimuth_updater = AzimuthUpdater(
                latitude=config["latitude"],
                longitude=config["longitude"]
                )

        self.cameras = dict()
        for camera_config in config["cameras"]:
            self.cameras[camera_config["cam_id"]] = HiveSide(
                cam_id=camera_config["cam_id"],
                log_fn=self.log_fn,
                print_fn=self.print_fn,
                comb_config=camera_config,
                azimuth_updater=self.azimuth_updater,
                suppression_soundfile_index=sound_index,
                suppression_signal_index=signal_index,
                suppression_signal_duration=signal_duration,
                use_all_actuators=all_actuators,
                use_hardwired_signals=hardwired_signals,
                use_soundboard=use_soundboard,
                detector_kws=dict(
                    waggle_max_gap=waggle_max_gap,
                    waggle_min_count=waggle_min_count,
                    waggle_max_distance=waggle_max_distance,
                )
            )
        print("Loaded configs for {} cameras.".format(len(self.cameras)))

        print("Initializing WDD connection..", flush=True)
        self.wdd = WDDListener(
            port=wdd_port, authkey=wdd_authkey, print_fn=print_fn, log_fn=self.log_fn
        )

        print("Initializing serial connection..", flush=True)
        self.comb = CombConnector(
            port=comb_port,
            actuator_count=next(iter(self.cameras.values())).comb_mapper.get_actuator_count(),
            print_fn=print_fn,
            log_fn=self.log_fn,
            all_actuators=all_actuators,
            hardwired_signals=hardwired_signals,
            signal_index=signal_index,
            sound_index=sound_index,
            use_soundboard=use_soundboard
        )

        self.screen = None

    def stop(self):
        if self.running:
            self.log_fn("stopping execution")
            self.running = False

            if self.screen is not None:
                self.screen.close()

            self.wdd.close()
            self.comb.close()
            for cam in self.cameras.values():
                cam.close()

            if self.statistics is not None:
                self.statistics.close()


    def run(self):

        self.log_fn("starting execution")
        try:
            while self.running:
                
                if not self.no_gui:
                    self.run_ui()

                # Poll with a timeout, so we can e.g. interrupt the process.
                waggle_info = self.wdd.get_message(block=True, timeout=1.0)

                if not self.running:
                    self.stop()
                    break

                if not waggle_info:
                    continue
                waggle_cam_id = waggle_info.cam_id
                if waggle_cam_id not in self.cameras:
                    self.print_fn("Received waggle for invalid camera ID.")

                messages = self.cameras[waggle_cam_id].process(waggle_info)

                for world_angle, message in messages:
                    
                    if message is None:
                        continue

                    if self.experimental_control is not None:
                        message = self.experimental_control.filter_message(message, world_angle)
                    
                    if message is not None:
                        self.log_fn("sending comb message", what=str(message))
                        self.comb.send_message(message)
        except Exception as e:
            import traceback
            self.log_fn("Main loop received exception: {}".format(str(e)), stacktrace=traceback.format_exc())
            raise
        finally:
            self.stop()

    def run_ui(self):
        def ui(screen):
            
            # Use the general information from any one side/camera (e.g. number of sensors).
            any_side = next(iter(self.cameras.values()))
            _, origin_y = any_side.comb_mapper.get_origin()
            screen.clear_buffer(7, 2, 0)

            ev = screen.get_key()
            is_number_key = ev is not None and (ev >= ord("0") and ev <= ord("9"))

            if ev in (ord("Q"), ord("q")):
                self.stop()
                print("Aborting!", flush=True)
                return
            elif ev in (ord("t"), ord("T")) or is_number_key:
                import pytz
                from .wdd_listener import Waggle
                x, y = 600, 200

                if is_number_key:
                    index = ev - ord("0")
                    w, h = any_side.comb_mapper.get_image_shape()
                    cols = 5
                    y = (1 + 2 * (index // cols)) * h / 4.0
                    x = (2 + (index % cols)) * (w / (cols + 2))

                waggle = Waggle(
                        x, y, 104 / 180.0 * np.pi, 0.42, pytz.UTC.localize(datetime.datetime.now()), "cam0", uuid=0
                    )
                self.wdd.incoming_queue.put(waggle)

            # Draw outline.

            hx0, hy0, hx1, hy1 = any_side.comb_mapper.get_comb_rectangle()
            hwidth, hheight = hx1 - hx0, hy1 - hy0

            # Make sure we have enough space for the logs below the screen.
            log_margin_lines = 10

            # Usually, fonts are higher than wide. Account a bit for that.
            for font_width_factor in (1.5, 1.25, 1.0):
                ctop, cbottom = 3, int(screen.height - log_margin_lines)
                cheight = cbottom - ctop
                cwidth = int(font_width_factor * cheight * (hwidth / hheight))
                if cwidth < screen.width:
                    break

            cleft, cright = int(0.5 * (screen.width - cwidth)), int(0.5 * (screen.width + cwidth))

            def draw_border(start, to):
                screen.move(*start)
                screen.draw(*to)

            draw_border((cleft, ctop), (cright, ctop))
            draw_border((cright, ctop), (cright, cbottom))
            draw_border((cright, cbottom), (cleft, cbottom))
            draw_border((cleft, cbottom), (cleft, ctop))

            def draw_at_comb_position(xy, char, color):
                xy = xy.astype(np.float32)
                xy -= np.array([hx0, hy0], dtype=np.float32)
                xy /= np.array([hwidth, hheight], dtype=np.float32)
                xy *= np.array([cwidth, cheight], dtype=np.float32)
                xy += np.array([cleft, ctop], dtype=np.float32)
                x, y = xy.astype(np.int32)
                if origin_y == "bottom":
                    y = cheight - (y - ctop) + ctop
                screen.print_at(char, x, y, colour=color)

            # Draw current open dances.
            arrows = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘", "→"]
            side_colors = [
                asciimatics.screen.Screen.COLOUR_YELLOW,
                asciimatics.screen.Screen.COLOUR_CYAN,
            ]
            for side_index, hive_side in enumerate(self.cameras.values()):
                for dance_positions in hive_side.dance_detector.get_dance_positions():
                    for idx, ((x, y), o) in enumerate(dance_positions):
                        xy, _, _ = hive_side.comb_mapper.map_to_comb(
                            x, y, waggle_angle=0.0, find_sensor=False
                        )
                        char = "." if idx < len(dance_positions) - 1 else "o"
                        if self.draw_arrows and o is not None:
                            o = o / np.pi * 180
                            o = (o + 360) % 360
                            char = arrows[int(round(o / 45, 0))]
                        draw_at_comb_position(
                            xy, char=char, color=side_colors[side_index]
                        )

            for actuator_index, (x, y) in enumerate(any_side.comb_mapper.get_sensor_coordinates()):
                is_active = self.comb.is_actuator_active(actuator_index)

                draw_at_comb_position(
                    np.array([x, y]),
                    char="X",
                    color=asciimatics.screen.Screen.COLOUR_BLUE if not is_active else asciimatics.screen.Screen.COLOUR_YELLOW,
                )

            screen.print_at(
                "{} -- sun at {}".format(
                    datetime.datetime.utcnow().isoformat(),
                    world_angle_to_direction_string(self.azimuth_updater.get_azimuth())
                ),
                1,
                1,
                colour=asciimatics.screen.Screen.COLOUR_CYAN,
            )

            space = screen.height - cbottom - 1
            if space > 0:
                log = self.log[-space:]
                for i in range(min(len(log), space)):
                    screen.print_at(
                        log[i],
                        0,
                        cbottom + 1 + i,
                        colour=asciimatics.screen.Screen.COLOUR_CYAN,
                    )

            screen.refresh()

        if self.screen is not None and self.screen.has_resized():
            self.screen.close()
            self.screen = None

        if self.screen is None:
            self.screen = asciimatics.screen.Screen.open()
        ui(self.screen)
