# Topics

Algorithmic notes and conventions used across the `mc3d-source` pipeline. Each section describes one stage or concept; the order roughly mirrors the order in which the corresponding CLI commands are typically run.

## Semantics

The vocabulary used throughout this documentation:

- **Curated structure**: a `StructureData` produced by a `CifCleanWorkChain` that passed both checks &mdash; no partial occupancies and no formula mismatch. Curated structures are the input to the uniqueness analysis.
- **Duplicate family**: a set of source strings whose curated structures are deemed structurally equivalent by `pymatgen`'s `StructureMatcher` (see [Uniqueness](#uniqueness)).
- **Golden structure**: the one source string chosen to represent a duplicate family in the final MC3D set (see [Select](#select)). All other sources in the family are listed in the golden structure's `duplicates` extra.


## Data

The pipeline lives in an AiiDA database and is built around a few conventions on top of the AiiDA data types.

### Group labels

Pipeline state is tracked through AiiDA groups. By convention, labels are slash-separated paths with a (mostly) stable shape:

```
<database>[/<version>]/<data_type>/<stage>
```

The `<version>` segment is only used for databases that have been re-imported (currently only MPDS, with `v1` and `v2`). Using MPDS `v2` as the running example, the labels written across the pipeline are:

<table>
  <colgroup>
    <col style="width: 18em">
    <col>
  </colgroup>
  <thead>
    <tr><th>Label</th><th>Contents</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><code>mpds/v2/cif/raw</code></td>
      <td>Raw <code>CifData</code> nodes fetched from the MPDS. Written by <code>mc3d-source import</code>.</td>
    </tr>
    <tr>
      <td><code>mpds/v2/workchain/clean</code></td>
      <td>The <code>CifCleanWorkChain</code> runs themselves, one per raw CIF. Written by <code>pipeline/cif_clean/</code>.</td>
    </tr>
    <tr>
      <td><code>mpds/v2/cif/clean</code></td>
      <td>The cleaned <code>CifData</code> outputs of the <code>CifCleanWorkChain</code>s. Written by <code>pipeline/cif_clean/</code>.</td>
    </tr>
    <tr>
      <td><code>mpds/v2/structure/parsed</code></td>
      <td>The parsed <code>StructureData</code> outputs of the <code>CifCleanWorkChain</code>s. Input to <a href="#curate"><code>curate</code></a>. Written by <code>pipeline/cif_clean/</code>.</td>
    </tr>
    <tr>
      <td><code>mpds/v2/structure/curated</code></td>
      <td>Parsed <code>StructureData</code> that survived curation (no partial occupancies, no formula mismatch). All parsed structures also gain extras at this stage; only the clean subset is added to this group. Written by <a href="#curate"><code>mc3d-source curate</code></a>.</td>
    </tr>
    <tr>
      <td><code>mpds/v2/structure/final</code></td>
      <td>Reconciled structures for <code>v2</code>, with structures from <code>v1</code> carried over where possible. Only produced for re-imported databases. Written by <a href="#update"><code>mc3d-source update</code></a>.</td>
    </tr>
    <tr>
      <td><code>global/uniques/new</code></td>
      <td>Golden <code>StructureData</code> selected as the new MC3D set. Default name; configurable via <code>--new-uniques-group</code>. Written by <a href="#select"><code>mc3d-source select</code></a>.</td>
    </tr>
  </tbody>
</table>

Group labels are passed explicitly to every CLI command &mdash; the package does not assume any defaults.

### `StructureData` extras

After the `CifCleanWorkChain` runs and `curate`, every parsed `StructureData` carries extras from two sources: SeeKpath (via `aiida-codtools`) sets the structural / formula extras, and `mc3d-source curate` adds the provenance + curation flags.

#### Set by `aiida-codtools`

The `CifCleanWorkChain` calls the `primitive_structure_from_cif` calcfunction (in `aiida_codtools.calculations.functions.primitive_structure_from_cif`), which runs SeeKpath and attaches the following extras to the primitive `StructureData` it returns:

<table>
  <colgroup>
    <col style="width: 18em">
    <col>
  </colgroup>
  <thead>
    <tr><th>Extra (with type)</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><code>formula_hill</code><br>(<code>str</code>)</td>
      <td>Hill-notation chemical formula of the primitive cell.</td>
    </tr>
    <tr>
      <td><code>formula_hill_compact</code><br>(<code>str</code>)</td>
      <td>Hill-compact formula; used for the sort key by <code>uniq</code> along with the CIF space group number.</td>
    </tr>
    <tr>
      <td><code>chemical_system</code><br>(<code>str</code>)</td>
      <td>Hyphen-padded sorted set of element symbols, e.g. <code>-Fe-O-</code>. Used by <code>uniq</code>'s <code>--contains</code> / <code>--skip</code> filters and by <code>select</code>'s COD-hydrogen exclusion.</td>
    </tr>
    <tr>
      <td><code>spacegroup_international</code><br>(<code>str</code>)</td>
      <td>SeeKpath international space-group symbol.</td>
    </tr>
    <tr>
      <td><code>spacegroup_number</code><br>(<code>int</code>)</td>
      <td>SeeKpath space-group number. Read by <code>select</code> to populate the <code>spglib_space_group</code> field of <code>new-mc3d-data.json</code>. Distinct from <code>cif_spacegroup_number</code> (see below), which comes from the cleaned CIF.</td>
    </tr>
    <tr>
      <td><code>bravais_lattice</code><br>(<code>str</code>)</td>
      <td>SeeKpath Bravais-lattice short label.</td>
    </tr>
    <tr>
      <td><code>bravais_lattice_extended</code><br>(<code>str</code>)</td>
      <td>SeeKpath Bravais-lattice extended label.</td>
    </tr>
  </tbody>
</table>

These extras are present on every parsed `StructureData`, regardless of whether `curate` later admits it to the curated group.

#### Set by `mc3d-source curate`

<table>
  <colgroup>
    <col style="width: 18em">
    <col>
  </colgroup>
  <thead>
    <tr><th>Extra (with type)</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><code>source</code><br>(<code>dict</code> with keys <code>database</code>, <code>version</code>, <code>id</code>)</td>
      <td>Provenance of the structure in the upstream database. Copied from the raw <code>CifData</code>, mapping the upstream <code>db_name</code> to a short code: <code>Crystallography Open Database</code> &rarr; <code>cod</code>, <code>Icsd</code> &rarr; <code>icsd</code>, <code>Materials Platform for Data Science</code> &rarr; <code>mpds</code>.</td>
    </tr>
    <tr>
      <td><code>cif_spacegroup_number</code><br>(<code>int</code>)</td>
      <td>Used first as a sort key in the uniqueness analysis. Taken from the <code>spacegroup_numbers</code> attribute of the cleaned <code>CifData</code> produced by <code>CifCleanWorkChain</code>. Only set when the workflow reports exactly one space group.</td>
    </tr>
    <tr>
      <td><code>partial_occupancies</code><br>(<code>bool</code>)</td>
      <td>Flags non-stoichiometric structures. Set to <code>structure.is_alloy or structure.has_vacancies</code>.</td>
    </tr>
    <tr>
      <td><code>incorrect_formula</code><br>(<code>str</code>)</td>
      <td>Flags a formula mismatch between the cleaned CIF and the parsed structure. Set only when the <code>CifCleanWorkChain</code> exit code is one of: <code>430</code> &rarr; <code>missing_elements</code>, <code>431</code> &rarr; <code>different_comp</code>, <code>432</code> &rarr; <code>check_failed</code>.</td>
    </tr>
  </tbody>
</table>

#### Created later by `uniq`

Once a structure leaves the AiiDA database (i.e. is serialised to JSON), it is referred to by a "source string" of the form:

```
<database>|<version>|<id>
```

e.g. `cod|1521121|176429`. This is the canonical key used in all JSON outputs &mdash; the unique families file from `uniq`, the deprecation reports from `analyse`, the new MC3D data file from `select`, and the `duplicates` extras written back by `select`.

The string is constructed by `mc3d_source.tools.source.get_source_string`, which understands both the raw `CifData.source` format (`db_name` + `version` + `id`) and the curated extras format (`database` + `version` + `id`).

Source strings are first emitted by [`uniq`](#uniqueness): it groups curated `StructureData` into duplicate families and writes a JSON list of source-string lists. Subsequent stages consume that file by source string rather than by AiiDA UUID.

#### Added later by `select`

`select` writes a `duplicates` extra (`list[str]`) on each golden structure with the list of source strings that collapsed into it (excluding the golden source itself).

## Curate

`curate` takes a `CifCleanWorkChain` group (e.g. `mpds/v2/workchain/clean`) and writes results into a curated `StructureData` group (`curated_structure_group`, e.g. `mpds/v2/structure/curated`). See the [group labels table](#group-labels) for the full set of groups in play.

For each `CifCleanWorkChain` in the input group, `curate` adds the four extras described above to the parsed `StructureData`:

1. `source` from the raw CIF.
2. `cif_spacegroup_number` from the cleaned CIF (only if a single space group is reported).
3. `partial_occupancies` based on `is_alloy` / `has_vacancies`.
4. `incorrect_formula` based on the work chain exit status.

Stoichiometric structures without formula-mismatch issues are added to the curated group; the rest get the extras but stay out of the curated group. This way nothing is lost, but the curated group is exactly the set fit for uniqueness analysis.

## Update

`update` handles the case where you re-import a source database and want to fold the new import into the previous curated set without redoing the unique-family analysis from scratch.

It takes three group labels &mdash; `old_group`, `new_group`, and `target_group`. For the MPDS re-import these would be `mpds/v1/structure/curated`, `mpds/v2/structure/curated`, and `mpds/v2/structure/final` respectively. See the [group labels table](#group-labels) for context.

!!! warning

    The current logic was written for the MPDS, where every entry's `version` field is bumped on every import. For databases where only some entries change version (e.g. COD), the logic needs to be revisited.

The procedure has two steps:

1. **Import and process the new version.** Do a full `import`, run `CifCleanWorkChain` for all the new raw CIFs, then `curate` to obtain e.g. `mpds/v2/structure/curated`.
2. **Reconcile against the previous curated set.** For each `StructureData` in the new curated group:
    - If a structure with the same source ID is already in the target group, skip it (this makes `update` re-runnable on a partial target).
    - Else if no entry with the same source ID exists in the old curated group, take the new structure.
    - Else, compare the old and new structures via `StructureMatcher`: if they match, keep the **old** structure (preserves the older version string and avoids spurious churn); otherwise take the new structure.

The output goes into the target group (the "final" group for the new version, e.g. `mpds/v2/structure/final`).

This handles three real cases:

- Entry removed upstream &rarr; absent from `latest`, will be flagged later by `analyse id-removed`.
- Entry updated but structurally unchanged &rarr; old source is preserved.
- Entry updated and structurally different &rarr; the version string is bumped.

One case is **not** handled: when the new `CifCleanWorkChain` fails but the old one succeeded, we currently drop the entry even if the old version is still valid upstream. If this becomes important, the logic needs to consult the previous curated set as a fallback.

## Uniqueness

`uniq` collapses curated structures into duplicate families. The procedure:

1. **Pre-filter.** Skip structures whose extras include `incorrect_formula`. `--contains` / `--skip` options apply additional `chemical_system` filters at the query level.
2. **Sort key.** Each structure gets a key based on its Hill-compact formula and, by default, its space group number (taken from the `cif_spacegroup_number` extra or computed with `spglib` if missing). Structures with different keys can never match.
3. **Compare within a bucket.** For each bucket of structures sharing a key, run a similarity analysis via `pymatgen`'s `StructureMatcher`. Three methods are available:
    - `first` (default): walk the bucket linearly, comparing each structure against the existing representatives; the first matching representative absorbs it.
    - `seb`: build a full adjacency matrix and split into connected components.
    - `pymatgen`: defer to `StructureMatcher.group_structures`.
4. **Default matcher settings.** `ltol=0.2`, `stol=0.3`, `angle_tol=5`, `primitive_cell=False` (structures are already primitivised by the cleaning step), `scale=True`, `attempt_supercell=False`. Override with `--matcher-settings <yaml>`.
5. **Parallelism and checkpointing.** Buckets are processed in a `multiprocessing.Pool` of size `--parallelize` (default 5). If `--chunk-size` is set, partial results are written to `checkpoint.json` after each chunk and reloaded on the next run.

The output is `result.json`: a list of families, where each family is a list of source strings that ended up matching.

## Select

`select` turns the unique-families JSON into the final MC3D set. It needs three inputs:

- `unique_families.json` &mdash; output of `uniq`.
- The previous MC3D data file (`mc3d_id_file`), mapping MC3D IDs to their golden source and previous duplicate family.
- `deprecation.json` &mdash; output of `analyse` (see below).

The logic is:

1. **Re-use existing MC3D IDs.** For each old MC3D ID, find the new family/families that contain any of its previous family's sources. If exactly one new family lines up, the MC3D ID inherits it. If multiple new families match, families containing an existing "golden" source from any other MC3D entry are dropped from the candidate set, so two old MC3D entries don't end up pointing to the same new family.
2. **Drop fully deprecated MC3D IDs.** If none of the previous family's sources appear in any new family and every source in the previous family appears in `deprecation.json`, the MC3D ID is marked deprecated.
3. **Pick new families.** Families that no MC3D ID has inherited are candidates for new entries. Two filters apply: families with a "golden" source from a previous MC3D entry are skipped (handled by step 1), and families whose sources are **entirely** a subset of the COD-with-hydrogen set (curated COD structures with `partial_occupancies=False` whose `chemical_system` contains `-H-`) are skipped.
4. **Pick golden sources.** For each new family, pick one source as the golden structure with effective priority **MPDS &gt; ICSD &gt; COD**: the code assigns from each bucket in turn with plain `if` (not `elif`), so the last one set wins. (The inline comment in `select.py` calls this "by permissions"; the rationale is the license / accessibility hierarchy of the underlying databases.) The chosen source's `StructureData` becomes the golden structure for that family; all other sources are written to its `duplicates` extra.
5. **Persist.** The golden structures are collected into a new AiiDA group (default `global/uniques/new`) and the per-MC3D-ID data is written to `new-mc3d-data.json`. The output also includes a `spglib_space_group` field per golden structure, read from the SeeKpath-set `spacegroup_number` extra on the `StructureData` (see the [extras table](#set-by-aiida-codtools)).

## Deprecation

"Deprecating" a source or an MC3D ID means flagging it as no longer valid: it must be removed from the MC3D frontend and excluded from future uniqueness analyses.

### Source-level deprecation

The `analyse` subcommands populate a single `deprecation.json`, keyed by source string, with one of three reasons (defined in `mc3d_source.contants.SourceDeprecation`):

- `id_removed` &mdash; flagged by `analyse id-removed`, which takes an **old** and a **new raw `CifData` group** and writes the source strings whose IDs are present in the old group but not the new one. The stored source string is the old one (the one being removed).
- `structure_updated` &mdash; flagged by `analyse structure-updated`, which takes an **old curated structure group** and a **new "final" structure group** and writes the source strings whose ID is present in both but whose `version`/structure changed in the new group. The stored source string is the **old** one (the now-superseded version).
- `incorrect_formula` &mdash; flagged by `analyse incorrect-formula`, which scans **all `StructureData` in the AiiDA database** (no group filter) for the `incorrect_formula` extra set by `curate`. The stored source string is the affected structure's source.

Each subcommand merges its findings into the existing `deprecation.json` (if any), but the overlap policies differ:

- `id-removed`: silently overwrites existing keys with the new value.
- `structure-updated`: aborts (prints `Critical` and returns) if any keys overlap.
- `incorrect-formula`: prompts via `typer.confirm`; on confirm, silently overwrites.

The asymmetry is incidental and probably worth aligning.

### MC3D-ID-level deprecation

An MC3D ID is deprecated when **all** sources in its previous duplicate family are deprecated (see step 2 of [Select](#select)). If only some sources are deprecated &mdash; including the "golden" one &mdash; the MC3D ID is kept and a warning is surfaced on the frontend instead, so the entry remains findable.

