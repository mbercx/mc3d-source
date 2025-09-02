"""Perform uniqueness analysis on a group of structures."""

from __future__ import annotations

import collections
import json
import time
from collections import OrderedDict
from itertools import islice
from multiprocessing import Manager, Pool
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import spglib
import yaml
from aiida import load_profile, orm
from aiida.cmdline.utils import decorators
from aiida.common import NotExistent
from aiida.tools.data.structure import structure_to_spglib_tuple
from numpy import eye, where
from pymatgen.analysis.structure_matcher import StructureMatcher
from rich import print
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, track
from scipy.sparse.csgraph import connected_components

if TYPE_CHECKING:
    import typer


@decorators.with_dbenv()
def main(
    source_group: list[str],
    *,
    profile: str | None = None,
    output_file: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output-file",
            help="Write the list of duplicate families to this file.",
        ),
    ] = "result.json",
    method: str = "first",
    sort_by_spg: bool = True,
    matcher_settings: Path | None = None,
    parallelize: int = 5,
    chunk_size: int | None = None,
    contains: Annotated[
        list[str] | None,
        typer.Option(
            "--contains",
            "-c",
            help="Filter on structures that contain this element. Can be used multiple times.",
        ),
    ] = None,
    skip: Annotated[
        list[str] | None,
        typer.Option(
            "-S",
            "--skip",
            help="Skip structures that contain this element. Can be used multiple times.",
        ),
    ] = None,
):
    """Perform uniqueness analysis on a group of structures.

    \bThis command will perform a uniqueness analysis on a group of structures. The structures are sorted by
    chemical formula and (optionally) space group. The uniqueness analysis is performed by comparing the
    structures in the sorted list to each other using the `StructureMatcher` from pymatgen.
    """
    if profile:
        load_profile(profile, allow_switch=True)

    if matcher_settings:
        with matcher_settings.open("r") as handle:
            structure_matcher_settings = yaml.safe_load(handle)
    else:
        # Set (mostly) the default settings from pymatgen, added here for reference
        structure_matcher_settings = {
            "ltol": 0.2,  # default
            "stol": 0.3,  # default
            "angle_tol": 5,  # default
            "primitive_cell": False,  # Set to `False` from `True`. Structures are already primitivized
            "scale": True,  # default
            "attempt_supercell": False,  # default
        }

    for group_label in source_group:
        try:
            orm.load_group(group_label)
        except NotExistent:
            print(f"[bold red]Error:[/] The source group `{group_label}` does not exist!")
            return

    struc_filters = {
        "and": [
            {"extras": {"!has_key": "incorrect_formula"}},
        ]
    }

    if contains:
        for element in contains:
            struc_filters["and"].append({"extras.chemical_system": {"like": f"%-{element}-%"}})

    if skip:
        for element in skip:
            struc_filters["and"].append({"extras.chemical_system": {"!like": f"%-{element}-%"}})

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": {"in": source_group}}, tag="group").append(
        orm.StructureData,
        with_group="group",
        filters=struc_filters,
        project=("*", "extras.source", "extras.cif_spacegroup_number"),
    )

    number_source = query.count()

    if number_source == 0:
        print("[bold red]Error:[/] There are no structures in the source group(s) with the specified filters.")
        return

    print(f"[bold blue]Info:[/] Found {number_source} structures in the source group(s).")

    # Map all structures that are in the candidate group on reduced chemical formula and (optionally) space group
    mapping = collections.defaultdict(list)

    for structure, source, cif_spacegroup_number in track(
        query.iterall(),
        total=number_source,
        description="Sorting structures:" + " " * 9,
    ):
        sort_key = structure.get_formula(mode="hill_compact")

        if sort_by_spg:
            spg_number = (
                cif_spacegroup_number
                or spglib.get_symmetry_dataset(
                    structure_to_spglib_tuple(structure)[0],
                    symprec=0.005,
                ).number
            )
            sort_key += f"|{spg_number}"

        source_string = f"{source.get('database')}|" f"{source.get('version')}|" f"{source.get('id')}"
        mapping[sort_key].append((source_string, structure.get_pymatgen_structure()))

    print(f"[bold blue]Info:[/] Sorted the structures into {len(mapping)} groups.")

    # Perform the uniqueness analysis for each formula/SPG key
    checkpoint_file = Path("checkpoint.json")

    if checkpoint_file.exists():
        with checkpoint_file.open("r") as handle:
            uniques_mapping = json.load(handle)
        print(f"[bold blue]Info:[/] Loaded previous data from {checkpoint_file}.")
    else:
        # For formula/SPG that only have one structure, no analysis needs to be performed
        uniques_mapping = {
            k: [
                v[0][0],
            ]
            for k, v in mapping.items()
            if len(v) == 1
        }

    mapping = OrderedDict(
        sorted(
            ((k, v) for k, v in mapping.items() if k not in uniques_mapping),
            key=lambda item: len(item[1]),
            reverse=True,
        )
    )
    if chunk_size is not None:
        for chunk in chunked_mapping(mapping, chunk_size):
            uniques_mapping.update(
                similarity_parallel(chunk, structure_matcher_settings, method=method, parallelize=parallelize)
            )
            with checkpoint_file.open("w") as handle:
                handle.write(json.dumps(uniques_mapping))
                print(f"[bold blue]Info:[/] Backed up data to {checkpoint_file}.")
    else:
        uniques_mapping.update(
            similarity_parallel(mapping, structure_matcher_settings, method=method, parallelize=parallelize)
        )

    unique_families = [x for v in uniques_mapping.values() for x in v]

    print(f"[bold blue]Info:[/] Found {len(unique_families)} unique families.")

    with output_file.open("w") as handle:
        handle.write(json.dumps(unique_families, indent=4))


