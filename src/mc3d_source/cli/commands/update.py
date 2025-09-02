"""Update the latest structure set for a database."""

from aiida import load_profile, orm
from pymatgen.analysis.structure_matcher import StructureMatcher
from rich import print
from rich.progress import track

load_profile("prod")


def main(old_group: str, new_group: str, target_group: str):
    """Update the latest structure set for a database."""

    target_source_ids = set(
        orm.QueryBuilder()
        .append(orm.Group, filters={"label": target_group}, tag="group")
        .append(orm.StructureData, with_group="group", project="extras.source.id")
        .all(flat=True)
    )
    if len(target_source_ids) > 1:
        print(f"[bold yellow]Report:[/] Found {len(target_source_ids)} `StructureData` in target group.")
        print("[bold blue]Info:[/] These will be skipped in the update process.")

    target_group = orm.load_group(target_group)

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": old_group}, tag="group").append(
        orm.StructureData,
        with_group="group",
        project=("extras.source.id", "*"),
    )
    old_id_to_nodes = dict(query.all())

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": new_group}, tag="group").append(
        orm.StructureData,
        with_group="group",
        project=("extras.source.id", "*"),
    )
    new_id_to_nodes = dict(query.all())

    matcher = StructureMatcher()

    n_old_structures = 0
    n_updated_structures = 0
    n_new_structures = 0

    for source_id, new_structure in track(new_id_to_nodes.items()):
        if source_id in target_source_ids:
            continue

        if source_id not in old_id_to_nodes:
            selected_structure = new_structure
            n_new_structures += 1
        else:
            old_structure = old_id_to_nodes[source_id]
            similar = matcher.fit(old_structure.get_pymatgen_structure(), new_structure.get_pymatgen_structure())
            if similar:
                selected_structure = old_structure
                n_old_structures += 1
            else:
                selected_structure = new_structure
                n_updated_structures += 1

        target_group.add_nodes(selected_structure)

    print(f"Took {n_old_structures} structures where the old one was fine.")
    print(f"Took {n_updated_structures} structures where the new one was different.")
    print(f"Found {n_new_structures} structures which are new.")
