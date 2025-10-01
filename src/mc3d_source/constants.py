from enum import Enum


class SourceDeprecation(str, Enum):
    ID_REMOVED = "id_removed"
    STRUCTURE_UPDATED = "structure_updated"
    INCORRECT_FORMULA = "incorrect_formula"


DEPRECATION_HELP = {
    SourceDeprecation.ID_REMOVED: "The corresponding ID has been removed from the source database.",
    SourceDeprecation.STRUCTURE_UPDATED: (
        "The corresponding ID has a different structure in a newer version of the database"
    ),
    SourceDeprecation.INCORRECT_FORMULA: (
        "The structure of the corresponding ID had a formula mismatch between the cleaned CIF "
        "and the parsed structure."
    ),
}
