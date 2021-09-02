import astropy
import datetime
import pytz
import queue
import threading
import time

class AzimuthUpdater:
    """Frequently retrieves the current azimuth in a background thread.
    """

    def __init__(self, latitude, longitude, update_frequency=60.0):

        self.latitude = latitude
        self.longitude = longitude
        self.update_frequency = update_frequency

        self.update_queue = queue.Queue()
        self.latest_azimuth = None

        self.running = True

        self.listener_thread = threading.Thread(target=self.update_azimuth, args=())
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def calculate_current_azimuth(self):

        import astropy.coordinates 
        import astropy.units as u
        import astropy.time

        current_time = datetime.datetime.now()

        earth_loc = astropy.coordinates.EarthLocation(lat=self.latitude*u.deg, lon=self.longitude*u.deg, height=0*u.m)
    
        current_time = astropy.time.Time(current_time.astimezone(pytz.UTC), scale="utc")
        sun_loc = astropy.coordinates.get_sun(current_time)
        azimuth_rad = sun_loc.transform_to(astropy.coordinates.AltAz(obstime=time, location=earth_loc)).az

        # azimuth_rad is now at N0, E90

        # to N0, E-90
        azimuth_rad = -azimuth_rad
        # to N90, E0
        azimuth_rad = azimuth_rad + np.pi / 2.0

        return azimuth_rad

    def update_azimuth(self):

        while self.running:
            updated_azimuth = self.calculate_current_azimuth()
            self.update_queue.put(updated_azimuth)

            time.sleep(self.update_frequency)

    def get_azimuth(self):

        # Fetch latest update.
        while self.update_queue.full():
            update = self.update_queue.get()
            self.latest_azimuth = update

        # If, for some reason, the azimuth is requested immediately, just wait a bit.
        if self.latest_azimuth is None:
            update = self.update_queue.get()
            self.latest_azimuth = update

        return self.latest_azimuth

    def close(self):
        self.running = False
