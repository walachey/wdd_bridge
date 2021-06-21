import queue
import serial
import time
import threading


class CombConnector:
    def __init__(self, port, print_fn):

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

        self.output_queue = queue.Queue()

        self.listener_thread = threading.Thread(target=self.run_connector, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def close(self):
        self.running = False

        if self.con and self.con.isOpen():
            self.con.close()

        self.listener_thread.join()

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

                if not self.con.isOpen():
                    self.print_fn("Comb: Serial connection broken. Message dropped.")
                    break

                self.con.write(message)

    def send_message(self, message):
        self.output_queue.put(message)
