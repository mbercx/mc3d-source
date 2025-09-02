"""Import the CIF files as `CifData`."""

from __future__ import annotations

from datetime import datetime
from urllib.error import HTTPError

from aiida import load_profile, orm
from aiida.plugins.factories import DbImporterFactory
from CifFile.StarFile import StarError
from rich import print as rprint

load_profile("prod")


def main(
    database: str,
    cif_raw_group: str,
    *,
    max_number_species: int | None = None,
    api_key: str | None = None,
    dry_run: bool = False,
    batch_size: int = 1000,
):
    """Import structures from an external database.

    This command will call the `aiida-codtools data cif import` CLI script to perform the actual importing.
    The imported CIF files will be turned into `CifData` nodes and stored in the group `{database}/cif/raw`. The output
    of the script will be piped to a file in a folder that bears the name of the chosen database and the filename is
    created by the current date. This way it is easy to see when this script was ran for the last time. Simply by
    rerunning this script, any new CIF files that have been added to the external database since the last import will be
    simply added to the group.
    """

    def time_report(message):
        rprint(f"[bold yellow]Report ({datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}):[/] {message}")

    max_number_species = max_number_species or 20
    group_cif_raw, created = orm.Group.collection.get_or_create(label=cif_raw_group)

    if created:
        rprint(f"[bold blue]Info:[/] Created group with label: {cif_raw_group}")

    importer_parameters = {}
    inputs_database_specific = {}

    if database == "icsd":
        importer_parameters = {
            "server": "http://localhost/",
            "host": "127.0.0.1",
            "db": "icsd",
            "passwd": "sql",
        }

    elif database == "mpds":
        if api_key is None:
            rprint("[bold red]Critical[/]: must specify --api-key for MPDS.")

        importer_parameters["api_key"] = api_key

        if max_number_species > 5:  # noqa: PLR2004
            # Anything above `quinary` will be translated to `multinary`
            max_number_species = 6

    for number_species in range(1, max_number_species + 1):
        query_parameters = {}

        inputs = {
            "group": group_cif_raw,
            "database": database,
            "number_species": number_species,
            "dry_run": dry_run,
        }
        inputs.update(inputs_database_specific)

        if database == "mpds":
            query_parameters = {"query": {}, "collection": "structures"}

            number_species_to_class = {
                1: "unary",
                2: "binary",
                3: "ternary",
                4: "quaternary",
                5: "quinary",
            }
            if number_species in number_species_to_class:
                query_parameters["query"]["classes"] = number_species_to_class[number_species]
            else:
                # Limitation of MPDS: retrieve everything with more than 5 elements and filter on retrieved cifs. Since it
                # is impossible to quickly determine the number of elements in a raw CIF file without parsing it, we cannot
                # actually apply the filtering in the import here.
                query_parameters["query"]["classes"] = "multinary"
        else:
            query_parameters["number_of_elements"] = number_species

        rprint("=" * 80)
        time_report("Starting import")
        rprint(f"Importer parameters: {importer_parameters}")
        rprint(f"Query parameters: {query_parameters}")
        rprint("-" * 80)

        try:
            importer = DbImporterFactory(f"core.{database}")(**importer_parameters)
            query_results = importer.query(**query_parameters)
        except Exception as exception:  # noqa: BLE001
            rprint(f"[bold red]Critical:[/] database query failed: {exception}")
            return

        query = orm.QueryBuilder()
        query.append(orm.Group, filters={"label": group_cif_raw.label}, tag="group")
        query.append(orm.CifData, with_group="group", project="attributes.source.id")
        existing_source_ids = set(query.all(flat=True))

        batch = []

        for entry in query_results:
            source_id = entry.source["id"]

            if source_id in existing_source_ids:
                time_report(f"Cif<{source_id}> skipping: already present in group {group_cif_raw.label}")
                continue

            try:
                cif = entry.get_cif_node()
            except (AttributeError, UnicodeDecodeError, StarError, HTTPError) as exception:
                name = exception.__class__.__name__
                time_report(
                    f"Cif<{source_id}> skipping: encountered an error retrieving cif data: {name} | {exception}"
                )
            else:
                batch.append(cif)
                time_report(f"Cif<{source_id}> adding new CifData<{cif.uuid}> to batch.")

            if len(batch) == batch_size:
                time_report(f"Storing batch of {len(batch)} CifData nodes")
                nodes = [node.store() for node in batch]
                time_report(f"Adding CifData nodes {group_cif_raw.label}")
                group_cif_raw.add_nodes(nodes)
                batch = []
