"""Find missing raw `CifData` in new import."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import typer
from aiida import orm
from rich import print as rprint

from mc3d_source.constants import SourceDeprecation
from mc3d_source.tools.source import get_source_string

if TYPE_CHECKING:
    from pathlib import Path


def id_removed(old_raw_cif_group: str, new_raw_cif_group: str, file_path: Path | None = "deprecation.json"):
    """Find missing raw `CifData` in new import."""

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": old_raw_cif_group}, tag="group").append(
        orm.CifData, with_group="group", project="attributes.source.id"
    )
    old_cif_ids = query.all(flat=True)

    rprint(f"[bold yellow]Report:[/] Found {len(old_cif_ids)} `CifData` nodes in `{old_raw_cif_group}`.")

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": new_raw_cif_group}, tag="group").append(
        orm.CifData, with_group="group", project="attributes.source.id"
    )
    new_cif_ids = query.all(flat=True)

    missing_ids = set(old_cif_ids).difference(set(new_cif_ids))

    rprint(f"[bold yellow]Report:[/] Found {len(new_cif_ids)} `CifData` nodes in `{new_raw_cif_group}`.")
    rprint(
        f"[bold yellow]Report:[/] Found {len(missing_ids)} IDs that no longer have a raw `CifData` in `{old_raw_cif_group}`."
    )

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": old_raw_cif_group}, tag="group").append(
        orm.CifData,
        with_group="group",
        filters={"attributes.source.id": {"in": list(missing_ids)}},
        project="attributes.source",
    )
    source_to_issues = {
        get_source_string(source): SourceDeprecation.ID_REMOVED.value for source in query.all(flat=True)
    }
    if file_path.exists():
        rprint(f"[bold blue]Info:[/] `{file_path}` exists, updating data.")
        file_issues = json.loads(file_path.read_text())
        source_to_issues = file_issues | source_to_issues

    file_path.write_text(json.dumps(source_to_issues, indent=2, sort_keys=True))


def structure_updated(
    old_curated_structure_group: str, new_final_structure_group: str, file_path: Path | None = "deprecation.json"
):
    """Find structures that have been updated."""
    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": new_final_structure_group}, tag="group").append(
        orm.StructureData, with_group="group", project=("extras.source")
    )
    new_sources = {get_source_string(source) for source in query.all(flat=True)}

    query = orm.QueryBuilder()
    query.append(orm.Group, filters={"label": old_curated_structure_group}, tag="group").append(
        orm.StructureData, with_group="group", project=("extras.source.id", "extras.source")
    )
    old_id_to_source = {source_id: get_source_string(source) for source_id, source in query.all()}
    old_sources = set(old_id_to_source.values())
    old_source_ids = {source_string.split("|")[-1] for source_string in old_sources}

    old_source_were_fine = old_sources.intersection(new_sources)
    rprint(f"[bold yellow]Report:[/] Found {len(old_source_were_fine)} structures where the old source was fine.")

    new_sources_taken = new_sources.difference(old_source_were_fine)

    versions = set()
    updated_sources = set()

    for source_string in new_sources_taken:
        _, version, source_id = source_string.split("|")
        versions.add(version)

        if source_id in old_source_ids:
            updated_sources.add(old_id_to_source[source_id])

    rprint(f"[bold blue]Info:[/] Found the following versions among the new structures: {versions}.")
    rprint(f"[bold yellow]Report:[/] Found {len(updated_sources)} structures where the structure was updated.")

    source_to_issues = {source: SourceDeprecation.STRUCTURE_UPDATED.value for source in updated_sources}
    if file_path.exists():
        rprint(f"[bold blue]Info:[/] `{file_path}` exists, updating data.")
        file_issues = json.loads(file_path.read_text())
        keys_overlap = set(file_issues.keys()).intersection(source_to_issues.keys())

        if keys_overlap:
            rprint(f"[bold red]Critical:[/] Found issues for sources that overlap with those in `{file_path}`!")
            return

        source_to_issues = file_issues | source_to_issues

    file_path.write_text(json.dumps(source_to_issues, indent=2, sort_keys=True))


def incorrect_formula(file_path: Path | None = "deprecation.json"):
    """Find structures that have an incorrect formula."""
    query = orm.QueryBuilder()

    query.append(
        orm.StructureData,
        filters={"extras": {"has_key": "incorrect_formula"}},
        project=("extras.source",),
    )
    source_to_issues = {
        get_source_string(source): SourceDeprecation.INCORRECT_FORMULA.value for source in query.all(flat=True)
    }
    if file_path.exists():
        rprint(f"[bold blue]Info:[/] `{file_path}` exists, updating data.")
        file_issues = json.loads(file_path.read_text())
        keys_overlap = set(file_issues.keys()).intersection(source_to_issues.keys())

        if keys_overlap:
            rprint(
                f"[bold orange]Warning:[/] Found issues for {len(keys_overlap)} sources that overlap with those in `{file_path}`!"
            )
            if not typer.confirm("Do you want to continue? This will overwrite the issues."):
                typer.echo("[bold red]Aborted![/]")
                return

        source_to_issues = file_issues | source_to_issues

    file_path.write_text(json.dumps(source_to_issues, indent=2, sort_keys=True))
