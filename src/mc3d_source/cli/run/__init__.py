# -*- coding: utf-8 -*-
"""Run commands to obtain the final list of structures."""
import collections
from importlib import resources
from pathlib import Path
from typing import Annotated, List, Optional

import pandas as pd
import typer
import yaml
from aiida import orm
from aiida.cmdline.utils import decorators
from aiida.common import NotExistent
from aiida.manage import get_manager
from hith.data import flags
from pymatgen.analysis.structure_matcher import StructureMatcher
from rich import print
from rich.pretty import pprint
from rich.progress import track

app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
@decorators.with_dbenv()
def uniq(
    source_group: str,
    target_group: str,
    create_target_group: bool = False,
    method: str = "first",
    contains: Annotated[
        Optional[List[str]],
        typer.Option(
            "--contains",
            "-c",
            help="Filter on structures that contain this element. Can be used multiple times.",
        ),
    ] = None,
    skip: Annotated[
        Optional[List[str]],
        typer.Option(
            "-S",
            "--skip",
            help="Skip structures that contain this element. Can be used multiple times.",
        ),
    ] = None,
    max_size: int = None,
    dry_run: bool = False,
    sort_by_spg: bool = True,
    matcher_settings: Path = None,
    limit: int = None,
):
    """Perform uniqueness analysis on a group of structures.

    \bThis command will perform a uniqueness analysis on a group of structures. The structures are sorted by
    chemical formula and (optionally) space group. The uniqueness analysis is performed by comparing the
    structures in the sorted list to each other using the `StructureMatcher` from pymatgen.
    """
    from .uniq import (
        first_come_first_serve,
        get_spglib_spacegroup_symbol,
        pymatgen_group,
        seb_knows_best,
    )

    method_mapping = {
        "seb": seb_knows_best,
        "first": first_come_first_serve,
        "pmg": pymatgen_group,
    }
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
    matcher = StructureMatcher(**structure_matcher_settings)

    try:
        source_group = orm.load_group(source_group)
    except NotExistent:
        print("[bold red]Error:[/] The source group does not exist!")
        return

    if len(source_group.nodes) == 0:
        print("[bold blue]Info:[/] The source group is empty.")
        return

    try:
        target_group = orm.load_group(target_group)
    except NotExistent:
        if create_target_group:
            target_group, _ = orm.Group.collection.get_or_create(target_group)
        else:
            print(
                "[bold red]Error:[/] The target group does not exist! Use `--create-target-group` if you want to "
                "automatically create the target group."
            )
            return

    failures = []

    struc_filters = {"and": [{"extras": {"!has_key": "incorrect_formula"}}]}

    if contains:
        for element in contains:
            struc_filters["and"].append(
                {"extras.chemical_system": {"like": f"%-{element}-%"}}
            )

    if skip:
        for element in skip:
            struc_filters["and"].append(
                {"extras.chemical_system": {"!like": f"%-{element}-%"}}
            )

    if max_size is not None:
        struc_filters["and"].append({"extras.number_of_sites": {"<=": max_size}})

    query_dict = {"source": orm.QueryBuilder(), "target": orm.QueryBuilder()}

    query_dict["source"].append(
        orm.Group, filters={"label": source_group.label}, tag="group"
    )

    if isinstance(source_group.nodes[0], orm.StructureData):
        query_dict["source"].append(
            orm.StructureData, with_group="group", filters=struc_filters
        )
    elif isinstance(source_group.nodes[0], orm.WorkChainNode):
        query_dict["source"].append(
            orm.WorkChainNode, with_group="group", tag="wc"
        ).append(orm.StructureData, with_incoming="wc", filters=struc_filters)

    query_dict["target"].append(
        orm.Group, filters={"label": target_group.label}, tag="group"
    ).append(orm.StructureData, with_group="group", filters=struc_filters)

    number_source = query_dict["source"].count()
    number_target = query_dict["target"].count()

    if number_source == 0:
        print(
            "[bold red]Error:[/] There are no structures in the source group with the specified filters."
        )
        return
    else:
        print(
            f"[bold blue]Info:[/] Found {number_source} structures in the source group."
        )

    if limit:
        print(f"[bold blue]Info:[/] Limiting the source query to {limit} structures.")
        query_dict["source"].limit(limit)

    if number_target != 0:
        print(
            f"[bold blue]Info:[/] Found {number_target} structures in the target group."
        )

    # Map all structures that are in the candidate group on reduced chemical formula and (optionally) space group
    mapping = collections.defaultdict(list)

    for group, query in query_dict.items():
        for [structure] in track(
            query.iterall(),
            total=query.count(),
            description=f"Sorting {group} group:" + " " * 9,
        ):
            try:
                sort_key = structure.get_formula(mode="hill_compact")

                if sort_by_spg:
                    sort_key += "|"
                    sort_key += str(
                        get_spglib_spacegroup_symbol(structure, symprec=0.005)
                    )

                if group == "target" and sort_key not in mapping.keys():
                    # If the `target` key is not in the list of `source` keys, it doesn't need to be considered
                    continue

                mapping[sort_key].append(
                    [len(structure.sites), structure.uuid, structure]
                )

            except Exception as exc:
                failures.append((structure.uuid, exc))

    if failures:
        print("[bold yellow]Warning:[/] Some structures failed to be sorted:")
        pprint(failures)

    # Order the mapping alphabetically by chemical formula and within each formula entry by number of atoms and UUID
    ordered = collections.OrderedDict()
    for sort_key, entries in sorted(mapping.items(), key=lambda x: x[0]):
        ordered[sort_key] = [
            (entry[1], entry[2])
            for entry in sorted(entries, key=lambda e: (e[0], e[1]))
        ]

    # Write out the sorted mapping
    # sort_number_dict = {key: len(listy) for key, listy in ordered.items()}
    # timestamp = "".join(str(datetime.now()).split('.')[:-1]).replace(' ', '_')
    # with Path(f'sorted_numbers-{timestamp}.yaml').open('w') as handle:
    #     yaml.dump(sort_number_dict, handle)

    # Perform the uniqueness analysis with the chosen method
    uniq = method_mapping[method](ordered, matcher)

    # with Path(f'results-{timestamp}.yaml').open('w') as handle:
    #     yaml.dump({puuid: data[1] for puuid, data in uniq.items()}, handle)

    new_uuid_uniq = uniq.copy()

    duplicate_style = "source"

    def get_duplicate_id(node, style="source"):
        if style == "source":
            duplicate_id = list(node.extras["source"].values())
            duplicate_id.reverse()
            return "|".join(duplicate_id)
        if style == "uuid":
            return node.uuid

    def get_duplicate_set(uuid, style="source"):
        duplicates = orm.load_node(uuid).extras.get("duplicates", [])
        duplicates = [] if isinstance(duplicates, dict) else duplicates
        return set(
            [
                get_duplicate_id(orm.load_node(uuid), style),
            ]
            + duplicates
        )

    target_duplicates_list = []

    # Add the duplicates to the target group nodes
    if target_group.nodes:
        for structure in track(
            target_group.nodes, description="Looking for new unique nodes: "
        ):
            for uniq_uuid, data in uniq.items():
                _, duplicate_uuids = data

                if structure.uuid in data[1]:
                    new_uuid_uniq.pop(uniq_uuid, None)

                    if not dry_run:
                        target_duplicates = set(structure.extras["duplicates"])
                        for duplicate_uuid in duplicate_uuids:
                            target_duplicates.update(
                                get_duplicate_set(duplicate_uuid, duplicate_style)
                            )
                        target_duplicates_list.append((structure, target_duplicates))

    if not dry_run and target_group.nodes:
        for structure, duplicates in track(
            target_duplicates_list, description="Updating target duplicates:   "
        ):
            duplicates.remove(get_duplicate_id(structure))
            structure.base.extras.set("duplicates", duplicates)

    print(f"[bold blue]Info:[/] Found {len(new_uuid_uniq)} new unique structures.")

    if len(new_uuid_uniq) == 0:
        return

    new_nodes = []

    if not dry_run and len(new_uuid_uniq) > 0:
        # Add the new golden structures + duplicates to the target group
        with get_manager().get_profile_storage().transaction() as _:
            for data in track(
                new_uuid_uniq.values(), description="Adding extras to new nodes:   "
            ):
                structure, duplicates = data
                try:
                    target_duplicates = set(structure.extras.get("duplicates", []))
                except TypeError:
                    raise ValueError(structure.extras.get("duplicates", []))
                if duplicate_style == "source":
                    duplicates = [
                        get_duplicate_id(orm.load_node(uuid)) for uuid in duplicates
                    ]
                target_duplicates.update(set(duplicates))
                target_duplicates.remove(get_duplicate_id(structure))
                structure.base.extras.set("duplicates", target_duplicates)
                new_nodes.append(structure)

    print(f"[bold blue]Info:[/] Adding {len(new_nodes)} nodes to target group.")
    target_group.backend_entity.add_nodes(
        [node.backend_entity for node in new_nodes], skip_orm=True
    )
    print("[bold green]Success:[/] Uniqueness Analysis complete! 🌈")

    # Add the "golden UUID" to the structures left behind
    # TODO


