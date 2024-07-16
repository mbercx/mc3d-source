#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI for the MC3D relax pipeline."""
from pathlib import Path
from time import sleep
from aiida import orm
from aiida.cmdline.utils.decorators import with_dbenv

from aiida_quantumespresso.workflows.pw.relax import PwRelaxWorkChain
from aiida_quantumespresso.common.types import ElectronicType, SpinType, RelaxType
from aiida_submission_controller.from_group import FromGroupSubmissionController

import yaml
import typer


class RelaxSubmissionController(FromGroupSubmissionController):
    """Submission controller for the MC3D relax pipeline."""

    pw_code: str
    overrides: dict = {}

    def get_inputs_and_processclass_from_extras(self, extras_values):
        parent_node = self.get_parent_node_from_extras(extras_values)

        if not isinstance(parent_node, orm.StructureData):
            raise ValueError("The parent node is not a StructureData node.")

        #if any(coord > 1 for site in parent_node.get_pymatgen().sites for coord in site.frac_coords):
        #    raise ValueError("Not all sites are in the unit cell.")

        builder = PwRelaxWorkChain.get_builder_from_protocol(
            code=orm.load_code(self.pw_code),
            structure=parent_node,
            overrides=self.overrides,
            relax_type=RelaxType.POSITIONS_CELL,
            electronic_type=ElectronicType.METAL,
            spin_type=SpinType.COLLINEAR,
        )
        return builder
    
    

@with_dbenv()
def cli(
    settings: Path
):
    """Command line interface for the MC3D relax pipeline."""

    with settings.open("r") as handle:
        settings_dict = yaml.safe_load(handle)

    submission_controller = RelaxSubmissionController(
        unique_extra_keys=["source.database", "source.id"],
        max_concurrent=settings_dict["max_concurrent"],
        parent_group_label=settings_dict["parent_group"],
        group_label=settings_dict["relax_group"],
        pw_code=settings_dict["pw_code"],
        overrides=settings_dict["overrides"],
        filters={
            'extras.number_of_sites': {
                '<=': settings_dict["max_structure_size"],
                '>': 10  # 10 sites is the minimum size
            }
        },
        order_by={orm.Node: {'extras.number_of_sites': {'order': 'desc', 'cast': 'i'}}}
    )
    while True:
        submission_controller.submit_new_batch(verbose=True)
        sleep(30)

if __name__ == "__main__":
    typer.run(cli)
