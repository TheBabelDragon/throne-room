"""Duck proof-workbench — typed mathematical state sitting on MetaField."""

from qwuack.workbench.checker import CheckerCertificate, issue_certificate, verify_certificate
from qwuack.workbench.desk import DuckDesk
from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind
from qwuack.workbench.registry import BY_ID, MILLENNIUM, ProblemSpec, get_problem
from qwuack.workbench.store import ObjectStore
from qwuack.workbench.victory import VictoryCertificate, VictoryVerdict, admit_victory, evaluate_victory
from qwuack.workbench.workers import Workbench

__all__ = [
    "BY_ID",
    "CheckerCertificate",
    "ClaimStatus",
    "DuckDesk",
    "MILLENNIUM",
    "MathObject",
    "ObjectKind",
    "ObjectStore",
    "ProblemSpec",
    "VictoryCertificate",
    "VictoryVerdict",
    "Workbench",
    "admit_victory",
    "evaluate_victory",
    "get_problem",
    "issue_certificate",
    "verify_certificate",
]
