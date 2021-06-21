import datetime
import json
import queue
import secrets
import threading


class Statistics:
    def __init__(self, filename):

        self.filename = filename
        self.queue = queue.Queue()

        self.running = True
        self.token = secrets.token_urlsafe()

        self.filename = filename

        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = False  # No daemon, so writing is not cut off.
        self.thread.start()

    def log(self, message, payload=None, **kwargs):

        if payload is None:
            payload = dict()

        for n, v in kwargs.items():
            payload[n] = v

        payload["message"] = message
        payload["log_timestamp"] = datetime.datetime.utcnow()
        payload["token"] = self.token

        self.queue.put(payload)

    def close(self):
        self.running = False
        self.queue.put(None)
        self.thread.join()

    def run(self):
        while self.running:
            data = self.queue.get()

            if data is None:
                continue

            for k, v in data.items():
                if isinstance(v, datetime.datetime) or isinstance(v, datetime.date):
                    data[k] = v.isoformat()

            buffer = json.dumps(data)

            filename = self.filename
            if "<date>" in filename:
                filename = filename.replace(
                    "<date>", datetime.datetime.utcnow().date().isoformat()
                )

            with open(filename, "a") as f:
                f.write(buffer + "\n")
