from .wdd_listener import WDDListener
from .dance_detector import DanceDetector
from .comb_connector import CombConnector, CombTriggerActuatorMessage
from .comb_mapper import CombMapper
from .statistics import Statistics

import asciimatics
import asciimatics.screen
import datetime
import numpy as np


class Bridge:
    def __init__(
        self, wdd_port, wdd_authkey, comb_port, comb_config, draw_arrows, stats_file
    ):
        self.wdd_port = wdd_port
        self.wdd_authkey = wdd_authkey
        self.comb_port = comb_port
        self.draw_arrows = draw_arrows

        # Advanced logging.
        if stats_file:
            self.statistics = Statistics(filename=stats_file)
            self.log_fn = self.statistics.log
        else:
            self.statistics = None
            self.log_fn = lambda _, **_kwargs: None

        # Printing in the UI.
        self.log = []

        def print_fn(x):
            self.log.append(
                "[{}] {}".format(datetime.datetime.utcnow().time().isoformat(), x)
            )
            if self.statistics is not None:
                self.log_fn("log", text=x)

        self.print_fn = print_fn

        self.running = True

        print("Initializing WDD connection..", flush=True)
        self.wdd = WDDListener(
            port=wdd_port, authkey=wdd_authkey, print_fn=print_fn, log_fn=self.log_fn
        )
        self.dance_detector = DanceDetector(print_fn=print_fn, log_fn=self.log_fn)
        self.comb_mapper = CombMapper(config_path=comb_config)
        print("Initializing serial connection..", flush=True)
        self.comb = CombConnector(
            port=comb_port,
            actuator_count=self.comb_mapper.get_actuator_count(),
            print_fn=print_fn,
            log_fn=self.log_fn,
        )

        self.screen = None

    def stop(self):
        if self.running:
            self.log_fn("stopping execution")
            self.running = False
            self.wdd.close()
            self.comb.close()
            if self.statistics is not None:
                self.statistics.close()

            if self.screen is not None:
                self.screen.close()

    def run(self):

        self.log_fn("starting execution")
        try:
            while self.running:
                self.run_ui()
                # Poll with a timeout, so we can e.g. interrupt the process.
                waggle_info = self.wdd.get_message(block=True, timeout=1.0)

                if not self.running:
                    self.stop()
                    break

                if not waggle_info:
                    continue
                coordinates = self.dance_detector.process(waggle_info)

                for (x, y) in coordinates:
                    self.print_fn("Activating vibration")

                    xy, (idx, distance) = self.comb_mapper.map_to_comb(x, y)
                    self.comb.send_message(
                        CombTriggerActuatorMessage(idx, signal_index=1, side=1)
                    )
        finally:
            self.stop()

    def run_ui(self):
        def ui(screen):

            screen.clear_buffer(7, 2, 0)

            ev = screen.get_key()
            if ev in (ord("Q"), ord("q")):
                self.stop()
                print("Aborting!", flush=True)
                return

            # Draw outline.

            hx0, hy0, hx1, hy1 = self.comb_mapper.get_comb_rectangle()
            hwidth, hheight = hx1 - hx0, hy1 - hy0

            cleft, cright = int(screen.width * 0.1), int(screen.width * 0.9)
            cwidth = cright - cleft
            ctop, cbottom = min(5, cleft), int(cwidth * (hheight / hwidth))
            cheight = cbottom - ctop

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
                screen.print_at(char, x, y, colour=color)

            # Draw current open dances.
            arrows = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘", "→"]
            for dance_positions in self.dance_detector.get_dance_positions():
                for idx, ((x, y), o) in enumerate(dance_positions):
                    xy, _ = self.comb_mapper.map_to_comb(x, y, find_sensor=False)
                    char = "." if idx < len(dance_positions) - 1 else "o"
                    if self.draw_arrows and o is not None:
                        o = o / np.pi * 180
                        o = (o + 360) % 360
                        char = arrows[int(round(o / 45, 0))]
                    draw_at_comb_position(
                        xy, char=char, color=asciimatics.screen.Screen.COLOUR_YELLOW
                    )

            for (x, y) in self.comb_mapper.get_sensor_coordinates():
                draw_at_comb_position(
                    np.array([x, y]),
                    char="X",
                    color=asciimatics.screen.Screen.COLOUR_BLUE,
                )

            screen.print_at(
                datetime.datetime.utcnow().isoformat(),
                1,
                1,
                colour=asciimatics.screen.Screen.COLOUR_CYAN,
            )

            space = screen.height - cbottom
            if space > 0:
                log = self.log[-space:]
                for i in range(min(len(log), space)):
                    screen.print_at(
                        log[i],
                        0,
                        cbottom + 2 + i,
                        colour=asciimatics.screen.Screen.COLOUR_CYAN,
                    )

            screen.refresh()

        if self.screen is None:
            self.screen = asciimatics.screen.Screen.open()
        ui(self.screen)
