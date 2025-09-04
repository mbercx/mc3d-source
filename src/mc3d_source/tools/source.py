from functools import lru_cache

import spglib
from aiida import orm
from aiida.tools.data.structure import structure_to_spglib_tuple
from aiida_codtools.workflows.cif_clean import CifCleanWorkChain
from pymatgen.analysis.structure_matcher import StructureMatcher
from rich.progress import track

DB_NAME_MAPPING = {
    "Crystallography Open Database": "cod",
    "Icsd": "icsd",
    "Materials Platform for Data Science": "mpds",
}


@lru_cache(maxsize=1)
def get_source_uuid_mapping():
    """Get a cached mapping from source strings to the corresponding `StructureData` UUID."""
    query = orm.QueryBuilder()

    query.append(orm.StructureData, filters={"extras": {"has_key": "source"}}, project=("extras.source", "uuid"))
    return {get_source_string(source): uuid for source, uuid in query.all()}


def get_source_string(source):
    """Get the source string corresponding to a source in `dict` format.

    Works both for the sources stored on the extras of parsed `StructureData` and the attributes of the raw `CifData`.
    """
    try:
        database = source["database"]
    except KeyError:
        database = DB_NAME_MAPPING[source["db_name"]]

    return "|".join(
        (
            database,
            source["version"],
            source["id"],
        )
    )


def get_spacegroup_number(structure, symprec=0.005):
    """Get the spglib space group number for a specified `symprec`."""
    return (
        structure.base.extras.get("cif_spacegroup_number", None)
        or spglib.get_symmetry_dataset(
            structure_to_spglib_tuple(structure)[0],
            symprec=symprec,
        ).number
    )


def find_source_structure(source_string):
    """Find the `StructureData` corresponding to a source string."""

    database, version, source_id = source_string.split("|")

    query = orm.QueryBuilder()

    query.append(
        orm.StructureData,
        filters={
            "extras.source.database": database,
            "extras.source.version": version,
            "extras.source.id": source_id,
        },
    )
    result = query.all(flat=True)

    if len(result) == 1:
        return result[0]

    msg = f"Found {len(result)} results!"
    raise ValueError(msg)


def find_source_structure_cached(source_string):
    """Find the `StructureData` corresponding to a source string using the cached `get_source_uuid_mapping` function."""
    return orm.load_node(get_source_uuid_mapping()[source_string])


def get_source_structure_dict(source_list):
    """Return a `dict` mapping the source strings in `source_list` to the corresponding `StructureData`."""

    source_to_uuid = get_source_uuid_mapping()

    uuids = [source_to_uuid[source] for source in source_list]

    query = orm.QueryBuilder()
    query.append(orm.StructureData, filters={"uuid": {"in": uuids}}, project=("extras.source", "*"))
    total = query.count()
    source_structure_dict = {}

    for source, structure in track(query.iterall(), total=total):
        source_structure_dict[get_source_string(source)] = structure

    return source_structure_dict


def find_cif_clean(source_string):
    """Return the `CifCleanWorkChain` for a certain source string."""

    inv_mapping = {v: k for k, v in DB_NAME_MAPPING.items()}
    database, version, source_id = source_string.split("|")

    query = orm.QueryBuilder()
    query.append(
        orm.CifData,
        filters={
            "attributes.source.db_name": inv_mapping[database],
            "attributes.source.version": version,
            "attributes.source.id": source_id,
        },
        tag="cif",
    ).append(CifCleanWorkChain, with_incoming="cif")
    result = query.all(flat=True)

    if len(result) == 1:
        return result[0]

    msg = f"Found {len(result)} results!"
    raise ValueError(msg)


def sources_match(ref_source_string, target_source_string, matcher=None, tol_factor=None):
    """Check if the structures of two sources match with the `StructureMatcher`."""

    tol_factor = tol_factor or 1

    structure_matcher_settings = {
        "ltol": 0.2 * tol_factor,  # default
        "stol": 0.3 * tol_factor,  # default
        "angle_tol": 5 * tol_factor,  # default
        "primitive_cell": False,  # Set to `False` from `True`. Structures are already primitivized
        "scale": True,  # default
        "attempt_supercell": False,  # default
    }
    matcher = matcher or StructureMatcher(**structure_matcher_settings)

    ref_structure = find_source_structure(ref_source_string)
    target_structure = find_source_structure(target_source_string)

    return matcher.fit(
        ref_structure.get_pymatgen_structure(), target_structure.get_pymatgen_structure()
    ) and get_spacegroup_number(ref_structure) == get_spacegroup_number(target_structure)
