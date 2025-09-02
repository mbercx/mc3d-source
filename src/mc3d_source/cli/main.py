"""Top level of the `mc3d-source` CLI."""

import typer

from mc3d_source.cli.commands.curate import main as curate_main
class OrderedGroup(typer.main.TyperGroup):
    def list_commands(self, _):
        return [
            "curate",
        ]


app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
    cls=OrderedGroup
)
app.command("curate")(curate_main)


@app.callback()
def callback():
    """
    Tool for importing CIF files and converting them into a unique set of `StructureData`.
    """
