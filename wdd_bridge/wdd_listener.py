import datetime
import multiprocessing.connection
import queue
import threading

from .dance_detector import Waggle


class WDDListener:
    def __init__(self, port, authkey, print_fn, log_fn):

        self.listener = multiprocessing.connection.Listener(
            ("localhost", port), authkey=authkey.encode()
        )

        self.print_fn = print_fn
        self.log_fn = log_fn

        self.incoming_queue = queue.Queue()

        self.listener_thread = threading.Thread(target=self.run_listener, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def run_listener(self):

        self.running = True

        while self.running:
            self.print_fn("WDD: Waiting for connection...")
            try:
                con = self.listener.accept()
                self.print_fn(
                    "WDD: Accepted connection from {}".format(
                        self.listener.last_accepted
                    )
                )
            except Exception as e:
                self.print_fn("WDD: Error accepting new connection:")
                self.print_fn("WDD: " + str(e))
                continue

            while True:
                message = con.recv()
                if message == "close":
                    self.print_fn("WDD: Closing connection on request.")
                    con.close()
                    break
                if "timestamp_waggle" in message:
                    angle = None
                    if "waggle_angle" in message:
                        angle = message["waggle_angle"]
                    waggle = Waggle(
                        message["x"], message["y"], angle, message["timestamp_waggle"]
                    )
                    self.print_fn(
                        "WDD: received waggle detected {}s ago".format(
                            (
                                datetime.datetime.utcnow()
                                - message["system_timestamp_waggle"]
                            ).total_seconds()
                        )
                    )
                    self.incoming_queue.put(waggle)

    def close(self):
        self.running = False
        l = self.listener
        self.listener = None
        if l is not None:
            l.close()
        self.incoming_queue.put(None)
        # Don't join the listener thread here because it might be hanging on trying to get a connection.
        self.listener_thread.join()

    def get_message(self, block=True, timeout=None):

        try:
            return self.incoming_queue.get(block=block, timeout=timeout)
        except queue.Empty as e:
            pass

        return None
