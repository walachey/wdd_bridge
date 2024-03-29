from wdd_bridge.bridge import Bridge

import click


@click.command()
@click.option(
    "--wdd-port", default=9901, help="Local port to listen on for WDD detections."
)
@click.option(
    "--wdd-authkey", required=True, help="Passphrase to authenticate connections."
)
@click.option(
    "--comb-port", default="/dev/ttyUSB0", help="Serial port to connect to the comb. Use local mode (i.e. just play sound) if the 'port' is a .wav file."
)
@click.option(
    "--comb-config",
    required=True,
    help="Path to filename that contains comb configuration.",
)
@click.option(
    "--draw-arrows",
    is_flag=True,
    help="Output arrows in the UI based on waggle direction.",
)
@click.option(
    "--stats-file",
    help="Filename to log advanced statistics to. Each line is a json object.",
)
@click.option(
    "--no-gui",
    help="Do not present a graphical user interface. Might be useful for debugging purposes.",
)
@click.option(
    "--use-soundboard",
    type=click.IntRange(0, 1),
    multiple=True,
    help="Soundboard to use in single or all-actuators mode. Can be passed multiple times to use both soundboards. Defaults to 0."
)
@click.option(
    "--sound-index",
    help="Number of the sound file on the sound board to play on suppression (0-10).",
    default=0,
    type=click.IntRange(0, 11)
)
@click.option(
    "--signal-index",
    help="Index of the signal to use for suppression (1-4). Corresponds to the 2 x 2 audio channels of the sound boards.",
    default=1,
    type=click.IntRange(1, 5)
)
@click.option(
    "--all-actuators",
    is_flag=True,
    help="Play signal on all actuators simultaneously.",
)
@click.option(
    "--hardwired-signals",
    is_flag=True,
    help="Assume signals (i.e. channels) have been hardwired to the actuators. Then 'soundboard_index' and 'sound_index' from the actuator's config will be used to control the playback.",
)
@click.option(
    "--only-one-signal",
    is_flag=True,
    help="Do not play another signal if any actuator is still active.",
)
@click.option(
    "--signal-duration",
    default=1.0,
    type=float,
    help="Duration of the signal in seconds.",
)
@click.option(
    "--waggle-max-distance",
    default=200.0,
    type=float,
    help="Maximum distance in pixels between successive waggles to be considered one dance.",
)
@click.option(
    "--waggle-max-gap",
    default=7.0,
    type=float,
    help="Maximum time between two successive waggles to be considered one dance.",
)
@click.option(
    "--waggle-min-count",
    default=3,
    type=click.IntRange(2),
    help="Minimum number of waggles in a dance with a similar angle to trigger a signal.",
)
def main(**kwargs):

    print("Initializing bridge..", flush=True)

    bridge = Bridge(**kwargs)

    print("Starting bridge..", flush=True)
    bridge.run()


if __name__ == "__main__":
    main()
