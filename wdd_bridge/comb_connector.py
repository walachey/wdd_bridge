import datetime
import queue
import serial
import time
import threading


class CombActuatorMessage:
    def is_activation_message(self):
        return False

    def is_deactivation_message(self):
        return False


class CombTriggerActuatorMessage(CombActuatorMessage):
    # The default constructor deactivates the signal for the given actuator.
    def __init__(
        self, actuator_index, signal_duration=1.0, signal_index=None, side=None
    ):
        self.actuator_index = actuator_index
        self.signal_duration = signal_duration
        self.signal_index = signal_index
        self.side = side

    def __str__(self):
        if self.is_deactivation_message():
            return "mux {} 0".format(self.actuator_index)
        return "mux {} {} {}".format(self.actuator_index, self.signal_index, self.side)

    def is_deactivation_message(self):
        return not self.signal_index

    def is_activation_message(self):
        return not self.is_deactivation_message()

    def get_deactivation_message(self):
        return self.signal_duration, CombTriggerActuatorMessage(self.actuator_index)

    def get_actuator_index(self):
        return self.actuator_index


class Actuator:
    """We need to keep a virtual sensor map around so two simultaneuos signals for one sensor don't interefere."""

    def __init__(self):
        self.active_until = None

    def is_active(self, dt=None):
        if self.active_until is None:
            return False

        if dt is None:
            dt = datetime.datetime.utcnow()
        return (self.active_until - dt).total_seconds() > 0e-3

    def set_active_for(self, seconds):
        self.set_active_until(
            datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        )

    def set_active_until(self, timestamp):
        self.active_until = timestamp


class CombConnector:

    def __init__(self, port, actuator_count, print_fn, log_fn, character_delay=0.001):

        self.audio_file = None
        if port.endswith(".wav"):
            self.audio_file = port
            port = ""

        self.actuators = [Actuator() for i in range(actuator_count)]
        self.character_delay = character_delay
        self.dummy_mode = not port

        if not self.dummy_mode:
            self.con = serial.Serial(
                port=port,
                baudrate=9600,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_TWO,
                bytesize=serial.SEVENBITS,
            )
        else:
            self.con = None

        self.print_fn = print_fn
        self.log_fn = log_fn

        self.output_queue = queue.Queue()

        run_fn = self.run_connector
        if self.audio_file is not None:
            run_fn = self.run_local_audio_mode

        self.listener_thread = threading.Thread(target=run_fn, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def close(self):
        self.running = False

        if self.con and self.con.isOpen():
            self.con.close()

        self.output_queue.put(None)
        self.listener_thread.join()

    def run_local_audio_mode(self):
        
        import simpleaudio

        audio = simpleaudio.WaveObject.from_wave_file(self.audio_file)

        self.running = True

        self.print_fn("Comb: Running in audio-only mode...")

        while self.running:

            message = self.output_queue.get()
            if message is None or not self.running:
                break

            self.print_fn(str(message))

            audio.play()

    def run_connector(self):

        self.running = True

        while self.running:

            self.print_fn("Comb: Waiting for serial connection...")
            while self.running and (self.dummy_mode or not self.con.isOpen()):
                if not self.dummy_mode:
                    self.con.open()
                time.sleep(1.0)

            if not self.running:
                return

            self.print_fn("Comb: Opened serial connection.")

            while True:

                message = self.output_queue.get()
                if message is None:
                    break

                if not self.con.isOpen():
                    self.print_fn("Comb: Serial connection broken. Message dropped.")
                    break
                self._send_serial_message(message)

    def send_message(self, message):
        self.output_queue.put(message)

    def _send_serial_message(self, message):

        # Potentially schedule deactivation.
        def schedule_deactivation(delay, deactivation_message):
            time.sleep(delay)
            self.output_queue.put(deactivation_message)

        if message.is_activation_message():

            delay, deactivation_message = message.get_deactivation_message()
            self.actuators[message.get_actuator_index()].set_active_for(delay)

            scheduling_thread = threading.Thread(
                target=schedule_deactivation,
                args=(delay, deactivation_message),
                kwargs=(),
            )
            scheduling_thread.start()
        elif message.is_deactivation_message():
            # Only deactivate if no other message activated it in the meantime.
            if self.actuators[message.get_actuator_index()].is_active():
                self.print_fn("Skipping actuator deactivation.")
                return

        message = (str(message).upper() + "\r\n").encode("utf-8")

        self.log_fn(
            "serial message", text=message, character_delay=self.character_delay
        )

        if not self.character_delay:
            self.con.write(message)
        else:
            for char in message:
                self.con.write(char)
                time.sleep(self.character_delay)