@app.command()
@decorators.with_dbenv()
def select(unique_group):
    """Select the structures we want to run.

    \bThis command will check the flags of all structures in the `unique_group` group and check if:

    \b1. The structure has any problematic flags (e.g. `is_theoretical`, `is_high_pressure`, etc.).
    2. If so, whether there are any duplicates that do not have these flags.

    In this case, we want to replace the structure with a "better" duplicate. Here we select one
    duplicate that doesn't have any problematic flags, preferring those from the COD, then the ICSD,
    then the MPDS. This is based on the permissiveness of the licenses of these databases.
    """
    from .select import find_better_duplicates, replace_structure

    flag_dict = {}

    print(
        "[bold blue]Info[/]: Populating flag dictionary from the CSV files of each database."
    )
    for database in ("cod", "icsd", "mpds"):
        flag_dict.setdefault(database, {})
        df = pd.read_csv(resources.files(flags) / f"{database}.csv", header=2)
        for _, row in track(df.iterrows(), description=database.upper()):
            flag_dict[database][str(row["id"])] = row

    replacements = []

    for structure in track(
        orm.load_group("global/uniq").nodes,
        description="Checking for better duplicates",
    ):
        if "duplicates" in structure.extras:
            better_duplicates = find_better_duplicates(flag_dict, structure)
            if better_duplicates:
                replacements.append((structure, better_duplicates))

    print(
        f"[bold blue]Info[/]:Found {len(replacements)} structures to replace with better duplicates."
    )
    typer.confirm("Do you want to continue?", abort=True)

    group = orm.load_group(unique_group)

    for replacement in track(replacements, description="Replacing structures"):
        replace_structure(replacement, group)
