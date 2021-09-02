import datetime
import multiprocessing.connection
import queue
import threading
import time

from .dance_detector import Waggle


class WDDListener:
    def __init__(self, port, authkey, print_fn, log_fn):

        self.listener = multiprocessing.connection.Listener(
            ("localhost", port), authkey=authkey.encode()
        )

        self.print_fn = print_fn
        self.log_fn = log_fn

        self.incoming_queue = queue.Queue()
        self.connections = []  # Note that access to lists is generally thread-safe.

        self.running = True

        self.listener_thread = threading.Thread(target=self.run_listener, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

        self.receiving_thread = threading.Thread(target=self.run_receivers, args=())
        self.receiving_thread.daemon = True
        self.receiving_thread.start()

    def run_listener(self):

        while self.running:
            self.print_fn("WDD: Waiting for connection...")
            try:
                con = self.listener.accept()
                self.print_fn(
                    "WDD: Accepted connection {} from {}".format(
                        len(self.connections), self.listener.last_accepted
                    )
                )
                self.connections.append(con)
            except Exception as e:
                self.print_fn("WDD: Error accepting new connection:")
                self.print_fn("WDD: " + str(e))
                continue

    def run_receivers(self):

        while self.running:
            for i in range(len(self.connections)):
                con = self.connections[i]
                if not con.poll():
                    continue

                message = con.recv()
                if message == "close":
                    self.print_fn("WDD: Closing connection {} on request.".format(i))
                    con.close()
                    del self.connections[i]
                    break

                if "timestamp_waggle" in message:
                    angle = None
                    cam_id = message["cam_id"]
                    if "waggle_angle" in message:
                        angle = message["waggle_angle"]
                    waggle = Waggle(
                        message["x"], message["y"], angle, message["timestamp_waggle"], cam_id
                    )
                    self.print_fn(
                        "WDD: received waggle detected {}s ago (on connection {}, cam id: '{}')".format(
                            (
                                datetime.datetime.utcnow()
                                - message["system_timestamp_waggle"]
                            ).total_seconds(),
                            i, cam_id
                        )
                    )
                    self.incoming_queue.put(waggle)
            else:  # If no connections are there yet.
                time.sleep(1.0)

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
