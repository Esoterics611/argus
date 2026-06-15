"""argus — browser-native market-data harvester CLI."""

import asyncio

import typer

app = typer.Typer(help="Argus: browser-native market-data harvester.")


@app.command()
def profile(url: str, pillar: str = "news", id: str = "") -> None:
    """Profile a URL: run Cartographer, classify tier, draft a Source Card."""
    source_id = id or url.split("//")[-1].split("/")[0].replace(".", "_")
    asyncio.run(_cartograph_async(url, pillar, source_id, []))


@app.command()
def cartograph(
    url: str,
    pillar: str = typer.Option("news"),
    id: str = typer.Option("", help="Source slug (derived from URL if omitted)"),
    hint_clicks: str = typer.Option("", help="Comma-separated tab labels to click"),
    backend: str = typer.Option("vanilla", help="Stealth backend"),
) -> None:
    """Map all data endpoints a site uses; emit cartograph.json + draft Source Card."""
    source_id = id or url.split("//")[-1].split("/")[0].replace(".", "_")
    hints = [h.strip() for h in hint_clicks.split(",") if h.strip()]
    asyncio.run(_cartograph_async(url, pillar, source_id, hints, backend=backend))


async def _cartograph_async(
    url: str, pillar: str, source_id: str, hints: list[str], backend: str = "vanilla"
) -> None:
    from argus.cartographer import Cartographer

    result = await Cartographer(
        url=url,
        pillar=pillar,
        source_id=source_id,
        stealth_backend=backend,
        hint_clicks=hints,
    ).run()
    typer.echo(f"\nRecommended tier: {result.recommended_tier}")
    typer.echo(f"Top data endpoints: {len(result.top_endpoints)}")
    for ep in result.top_endpoints[:5]:
        typer.echo(f"  [{ep.data_likelihood:.2f}] {ep.method} {ep.url[:90]}")
    if result.websockets:
        typer.echo(f"WebSockets: {len(result.websockets)}")
        for ws in result.websockets:
            typer.echo(f"  {ws.url[:90]}")
    typer.echo(f"\nSource card  → sources/{pillar}/{source_id}.yaml")
    typer.echo(f"Inventory    → sources/{pillar}/{source_id}.cartograph.json")
    typer.echo(f"Snippets     → sources/{pillar}/{source_id}.snippets.py")


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
