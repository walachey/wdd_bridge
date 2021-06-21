from distutils.core import setup


def parse_requirements(filename):
    with open(filename, "r") as file:
        lines = (line.strip() for line in file)
        return [line for line in lines if line and not line.startswith("#")]


reqs = parse_requirements("requirements.txt")

setup(
    name="wdd_bridge",
    version="0.1.0",
    description="",
    entry_points={
        "console_scripts": [
            "wdd_bridge = wdd_bridge.scripts.wdd_bridge:main",
        ]
    },
    install_requires=reqs,
    packages=[
        "wdd_bridge",
        "wdd_bridge.scripts",
    ],
)