def chunked_mapping(mapping, size):
    """Yield dict chunks of given size from a mapping."""
    it = iter(mapping.items())
    while True:
        chunk = dict(islice(it, size))
        if not chunk:
            break
        yield chunk


def similarity_parallel(mapping, structure_matcher_settings, method, parallelize):
    """Run the similarity analysis in parallel.

    :param dict mapping: Mapping of formula|spg to a list of (source, pymatgen.Structure) pairs.
    :param dict structure_matcher_settings: Settings to configure the `StructureMatcher`.
    :param str method: Method to use for similarity analysis.
    :param int parallelize: Number of parallel processes to use.

    :return: A dictionary that maps each formula|spg to a list of sources.
    """

    manager = Manager()
    queue = manager.Queue()
    wrapper = {"first": first_wrapper, "seb": seb_wrapper, "pymatgen": pymatgen_wrapper}[method]

    total_steps = sum(len(v) for v in mapping.values())

    with Progress(
        TextColumn("[progress.description]{task.description:<30}"),
        BarColumn(),
        TimeElapsedColumn(),
    ) as progress:
        overall = progress.add_task("[bold green]Initialising...", total=total_steps)

        with Pool(processes=parallelize) as pool:
            result_async = pool.map_async(
                wrapper,
                [(formula, structures, structure_matcher_settings, queue) for formula, structures in mapping.items()],
            )

            while not result_async.ready():
                while not queue.empty():
                    msg = queue.get()
                    progress.advance(overall, 1)
                    progress.update(overall, description=f"[bold green]Processing {msg:<15}")

                time.sleep(0.1)

            uniq_dicts = result_async.get()

    return {k: v for d in uniq_dicts for k, v in d.items()}


def first_wrapper(args):
    """Wrapper for the multiprocessing pool to handle arguments."""
    return first_reference(*args)


def seb_wrapper(args):
    """Wrapper for the multiprocessing pool to handle arguments."""
    return seb_knows_best(*args)


def first_reference(formula, data, structure_matcher_settings, queue):
    """Similarity analysis that takes the first structure as the reference structure to match with.

    :param str formula:
    :param dict structure_matcher_settings: Settings to configure the `StructureMatcher`.
    :param str method: Method to use for similarity analysis.
    :param int parallelize: Number of parallel processes to use.

    :return: A dictionary that maps each formula|spg to a list of sources.
    """
    queue.put(formula)

    matcher = StructureMatcher(**structure_matcher_settings)

    uniq_list = []

    for source_string, structure in data:
        new_unique = True

        # Look for similarity, stop in case you've found it
        for uniq_data in uniq_list:
            reference_structure, sources = uniq_data

            if matcher.fit(structure, reference_structure):
                new_unique = False
                sources.append(source_string)
                break

        if new_unique:
            uniq_list.append((structure, [source_string]))

    return {formula: [el[1] for el in uniq_list]}


def seb_knows_best(formula, data, structure_matcher_settings, queue):
    """Perform a similarity analysis using the Seb-knows-best method."""
    queue.put(formula)

    matcher = StructureMatcher(**structure_matcher_settings)

    source_strings = [s[0] for s in data]
    structures = [s[1] for s in data]

    nstructures = len(structures)
    adjacent_matrix = eye(nstructures, dtype=int)

    for i in range(nstructures):
        for j in range(i + 1, nstructures):
            adjacent_matrix[i, j] = matcher.fit(structures[i], structures[j])
            adjacent_matrix[j, i] = adjacent_matrix[i, j]

    _, connection = connected_components(adjacent_matrix, directed=False)
    prototype_indices = [where(connection == e)[0].tolist() for e in set(connection)]

    uniq_list = []

    for prototype in prototype_indices:
        prototype_sources = [source_strings[index] for index in prototype]
        prototype_structure = structures[prototype[0]]

        uniq_list.append((prototype_structure, prototype_sources))

    queue.put(formula)

    return {formula: [el[1] for el in uniq_list]}


def pymatgen_wrapper(args):
    """Wrapper for the multiprocessing pool to handle arguments."""

    def pymatgen_group(formula, data, structure_matcher_settings, queue):
        """Perform a similarity analysis using the pymatgen `group_structures` method."""
        queue.put(formula)
        matcher = StructureMatcher(**structure_matcher_settings)

        id_to_source = {id(structure): source_string for source_string, structure in data}
        groups = matcher.group_structures([structure for _, structure in data])

        return {formula: [[id_to_source[id(structure)] for structure in group] for group in groups]}

    return pymatgen_group(*args)
