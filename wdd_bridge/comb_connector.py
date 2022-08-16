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

    def __str__(self):
        return str(self.__class__.__name__) + "(???)"

class SetLEDsMessage(CombActuatorMessage):

    def __init__(self, config):
        if config < 0 or config > 7:
            raise ValueError("LED config must be in range 0-7 (got {}).".format(config))

        self.config = config
    
    def get_serial_message(self):
        return "LEDS {}".format(self.config)

    def __str__(self):
        return "SetLEDsMessage(config={})".format(self.config)

class ActuatorSignalSelectionMessage(CombActuatorMessage):

    def __init__(self, actuator_index, signal_index=0, duration=None):

        if not (actuator_index >= 0 and actuator_index <= 7):
            raise ValueError("Actuator index must be in range [0, 7], got {}.".format(actuator_index))

        if not (signal_index >= 0 and signal_index <= 4):
            raise ValueError("Signal index must be in range [0, 4], got {}.".format(signal_index))

        self.actuator_index = actuator_index
        self.signal_index = signal_index
        self.duration = duration

    def is_deactivation_message(self):
        return self.signal_index == 0
    
    def is_activation_message(self):
        return self.duration is not None and not self.is_deactivation_message()
    
    def get_deactivation_message(self):
        if self.duration is None:
            return None, None
        return self.duration, ActuatorSignalSelectionMessage(self.actuator_index, signal_index=0)

    def get_actuator_index(self):
        return self.actuator_index

    def get_serial_message(self):
        return "mux {} {}".format(self.actuator_index, self.signal_index)

    def __str__(self):
        return "ActuatorSignalSelectionMessage(actuator_index={}, signal_index={})".format(
            self.actuator_index, self.signal_index)

class StopTriggerMessage(CombActuatorMessage):

    def __init__(self):
        pass

    def is_deactivation_message(self):
        return True
    
    def get_actuator_index(self):
        return None

    def get_serial_message(self):
        return "stop_trig"

    def __str__(self):
        return "StopTriggerMessage()"

class TriggerMessage(CombActuatorMessage):

    def __init__(self, file_index0=None, file_index1=None, duration=1.0, manual_actuator_index=None):

        if file_index0 is None:
            file_index0 = 11
        if file_index1 is None:
            file_index1 = 11

        for file_index in (file_index0, file_index1):
            if not (file_index >= 0 and file_index <= 11):
                raise ValueError("File index must be in range [0, 11], got {}.".format(file_index))

        self.file_index0 = file_index0
        self.file_index1 = file_index1
        self.duration = duration
        self.set_actuator_index(manual_actuator_index)

    def set_actuator_index(self, index):
        """
        Can be None (all actuators), an integer (actuator index) or a list of integers.
        """
        self.manual_actuator_index = index

    def is_deactivation_message(self):
        return self.file_index0 == 11 and self.file_index1 == 11

    def is_activation_message(self):
        return self.duration is not None and not self.is_deactivation_message()

    def get_actuator_index(self):
        # Defaults to None.
        return self.manual_actuator_index

    def get_deactivation_message(self):
        if self.duration is None:
            return None, None
        return self.duration, StopTriggerMessage()

    def get_serial_message(self):
        return "trig {} {}".format(self.file_index0, self.file_index1)

    def __str__(self):
        return "TriggerMessage(file_index0={}, file_index1={}, duration={})".format(
            self.file_index0, self.file_index1, self.duration)

class LinkAllActuatorsToSignal(CombActuatorMessage):

    def __init__(self, signal_index):
        self.signal_index = signal_index

    def get_serial_message(self):
        return [ActuatorSignalSelectionMessage(i, signal_index=self.signal_index) for i in range(8)]

    def is_deactivation_message(self):
        return self.signal_index == 0

    def get_actuator_index(self):
        return None

    def __str__(self):
        return "LinkAllActuatorsToSignal(signal_index={})".format(
            self.signal_index)

class DisableAllActuators(LinkAllActuatorsToSignal):

    def __init__(self):
        super().__init__(signal_index = 0)

    def __str__(self):
        return "DisableAllActuators()"
        
class StopSoundfileOnActuator(CombActuatorMessage):

    def __init__(self, actuator_index):

        self.actuator_index = actuator_index

    def is_deactivation_message(self):
        return True

    def get_actuator_index(self):
        return self.actuator_index

    def get_serial_message(self):
        
        output = [StopTriggerMessage()]

        if self.actuator_index is None:
            output.append(DisableAllActuators())
        else:
            output.append(ActuatorSignalSelectionMessage(self.actuator_index, signal_index=0))
        
        return output

    def __str__(self):
        return "StopSoundfileOnActuator(actuator_index={})".format(
            self.actuator_index)

