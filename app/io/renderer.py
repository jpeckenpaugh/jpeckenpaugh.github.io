import os


class Renderer:
    def clear(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def render_text(self, frame: str) -> None:
        self.clear()
        print(frame)