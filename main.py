import argparse

from config import DEFAULT_MODE
from ui.cli.cli_menu import run_cli
from ui.gui import AppGUI

def main() -> int:
    parser = argparse.ArgumentParser(description="競馬予想ツール")
    parser.add_argument("--mode", choices=["gui", "cli"], default=DEFAULT_MODE)
    args, remaining = parser.parse_known_args()

    if args.mode == "cli":
        return run_cli(remaining)

    app = AppGUI()
    app.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
