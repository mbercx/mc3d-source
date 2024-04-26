# -*- coding: utf-8 -*-
"""Top-level of the aiida_sdb CLI."""
import typer

from . import run

app = typer.Typer(pretty_exceptions_show_locals=False)
app.add_typer(run.app, name="run")


@app.callback()
def callback():
    """
    Tool for importing CIF files and converting them into a unique set of `StructureData`.
    """