class PlaySoundfileOnActuator(CombActuatorMessage):

    def __init__(self, actuator_index, file_index, signal_index, duration=1.0):
        self.actuator_index = actuator_index
        self.file_index = file_index
        self.signal_index = signal_index
        self.duration = duration

    def is_activation_message(self):
        return True
    
    def get_actuator_index(self):
        return self.actuator_index

    def get_deactivation_message(self):
        return self.duration, StopSoundfileOnActuator(self.actuator_index)

    def get_serial_message(self):
        output = []
        if self.actuator_index is None:
            output.append(LinkAllActuatorsToSignal(self.signal_index))
        else:
            output.append(ActuatorSignalSelectionMessage(self.actuator_index, self.signal_index))

        output.append(TriggerMessage(self.file_index, duration=self.duration))

        return output

    def __str__(self):
        return "PlaySoundfileOnActuator(actuator_index={}, file_index={}, signal_index={}, duration={})".format(
            self.actuator_index, self.file_index, self.signal_index, self.duration)

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

    def __init__(self, port, actuator_count, print_fn, log_fn, character_delay=0.001,
                all_actuators=False, hardwired_signals=False, signal_index=0, sound_index=0):

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
        elif self.dummy_mode:
            # When we don't connect to a serial port, we process messages directly.
            run_fn = self.process_queue_for_serial_connection

        self.running = True
        self.listener_thread = threading.Thread(target=run_fn, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

        if not self.dummy_mode:

            # Can be unjoinable.
            led_flashing_thread = threading.Thread(target=self.flash_leds, args=())
            led_flashing_thread.daemon = True
            led_flashing_thread.start()

        if hardwired_signals:
            # When we have hardcoded signals and soundfile indices,
            # we just stop everything at the start.
            self.send_message(StopTriggerMessage())
        elif all_actuators:
            # All actuators are always playing at the same time?
            # Then, we link them to the correct signal here.
            self.send_message(StopTriggerMessage())
            self.send_message(LinkAllActuatorsToSignal(signal_index=signal_index))
        else:
            # Otherwise, we can unlink all actuators but already play the signal.
            self.send_message(DisableAllActuators())
            self.send_message(TriggerMessage(file_index0=sound_index, duration=None))



    def flash_leds(self):
        time.sleep(0.5)
        for i in range(0, 3):
            self.send_message(SetLEDsMessage((1 << i)))
            time.sleep(0.5)
            self.send_message(SetLEDsMessage(0))
            time.sleep(0.5)

    def close(self):
        self.running = False

        if self.con and self.con.isOpen():
            self.con.close()

        self.output_queue.put(None)
        self.listener_thread.join()

    def run_local_audio_mode(self):
        
        import simpleaudio

        audio = simpleaudio.WaveObject.from_wave_file(self.audio_file)
        audio_replay = None

        self.print_fn("Comb: Running in audio-only mode...")

        while self.running:

            message = self.output_queue.get()
            if message is None or not self.running or not message.is_activation_message():
                continue
            
            is_still_playing = (audio_replay is not None) and (audio_replay.is_playing())
            action = "playing_sound"
            if is_still_playing:
                action = "continuing_last_sound"
            
            self.print_fn("{} - {}".format(str(message), action))
            self.log_fn(action, file=self.audio_file)

            if not is_still_playing:
                try:
                    audio_replay = audio.play()
                except Exception as e:
                    self.print_fn("Error when playing sound! {}: {}".format(type(e).__name__, str(e)))

    def process_queue_for_serial_connection(self):
        assert self.dummy_mode or self.con.isOpen()

        while self.running:

            message = self.output_queue.get()
            if message is None or not self.running:
                break

            if self.con is not None and not self.con.isOpen():
                self.print_fn("Comb: Serial connection broken. Message dropped.")
                break
            self._send_serial_message(message)

    def run_connector(self):

        while self.running:

            self.print_fn("Comb: Waiting for serial connection...")
            while self.running and (self.dummy_mode or not self.con.isOpen()):
                if not self.dummy_mode:
                    self.con.open()
                time.sleep(1.0)

            if not self.running:
                return

            self.print_fn("Comb: Opened serial connection.")
            self.process_queue_for_serial_connection()
            

    def send_message(self, message):
        self.output_queue.put(message)

    def _send_serial_message(self, message):

        # Potentially schedule deactivation.
        def schedule_deactivation(delay, deactivation_message):
            time.sleep(delay)
            self.output_queue.put(deactivation_message)

        def message_to_actuator_label(message):

            selected_actuator_index = message.get_actuator_index()
            selected_actuators = self.actuators
            actuator_label = "all actuators"
            if selected_actuator_index is not None:
                if not isinstance(selected_actuator_index, list):
                    selected_actuator_index = [selected_actuator_index]
                selected_actuators = [selected_actuators[i] for i in selected_actuator_index]
                actuator_label = "actuator {}".format("+".join(map(str, selected_actuator_index)))

            return selected_actuators, actuator_label

        if message.is_activation_message():

            delay, deactivation_message = message.get_deactivation_message()

            if deactivation_message is not None:
                selected_actuators, actuator_label = message_to_actuator_label(message)

                all_are_active = all((a.is_active() for a in selected_actuators))
                for actuator in selected_actuators:
                    actuator.set_active_for(delay)

                scheduling_thread = threading.Thread(
                    target=schedule_deactivation,
                    args=(delay, deactivation_message),
                    kwargs=dict(),
                )
                scheduling_thread.start()

                if all_are_active:
                    self.print_fn("Holding {} for {:3.2f} s more".format(actuator_label, delay))
                    return

                self.print_fn("Triggering {} for {:3.2f} s".format(actuator_label, delay))

        elif message.is_deactivation_message():
            # Only deactivate if no other message activated it in the meantime.
            selected_actuators, actuator_label = message_to_actuator_label(message)
            for actuator in selected_actuators:
                if actuator.is_active():
                    self.log_fn("Skipping actuator deactivation.")
                    return
            
        serial_messages = [message]

        while len(serial_messages) > 0:
            message = serial_messages.pop(0)

            # A message can recursively be made from other messages.
            if not isinstance(message, str):
                message = message.get_serial_message()

                if isinstance(message, str):
                    message = [message]

                serial_messages = message + serial_messages
                continue

            message = str(message).upper()

            self.log_fn(
                "serial message", text=message, character_delay=self.character_delay
            )

            message = message + "\n\r"

            for char in message:
                if self.con is not None:
                    self.con.write(char.encode("utf-8"))

                if self.character_delay:
                    time.sleep(self.character_delay)

    def is_actuator_active(self, actuator_index):
        return self.actuators[actuator_index].is_active()
