# Topics

This is a collection of notes that discuss the approach to various steps of the MC3D-source pipeline.

## Curate

Starting from each `CifCleanWorkChain`, add several details to the extras of the parsed
`StructureData`:

1. Add the source from the raw CIF to all `StructureData` under `source`.
2. Add the spacegroup number of the cleaned CIF to all `StructureData` under `cif_spacegroup_number`.
3. Check if the structure has partial occupancies and add that boolean under `partial_occupancies`.
4. Check if the `CifCleanWorkChain` had an exit code corresponding to a formula mismatch and add the corresponding
    extra to `incorrect_formula`.

Finally, stoichiometric structures without formula mismatch issues are considered "curated", i.e. can be considered for the uniqueness analysis.

## Update

This section discusses our approach for "updating" an import, i.e. you do a fresh import from a source database that you already imported structures from previously.

!!! warning

    These notes are based on the new MPDS import, where all versions are updated. This will have to be changed for other imports (e.g. COD) where the versions for some structures may not have changed.

### Import and process the new set of structures

First steps are to:

1. Do a full import of all the raw `CifData`.
1. Run the `CifCleanWorkChain` for all of them.
3. "Curate" the structures with `mc3d curate`.

This will result in a group of "curated" structures, let's call it `mpds/v2/structure/curated`.

### Update the list of curated structures

We want to update the list of curated structures from the previous import (e.g. `mpds/v1/structure/curated`) using the new import.

The steps are:

1. Loop over the **new** curated `StructureData`. If there is structure with the same ID in the old curated group, add it to `mpds/v2/structure/final`.
1. If there is a corresponding entry, check for similarity:
   * If similar, no point in updating: take the `v1` structure and add it to `mpds/v2/structure/final`.
   * If not, take the `v2` structure and add it to `mpds/v2/structure/final`.

This deals with the following cases:

1. If the entry was removed by the MPDS, it will not be in `mpds/structure/latest`. Only IDs that are currently still in the MPDS will be in `mpds/structure/latest`.
2. If the entry update doesn't generate a significantly different structure, the old source is preserved.
3. If the entry update _does_ generate a new structure (i.e. doesn't match), the version is updated.

One case that is missed is when the `CifCleanWorkChain` failed for the new import, but succeeded for the old one.
If this happens, we want to still keep the old version, unless it was since removed by the MPDS.

## Deprecation

Here we discuss the process of "deprecating" sources and MC3D IDs.
This means that they are no longer valid for some reason, and need to be flagged/removed from the frontend, and no longer considered when building the unique families of duplicates.

### Sources

Reasons to deprecate a source include:

* `id_removed`: The corresponding ID has been removed from the source database.
* `structure_updated`: The corresponding ID has a different structure in a newer version of the database
* `incorrect_formula`: The structure of the corresponding ID had a formula mismatch between the cleaned CIF and the parsed structure.

### MC3D-IDs

When all of the sources in the corresponding family are deprecated, an MC3D ID is considered "fully" deprecated.

!!! note

    This means when a structure we ran (aka golden structure) might be deprecated, but the MC3D ID is not.
    We instead put a warning, but keep the structure findable.
