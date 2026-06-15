"""argus — browser-native market-data harvester CLI."""

import typer

app = typer.Typer(help="Argus: browser-native market-data harvester.")


@app.command()
def profile(url: str, pillar: str = "news", id: str = "") -> None:
    """Profile a URL: run Cartographer, classify tier, draft a Source Card."""
    typer.echo(f"[stub] profile {url} pillar={pillar} id={id}")


@app.command()
def cartograph(
    url: str,
    pillar: str = typer.Option("news"),
    id: str = typer.Option(""),
    hint_clicks: str = typer.Option("", help="Comma-separated tab labels to click"),
) -> None:
    """Map all data endpoints a site uses; emit draft Source Card."""
    typer.echo(f"[stub] cartograph {url}")


@app.command()
def fingerprint(backend: str = "vanilla") -> None:
    """Run the Fingerprint Lab for the given stealth backend."""
    typer.echo(f"[stub] fingerprint backend={backend}")


@app.command()
def harvest(
    pillar: str = typer.Argument(..., help="news | coinglass | calendar"),
    source: str = typer.Option("", help="Specific source id (all if omitted)"),
    since: str = typer.Option("", help="ISO datetime lower bound"),
) -> None:
    """Harvest one or all sources for a pillar."""
    typer.echo(f"[stub] harvest pillar={pillar} source={source}")


@app.command()
def fuse(
    since: str = typer.Option("", help="ISO datetime lower bound"),
    window: str = typer.Option("30s,5m,1h", help="Return windows"),
) -> None:
    """Join event tapes to price tape → ReactionRow dataset."""
    typer.echo(f"[stub] fuse since={since} window={window}")


@app.command()
def report() -> None:
    """Build the Harvest Report (site/index.html)."""
    typer.echo("[stub] report")


if __name__ == "__main__":
    app()
