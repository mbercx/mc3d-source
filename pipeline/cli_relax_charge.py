#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI for the MC3D relax pipeline."""
from pathlib import Path
from time import sleep
from aiida import orm
from aiida.cmdline.utils.decorators import with_dbenv

from aiida_quantumespresso.workflows.pw.base import PwBaseWorkChain
from aiida_quantumespresso.common.types import ElectronicType, SpinType
from aiida_submission_controller.from_group import FromGroupSubmissionController

import yaml
import typer


class ChargeSubmissionController(FromGroupSubmissionController):
    """
    Controller class for submitting charge calculations.
    """

    pw_code: str
    overrides: dict = {}

    def get_inputs_and_processclass_from_extras(self, extras_values):
        """
        Get inputs and process class from extras values.

        Args:
            extras_values (dict): Dictionary of extra values.

        Returns:
            builder (PwBaseWorkChain): Builder for the scf.
        """
        parent_node = self.get_parent_node_from_extras(extras_values)

        if not isinstance(parent_node, orm.StructureData):
            raise ValueError("The parent node is not a StructureData node.")

        builder = PwBaseWorkChain.get_builder_from_protocol(
            code=orm.load_code(self.pw_code),
            structure=parent_node,
            overrides=self.overrides,
            electronic_type=ElectronicType.METAL,
            spin_type=SpinType.COLLINEAR)

        return builder
    
    
@with_dbenv()
def cli(
    settings_charge: Path
):
    """Command line interface for the MC3D relax pipeline."""

    with settings_charge.open("r") as handle:
        settings_dict = yaml.safe_load(handle)
    
    submission_controller = ChargeSubmissionController(
        unique_extra_keys=["source.database", "source.id"],
        max_concurrent=settings_dict["max_concurrent"],
        parent_group_label=settings_dict["parent_group"],
        group_label=settings_dict["relax_group"],
        pw_code=settings_dict["pw_code"],
        overrides=settings_dict["overrides"],
        filters={
            'extras.number_of_sites': {
                '<=': settings_dict["max_structure_size"],
                '>': 5  # 5 sites is the minimum size
            }
        },
        order_by={orm.Node: {'extras.number_of_sites': {'order': 'desc', 'cast': 'i'}}}
    )
    
    while True:
        submission_controller.submit_new_batch(verbose=True)

        sleep(30)

if __name__ == "__main__":
    typer.run(cli)


## Notes 

