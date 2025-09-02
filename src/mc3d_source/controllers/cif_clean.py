"""SubmissionController for submitting the `CifCleanWorkChain`."""

from __future__ import annotations

from aiida import orm
from aiida_codtools.common.resources import get_default_options
from aiida_codtools.common.utils import get_input_node
from aiida_codtools.workflows.cif_clean import CifCleanWorkChain
from aiida_submission_controller import FromGroupSubmissionController


class CifCleanController(FromGroupSubmissionController):
    """SubmissionController for submitting the `CifCleanWorkChain`."""

    cif_filter_code: str
    cif_select_code: str
    clean_structure_group: str | None = None
    clean_cif_group: str | None = None

    def get_inputs_and_processclass_from_extras(self, extras_values):
        """Return inputs and process class for the submission of this specific process."""

        parent_node = self.get_parent_node_from_extras(extras_values)

        if isinstance(parent_node, orm.CifData):
            cif = parent_node
        else:
            msg = f"Node {parent_node} from parent group is of incorrect type: {type(parent_node)}."
            raise TypeError(msg)

        node_cif_filter_parameters = get_input_node(
            orm.Dict,
            {
                "fix-syntax-errors": True,
                "use-c-parser": True,
                "use-datablocks-without-coordinates": True,
            },
        )
        node_cif_select_parameters = get_input_node(
            orm.Dict,
            {
                "canonicalize-tag-names": True,
                "dont-treat-dots-as-underscores": True,
                "invert": True,
                "tags": "_publ_author_name,_citation_journal_abbrev",
                "use-c-parser": True,
            },
        )
        inputs = {
            "cif": cif,
            "cif_filter": {
                "code": orm.load_code(self.cif_filter_code),
                "parameters": node_cif_filter_parameters,
                "metadata": {"options": get_default_options()},
            },
            "cif_select": {
                "code": orm.load_code(self.cif_select_code),
                "parameters": node_cif_select_parameters,
                "metadata": {"options": get_default_options()},
            },
            "parse_engine": "pymatgen",
            "site_tolerance": 5e-4,
            "symprec": 5e-3,
            "skip_formula_check": False,
        }
        if self.clean_cif_group is not None:
            inputs["group_cif"] = orm.load_group(self.clean_cif_group)
        if self.clean_structure_group is not None:
            inputs["group_structure"] = orm.load_group(self.clean_structure_group)

        builder = CifCleanWorkChain.get_builder()
        builder._update(inputs)  # noqa: SLF001

        return builder
