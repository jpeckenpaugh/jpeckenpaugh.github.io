"""Launcher for the open-world story sprint prototype.

Temporary correction: keep the visible baseline on the real travel_v01 renderer
while the clean world_story package is refit around that visual pipeline.
"""

from travel_v01 import main as travel_main


def main() -> None:
    travel_main(world_story_mode=True)


if __name__ == "__main__":
    main()
