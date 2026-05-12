[![Templated from python-copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mbercx/python-copier/refs/heads/main/docs/img/badge.json)](https://github.com/mbercx/python-copier)

# `mc3d-source`

Code for the [MC3D](https://mc3d.materialscloud.org/) source pipeline: the workflow that turns raw CIF dumps from external crystal structure databases (COD, ICSD, MPDS) into the unique, curated set of structures that seed all MC3D calculations.

For the scientific context, see the MC3D website and the accompanying paper in *Digital Discovery* ([Huber et al., 2026](https://pubs.rsc.org/en/content/articlelanding/2026/dd/d5dd00415b)).

## What it does

The package provides a single CLI, `mc3d-source`, that drives the pipeline in stages:

1. **`import`** &mdash; fetch raw CIFs from a source database into AiiDA.
2. *(Cleaning step.)* The raw `CifData` are processed by `CifCleanWorkChain` runs, submitted in batch from the separate runner in `pipeline/cif_clean/` (not part of the installed package).
3. **`curate`** &mdash; from a group of completed `CifCleanWorkChain`, attach source/spacegroup/formula extras to the parsed `StructureData` and collect the clean ones into a curated group.
4. **`update`** &mdash; when re-importing an updated version of a source database, reconcile the new curated set against the previous one (keep old structure when unchanged, take new when geometry differs, drop entries removed upstream).
5. **`analyse`** &mdash; produce the per-source deprecation report (`id_removed`, `structure_updated`, `incorrect_formula`) consumed by `select`.
6. **`uniq`** &mdash; deduplicate structures across sources via `pymatgen`'s `StructureMatcher`, emit unique families as JSON.
7. **`select`** &mdash; pick the final MC3D structures from the unique families, taking the previous MC3D set and the deprecation report into account.

## Install

Requires Python 3.9+ and a working AiiDA setup. Install from source:

```bash
git clone https://github.com/mbercx/mc3d-source.git
cd mc3d-source
pip install -e .
```

For development (docs, tests, pre-commit), use the `dev` dependency group or `hatch`. See [the developer guide](https://mbercx.github.io/mc3d-source/developer/).

## Usage

```bash
mc3d-source --help
```

Full documentation: <https://mbercx.github.io/mc3d-source/>.

## License

MIT &mdash; see [`LICENSE`](LICENSE).
