"""Top level of the `mc3d-source` CLI."""

import typer

from mc3d_source.cli.commands.analyse.deprecation import id_removed, incorrect_formula, structure_updated
from mc3d_source.cli.commands.cif_import import main as import_main
from mc3d_source.cli.commands.curate import main as curate_main
from mc3d_source.cli.commands.uniq import main as uniq_main
from mc3d_source.cli.commands.update import main as update_main


class OrderedGroup(typer.main.TyperGroup):
    def list_commands(self, _):
        return ["import", "curate", "update", "uniq"]


app = typer.Typer(pretty_exceptions_show_locals=False, rich_markup_mode="rich", cls=OrderedGroup)
app.command("import")(import_main)
app.command("curate")(curate_main)
app.command("update")(update_main)
app.command("uniq")(uniq_main)

analyse_app = typer.Typer()
analyse_app.command()(id_removed)
analyse_app.command()(structure_updated)
analyse_app.command()(incorrect_formula)

app.add_typer(analyse_app, name="analyse")


@app.callback()
def callback():
    """
    Tool for importing CIF files and converting them into a unique set of `StructureData`.
    """
