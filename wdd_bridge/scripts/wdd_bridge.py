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
    "--comb-port", default="/dev/ttyUSB0", help="Serial port to connect to the comb."
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
    "--signal-duration",
    default=1.0,
    type=float,
    help="Duration of the signal in seconds.",
)
def main(**kwargs):

    print("Initializing bridge..", flush=True)

    bridge = Bridge(**kwargs)

    print("Starting bridge..", flush=True)
    bridge.run()


if __name__ == "__main__":
    main()
