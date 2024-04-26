# -*- coding: utf-8 -*-
"""Utilities for the structure selection."""
# pylint: disable=redefined-builtin, unsubscriptable-object
from __future__ import annotations

from aiida import orm


def find_better_duplicates(flag_dict, structure):
    """Find better duplicates for a structure, if any."""

    def get_ok_duplicates(structure, bad_flags):
        duplicate_list = []

        for duplicate in structure.extras["duplicates"]:
            duplicate_db, _, duplicate_id = duplicate.split("|")
            try:
                data = flag_dict[duplicate_db][duplicate_id]
                if all(not bad for bad in [data[flag] for flag in bad_flags]):
                    duplicate_list.append(f"{duplicate_db}|{duplicate_id}")
            except KeyError:
                pass

        return duplicate_list

    source_db = structure.extras["source"]["database"]
    source_id = structure.extras["source"]["id"]

    try:
        struc_df = flag_dict[source_db][source_id]
    except KeyError:
        return

    if any(
        (
            struc_df["is_theoretical"],
            struc_df["is_high_pressure"],
            struc_df["is_high_temperature"],
        )
    ):
        better_duplicates = get_ok_duplicates(
            structure, ["is_theoretical", "is_high_pressure", "is_high_temperature"]
        )
        if better_duplicates:
            return better_duplicates


def replace_structure(replacement, unique_group):
    """Replace a structure with a better duplicate in the `unique_group` group."""

    structure, better_duplicates = replacement

    chosen_replacement = None

    for database in ["cod", "icsd", "mpds"]:
        for duplicate in better_duplicates:
            if duplicate.startswith(database) and chosen_replacement is None:
                chosen_replacement = duplicate

    replacement_db, replacement_id = chosen_replacement.split("|")

    query = orm.QueryBuilder()

    replacement_structure = query.append(
        orm.StructureData,
        filters={
            "and": [
                {"extras.source.database": replacement_db},
                {"extras.source.id": replacement_id},
            ]
        },
    ).first()[0]

    structure_source = "|".join(
        [
            structure.extras["source"]["database"],
            structure.extras["source"]["version"],
            structure.extras["source"]["id"],
        ]
    )

    replacement_source = "|".join(
        [
            replacement_structure.extras["source"]["database"],
            replacement_structure.extras["source"]["version"],
            replacement_structure.extras["source"]["id"],
        ]
    )

    duplicates_set = set(structure.extras["duplicates"])

    assert (
        structure_source not in duplicates_set
    ), f"Found the orignal source {structure_source} in the duplicates: {duplicates_set}"

    assert (
        replacement_source in duplicates_set
    ), f"Did not find the replacement source {replacement_source} in the duplicates: {duplicates_set}"

    duplicates_set.remove(replacement_source)
    duplicates_set.add(structure_source)

    replacement_structure.base.extras.set("duplicates", list(duplicates_set))
    structure.base.extras.delete("duplicates")

    unique_group.backend_entity.add_nodes(
        [
            replacement_structure.backend_entity,
        ],
        skip_orm=True,
    )
    unique_group.backend_entity.remove_nodes(
        [
            structure.backend_entity,
        ],
        skip_orm=True,
    )
