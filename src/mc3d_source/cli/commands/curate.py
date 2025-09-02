"""Curate the parsed `StructureData` from a set of `CifCleanWorkChain`."""

from aiida import load_profile, orm
from aiida_codtools.workflows.cif_clean import CifCleanWorkChain
from rich import print
from rich.progress import track

load_profile("prod")


KEY_SOURCE = "source"
KEY_PARTIAL_OCCUPANCIES = "partial_occupancies"
KEY_INCORRECT_FORMULA = "incorrect_formula"

# This maps the `db_name` value in the `source` attribute of the raw `CifData` to the desired `source.database` value
# for the `source` extra to assign to the parsed `StructureData`.
DB_NAME_MAPPING = {
    "Crystallography Open Database": "cod",
    "Icsd": "icsd",
    "Materials Platform for Data Science": "mpds",
}
# This maps the `CifCleanWorkChain` exit code to the value of the `incorrect_formula` extra which we assign to the
# parsed `StructureData`.
CIFCLEAN_EXIT_CODE_TO_EXTRAS_VALUE = {430: "missing_elements", 431: "different_comp", 432: "check_failes"}


def main(
    cif_clean_group: str,
    curated_structure_group: str,
):
    """Curate the parsed `StructureData`.

    Starting from the `CifCleanWorkChain` in `CIF_CLEAN_GROUP`, add several details to the extras of the parsed
    `StructureData`:

    1. Add the source from the raw CIF to all `StructureData`.
    2. Add the spacegroup number of the cleaned CIF to all `StructureData`.
    3. Check if the structure has partial occupancies and add that boolean.
    4. Check if the `CifCleanWorkChain` had an exit code corresponding to a formula mismatch and add the corresponding
       extra.

    Add stoichiometric structures without formula mismatch issues to the `CURATED_STRUCTURE_GROUP`.
    """
    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": cif_clean_group}, tag="group").append(
        CifCleanWorkChain, with_group="group", tag="cif_clean", project="attributes.exit_status"
    ).append(orm.CifData, with_outgoing="cif_clean", project=("attributes.source")).append(
        orm.CifData, with_incoming="cif_clean", project="attributes.spacegroup_numbers"
    ).append(orm.StructureData, with_incoming="cif_clean", project="*")
    print(f"[bold yellow]Report:[/] Found {query.count()} `CifCleanWorkChain` to process.")

    curated_structure_group = orm.load_group(curated_structure_group)

    data = []

    for cif_wc_exit_status, cif_source, spacegroup_numbers, structure in track(
        query.all(), description="Gathering data..."
    ):
        # Add the source from the raw CIF to the `StructureData`
        extras_to_set = {
            KEY_SOURCE: {
                "database": DB_NAME_MAPPING[cif_source["db_name"]],
                "version": cif_source["version"],
                "id": cif_source["id"],
            }
        }

        # Add the spacegroup number of the clean CIF to the `StructureData`
        if len(spacegroup_numbers) == 1:
            extras_to_set["cif_spacegroup_number"] = spacegroup_numbers[0]

        # Set the partial occupancies key
        partial_occupancies = structure.is_alloy or structure.has_vacancies
        extras_to_set[KEY_PARTIAL_OCCUPANCIES] = partial_occupancies

        # Check that the `CifCleanWorkChain` doesn't indicate that the structure might have an incorrect formula
        incorrect_formula = cif_wc_exit_status in CIFCLEAN_EXIT_CODE_TO_EXTRAS_VALUE
        if incorrect_formula:
            extras_to_set[KEY_INCORRECT_FORMULA] = CIFCLEAN_EXIT_CODE_TO_EXTRAS_VALUE[cif_wc_exit_status]

        # Select only structures that have no partial occupancies or formula issues.
        curated = not any((partial_occupancies, incorrect_formula))

        data.append((structure, extras_to_set, curated))

    with query.backend.transaction():
        for structure, extras_to_set, curated in track(data, description="Curating..."):
            structure.base.extras.set_many(extras_to_set)
            if curated:
                curated_structure_group.add_nodes(structure)
