"""
Command-line interface for the FileMan browser.

Commands:
    fm-browser inventory          File + package inventory from ^DIC
    fm-browser files              List all FileMan files
    fm-browser fields <file#>     Show fields for a file
    fm-browser data <file#>       Show entries from a file
    fm-browser export-dd          Export full data dictionary to output/
    fm-browser export-file <file#> Export file data to output/
    fm-browser serve              Start the web browser UI
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .connection import YdbConnection
from .data_dictionary import DataDictionary
from .exporter import DEFAULT_OUTPUT, Exporter
from .file_reader import FileReader
from .inventory import FileInventory

console = Console()
log = logging.getLogger(__name__)


def _get_conn_dd_reader() -> tuple[YdbConnection, DataDictionary, FileReader]:
    """Open YottaDB connection and return (conn, dd, reader)."""
    conn = YdbConnection.connect()
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    return conn, dd, reader


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(debug: bool) -> None:
    """VA FileMan Browser — inspect and export VistA FileMan data."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@main.command("files")
@click.option("--search", "-s", default="", help="Filter by name (case-insensitive)")
def cmd_files(search: str) -> None:
    """List all FileMan files."""
    conn, dd, _ = _get_conn_dd_reader()
    with conn:
        files = dd.search_files(search) if search else dd.list_files()

    table = Table(title=f"FileMan Files ({len(files)} found)")
    table.add_column("File #", style="cyan", justify="right")
    table.add_column("Label", style="white")

    for file_num, label in files:
        table.add_row(str(file_num), label)

    console.print(table)


