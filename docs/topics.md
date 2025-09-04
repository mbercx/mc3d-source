# Topics

This is a collection of notes that discuss the approach to various steps of the MC3D-source pipeline.

## Update

This section discusses our approach for "updating" an import, i.e. you do a fresh import from a source database that you already imported structures from previously.

!!! warning

    These notes are based on the new MPDS import, where all versions are updated. This will have to be changed for other imports (e.g. COD) where the versions for some structures may not have changed.

### Import and process the new set of structures

First steps are to:

1. Do a full import of all the raw `CifData`.
1. Run the `CifCleanWorkChain` for all of them.
3. "Curate" the structures with `mc3d-source curate`.

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
