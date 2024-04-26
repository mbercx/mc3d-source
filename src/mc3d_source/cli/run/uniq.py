# -*- coding: utf-8 -*-
"""Utitilies for the uniqueness analysis."""
import click
import spglib
from aiida.tools.data.structure import structure_to_spglib_tuple
from numpy import eye, where
from rich.progress import Progress
from scipy.sparse.csgraph import connected_components


def get_spglib_spacegroup_symbol(structure, symprec=0.005):
    """Get the spacegroup symbol of a structure using spglib."""
    return spglib.get_symmetry_dataset(
        structure_to_spglib_tuple(structure)[0],
        symprec=symprec,
    )["international"]


def first_come_first_serve(ordered, matcher):
    """Perform a similarity analysis using the first-come-first-serve method."""

    global_unique_dict = {}

    with Progress() as progress:
        task = progress.add_task("Uniqueness analysis")
        advance = 100 / len(ordered)

        for key, data in ordered.items():
            progress.update(
                task, description=f"Find uniques: {key:<16}", advance=advance
            )

            uniq_dict = {}

            for uuid, structure in zip(*zip(*data)):
                new_unique = True

                # Look for similarity, stop in case you've found it
                for uniq_data in uniq_dict.values():
                    if matcher.fit(
                        structure.get_pymatgen(), uniq_data[0].get_pymatgen()
                    ):
                        new_unique = False
                        uniq_data[1].append(uuid)
                        break

                if new_unique:
                    uniq_dict[uuid] = (structure, [uuid])

            global_unique_dict.update(uniq_dict)

    return global_unique_dict


def seb_knows_best(ordered, matcher):
    """Perform a similarity analysis using the Seb-knows-best method."""

    label = "Uniqueness analysis for each compound"
    with click.progressbar(label=label, length=len(ordered), show_pos=True) as progress:
        unique = {}

        for structures in ordered.values():
            uuids = [s[0] for s in structures]
            structures = [s[1] for s in structures]

            nstructures = len(structures)
            adjacent_matrix = eye(nstructures, dtype=int)

            for i in range(nstructures):
                for j in range(i + 1, nstructures):
                    adjacent_matrix[i, j] = matcher.fit(
                        structures[i].get_pymatgen(), structures[j].get_pymatgen()
                    )
                    adjacent_matrix[j, i] = adjacent_matrix[i, j]

            _, connection = connected_components(adjacent_matrix, directed=False)
            prototype_indices = [
                where(connection == e)[0].tolist() for e in set(connection)
            ]

            for prototype in prototype_indices:
                prototype_uuids = [uuids[index] for index in prototype]
                prototype_structure = structures[prototype[0]]

                unique[uuids[prototype[0]]] = (prototype_structure, prototype_uuids)

            progress.update(1)

    return unique


def pymatgen_group(ordered, matcher):
    """Perform a similarity analysis using the pymatgen method."""
    structures = [s[1] for data in ordered.values() for s in data]

    return matcher.group_structures(structures)
