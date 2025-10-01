#!/usr/bin/env python
"""CLI for the MC3D relax pipeline."""

from pathlib import Path
from time import sleep

import typer
import yaml
from aiida.cmdline.utils.decorators import with_dbenv

from mc3d_source.controllers.cif_clean import CifCleanController


@with_dbenv()
def cli(settings_charge: Path):
    """Command line interface for the MC3D relax pipeline."""

    with settings_charge.open("r") as handle:
        settings_dict = yaml.safe_load(handle)

    submission_controller = CifCleanController(**settings_dict)

    while True:
        submission_controller.submit_new_batch(verbose=True)
        sleep(1)


if __name__ == "__main__":
    typer.run(cli)
