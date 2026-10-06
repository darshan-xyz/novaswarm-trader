"""Allow running ``python -m novaswarm`` to start the CLI."""

from novaswarm.cli.main import app

if __name__ == "__main__":
    app()
