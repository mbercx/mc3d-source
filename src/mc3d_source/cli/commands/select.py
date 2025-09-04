"""Select the structures for the MC3D-source."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aiida import load_profile, orm
from pymatgen.core import Composition
from rich import print as rprint

from mc3d_source.tools.source import get_source_string, get_source_structure_dict

if TYPE_CHECKING:
    from pathlib import Path


load_profile("prod")


def main(
    unique_families_path: Path,
    mc3d_id_file: Path,
    deprecation_path: Path,
    selected_path: Path | None = "selected-families.json",
    new_mc3d_data: Path | None = "new-mc3d-data.json",
    new_uniques_group: str | None = "global/uniques/new",
):
    with mc3d_id_file.open("r") as handle:
        mc3d_id_data = json.load(handle)

    with unique_families_path.open("r") as handle:
        new_unique_families = json.load(handle)

    source_to_new_family_index = {}

    for family_index, family in enumerate(new_unique_families):
        for source in family:
            source_to_new_family_index[source] = family_index

    with deprecation_path.open("r") as handle:
        source_to_issue = json.load(handle)

    # Make sure the new family sources have no issues
    if not all(source not in source_to_new_family_index for source in source_to_issue):
        rprint("FAILURE")

    # We need to know all sources that correspond to COD structures with H
    query = orm.QueryBuilder()
    query.append(
        orm.StructureData,
        filters={
            "and": [
                {"extras.source.database": "cod"},
                {"extras.partial_occupancies": False},
                {"extras.chemical_system": {"like": "%-H-%"}},
            ]
        },
        project="extras.source",
    )

    cod_h_sources = {get_source_string(source) for source in query.all(flat=True)}

    # Find a mapping of old MC3D ids to families: these families we can skip
    mc3d_id_to_family_ids = {}

    golden_sources = set()
    mc3d_id_family_deprecated = {}
    other_deprecated_ids = {}

    for mc3d_id, data in mc3d_id_data.items():
        source_string = get_source_string(data["golden_structure"]["source"])
        golden_sources.add(source_string)

        # Get the previous family for the MC3D-source
        previous_family = data["duplicate_family"]

        # Find all the new family IDs that correspond to the corresponding sources in the previous family
        previous_family_ids = {
            source_to_new_family_index[source] for source in previous_family if source in source_to_new_family_index
        }
        if previous_family_ids:
            mc3d_id_to_family_ids[mc3d_id] = list(previous_family_ids)
            continue

        # If all the source in the previous family have an issue, we need to deprecate that MC3D ID
        if all(source in source_to_issue for source in previous_family):
            mc3d_id_family_deprecated[mc3d_id] = data
            continue

        other_deprecated_ids[mc3d_id] = source_string

    rprint(f"Number of MC3D IDs corresponding to a new family: {len(mc3d_id_to_family_ids)}")
    rprint(f"Number of MC3D IDs whose previous family is entirely deprecated: {len(mc3d_id_family_deprecated)}")

    rprint(f"Other MC3D IDs that no longer have a family: {len(other_deprecated_ids)}")

    all_mc3d_family_ids = set()

    for family_id_list in mc3d_id_to_family_ids.values():
        if len(family_id_list) == 1:
            all_mc3d_family_ids.add(family_id_list[0])
        else:
            # If there are multiple new families, we have to create new ones.
            # We skip any families that have a "golden" source in them.
            for family_id in family_id_list:
                if set(new_unique_families[family_id]) & golden_sources:
                    continue
                all_mc3d_family_ids.add(family_id)

    new_familes = []

    for family_index, family in enumerate(new_unique_families):
        if family_index in all_mc3d_family_ids:
            continue  # Already in MC3D

        if set(family).issubset(cod_h_sources):
            continue  # All structures are COD-H structures

        new_familes.append(family)

    rprint(f"Found {len(new_familes)} new families.")

    with selected_path.open("w") as handle:
        handle.write(json.dumps(new_familes, indent=4))

    # Time to select our golden structures
    new_golden_sources = set()
    new_golden_sources_dict = {}

    for family in new_familes:
        cod_sources = [source for source in family if source.startswith("cod|")]
        icsd_sources = [source for source in family if source.startswith("icsd|")]
        mpds_sources = [source for source in family if source.startswith("mpds|")]

        selection = None

        # Prioritize by permissions
        if cod_sources:
            selection = cod_sources[0]
        if icsd_sources:
            selection = icsd_sources[0]
        if mpds_sources:
            selection = mpds_sources[0]

        if selection is None:
            rprint("FAILURE")

        new_golden_sources.add(selection)

        database, version, source_id = selection.split("|")

        new_golden_sources_dict[selection] = {
            "duplicate_family": family,
            "golden_structure": {
                "source": {"database": database, "id": version, "version": source_id},
            },
        }

    rprint("Grabbing the `StructureData`.")
    source_to_structure = get_source_structure_dict(new_golden_sources)

    unique_structures = []

    with query.backend.transaction():
        for golden_source, data in new_golden_sources_dict.items():
            structure = source_to_structure[golden_source]
            data["golden_structure"].update(
                {
                    "reduced_formula": Composition(structure.get_formula()).reduced_formula,
                    "spglib_space_group": structure.base.extras.get("spacegroup_number"),
                    "uuid": structure.uuid,
                }
            )
            structure.base.extras.set(
                "duplicates", [source for source in data["duplicate_family"] if source != golden_source]
            )
            unique_structures.append(structure)

    with new_mc3d_data.open("w") as handle:
        handle.write(json.dumps(new_golden_sources_dict, indent=4))

    new_uniques_group, created = orm.Group.collection.get_or_create(new_uniques_group)

    if not created:
        rprint(f"Group `{new_uniques_group.label}` already exists!")
        return

    rprint(f"Group `{new_uniques_group.label}` created.")
    rprint("Adding nodes...")
    new_uniques_group.add_nodes(unique_structures)
