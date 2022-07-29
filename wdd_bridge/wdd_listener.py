import datetime
import multiprocessing.connection
import pytz
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

        def is_datetime_timezone_aware(dt):
            return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None

        while self.running:
            has_active_connection = False
            for i in range(len(self.connections)):
                con = self.connections[i]
                if not con.poll():
                    continue

                has_active_connection = True
                message = con.recv()
                if message == "close":
                    self.print_fn("WDD: Closing connection {} on request.".format(i))
                    con.close()
                    del self.connections[i]
                    break

                if "timestamp_waggle" in message:
                    angle = None
                    duration = None
                    cam_id = message["cam_id"]
                    if "waggle_angle" in message:
                        angle = message["waggle_angle"]
                        duration = message["waggle_duration"]
                    waggle_timestamp = message["timestamp_waggle"]
                    
                    if not is_datetime_timezone_aware(waggle_timestamp):
                        waggle_timestamp = pytz.UTC.localize(waggle_timestamp)
                    else:
                        assert int(waggle_timestamp.utcoffset().total_seconds()) == 0
                        
                    waggle = Waggle(
                        message["x"], message["y"], angle, duration, waggle_timestamp, cam_id, uuid=message["waggle_id"]
                    )
                    self.print_fn(
                        "WDD: received waggle detected {:4.3f}s ago (cam: '{}', con. {})".format(
                            (
                                datetime.datetime.utcnow()
                                - message["system_timestamp_waggle"]
                            ).total_seconds(),
                            cam_id, i
                        ),
                        cam_id=cam_id, waggle_timestamp=waggle.timestamp, waggle_angle=angle, waggle_id=waggle.uuid
                    )
                    self.incoming_queue.put(waggle)
                else:
                    self.print_fn("WDD: received invalid message ({}).".format(str(message)))
            
            if not has_active_connection:
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