@main.command("fields")
@click.argument("file_number", type=float)
def cmd_fields(file_number: float) -> None:
    """Show fields for a FileMan file."""
    conn, dd, _ = _get_conn_dd_reader()
    with conn:
        file_def = dd.get_file(file_number)

    if file_def is None:
        console.print(f"[red]File {file_number} not found[/red]")
        sys.exit(1)

    table = Table(
        title=f"File {file_number}: {file_def.label}  ({file_def.global_root})"
    )
    table.add_column("Field #", style="cyan", justify="right")
    table.add_column("Label", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Title", style="dim")

    for fld in sorted(file_def.fields.values(), key=lambda f: f.field_number):
        table.add_row(
            str(fld.field_number),
            fld.label,
            fld.datatype_name,
            fld.title[:60],
        )

    console.print(table)


@main.command("data")
@click.argument("file_number", type=float)
@click.option(
    "--limit", "-n", default=20, show_default=True, help="Max entries to show"
)
def cmd_data(file_number: float, limit: int) -> None:
    """Show data entries from a FileMan file."""
    conn, dd, reader = _get_conn_dd_reader()
    with conn:
        file_def = dd.get_file(file_number)
        if file_def is None:
            console.print(f"[red]File {file_number} not found[/red]")
            sys.exit(1)
        entries = list(reader.iter_entries(file_number, limit=limit))

    table = Table(
        title=f"File {file_number}: {file_def.label}  (first {limit} entries)"
    )
    table.add_column("IEN", style="cyan", justify="right")
    table.add_column("Zero-node (raw)", style="white", no_wrap=False, max_width=80)

    for entry in entries:
        table.add_row(entry.ien, entry.raw_nodes.get("0", ""))

    console.print(table)


@main.command("export-dd")
@click.option(
    "--output",
    "-o",
    default=str(DEFAULT_OUTPUT),
    show_default=True,
    help="Output directory",
)
def cmd_export_dd(output: str) -> None:
    """Export full data dictionary to JSON and CSV."""
    conn, dd, reader = _get_conn_dd_reader()
    out_dir = Path(output)
    with conn:
        exp = Exporter(dd, reader, output_dir=out_dir)
        exp.export_data_dictionary()
        exp.export_summary()
    console.print(f"[green]Data dictionary exported to {out_dir}[/green]")


@main.command("export-file")
@click.argument("file_number", type=float)
@click.option(
    "--limit", "-n", default=None, type=int, help="Max entries (default: all)"
)
@click.option(
    "--output",
    "-o",
    default=str(DEFAULT_OUTPUT),
    show_default=True,
    help="Output directory",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of CSV")
def cmd_export_file(
    file_number: float, limit: int | None, output: str, as_json: bool
) -> None:
    """Export all data from a FileMan file to CSV or JSON."""
    conn, dd, reader = _get_conn_dd_reader()
    out_dir = Path(output)
    with conn:
        exp = Exporter(dd, reader, output_dir=out_dir)
        if as_json:
            out = exp.export_file_json(file_number, limit=limit)
        else:
            out = exp.export_file(file_number, limit=limit)
    console.print(f"[green]Exported to {out}[/green]")


@main.command("inventory")
@click.option(
    "--output",
    "-o",
    default=str(DEFAULT_OUTPUT),
    show_default=True,
    help="Output directory for inventory.json",
)
@click.option("--json", "as_json", is_flag=True, help="Also write inventory.json")
@click.option(
    "--package",
    "-p",
    default="",
    help="Filter display to one package prefix (e.g. LR, PS, DG)",
)
def cmd_inventory(output: str, as_json: bool, package: str) -> None:
    """Show a file + package inventory from ^DIC.

    Lists every FileMan file grouped by VistA package, with field counts.
    Use --json to write the full inventory to inventory.json for offline analysis.
    """
    conn = YdbConnection.connect()
    with conn:
        fi = FileInventory(conn)
        fi.load()

    s = fi.summary()
    console.print(
        f"\n[bold]FileMan Inventory[/bold]  "
        f"[cyan]{s['total_files']}[/cyan] files  "
        f"[cyan]{s['total_packages']}[/cyan] packages  "
        f"[dim]({s['unpackaged_files']} unpackaged)[/dim]\n"
    )

    # Package summary table
    pkg_table = Table(title="Top Packages by File Count", show_lines=False)
    pkg_table.add_column("Package", style="white")
    pkg_table.add_column("Prefix", style="cyan", justify="center")
    pkg_table.add_column("Files", style="yellow", justify="right")
    for row in s["top_packages_by_file_count"][:30]:
        pkg_table.add_row(row["name"], "", str(row["file_count"]))

    # Rebuild table with prefix column (prefix not in summary dict)
    pkg_by_name = {p.name: p for p in fi.list_packages()}
    pkg_table = Table(title="Top Packages by File Count", show_lines=False)
    pkg_table.add_column("Package", style="white")
    pkg_table.add_column("Prefix", style="cyan", justify="center")
    pkg_table.add_column("Files", style="yellow", justify="right")
    for row in s["top_packages_by_file_count"][:30]:
        pkg = pkg_by_name.get(row["name"])
        prefix = pkg.prefix if pkg else ""
        pkg_table.add_row(row["name"], prefix, str(row["file_count"]))
    console.print(pkg_table)

    # Optional: detailed file list filtered by package prefix
    if package:
        grouped = fi.files_by_package()
        matched = {
            name: files
            for name, files in grouped.items()
            if any(
                p.prefix.upper() == package.upper()
                for p in fi.list_packages()
                if p.name == name
            )
        }
        if not matched:
            console.print(f"[red]No package with prefix '{package}' found[/red]")
        else:
            for pkg_name, files in matched.items():
                title = f"{pkg_name} ({package.upper()}) — {len(files)} files"
                file_table = Table(title=title)
                file_table.add_column("File #", style="cyan", justify="right")
                file_table.add_column("Label", style="white")
                file_table.add_column("Global", style="dim")
                file_table.add_column("Fields", style="yellow", justify="right")
                for fr in files:
                    file_table.add_row(
                        str(fr.file_number),
                        fr.label,
                        fr.global_root,
                        str(fr.field_count),
                    )
                console.print(file_table)

    if as_json:
        out = fi.export_json(Path(output))
        console.print(f"[green]Inventory written to {out}[/green]")


@main.command("serve")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=5000, show_default=True)
@click.option("--debug", "flask_debug", is_flag=True)
def cmd_serve(host: str, port: int, flask_debug: bool) -> None:
    """Start the web FileMan browser UI."""
    from .web.app import create_app  # noqa: PLC0415

    conn = YdbConnection.connect()
    dd = DataDictionary(conn)
    reader = FileReader(conn, dd)
    app = create_app(dd, reader)
    console.print(f"[green]FileMan browser running at http://{host}:{port}[/green]")
    app.run(host=host, port=port, debug=flask_debug)
