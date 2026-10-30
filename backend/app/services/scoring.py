import ast
import math
import operator
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.models import Tag, Task
from app.services.tags import ancestor_ids

DAY_SECONDS = 24 * 60 * 60
VARIABLES = {
    "priority",
    "ageDays",
    "idleDays",
    "dueOffsetDays",
    "hasDueDate",
    "tagValue",
}
DEFAULT_SCORING_FORMULA = (
    "priority * 25 + ageDays * 0.25 + idleDays * 1.0 + tagValue * 20 + "
    "((50 * exp(dueOffsetDays / 7) if dueOffsetDays < 0 else "
    "50 + dueOffsetDays * 20) if hasDueDate > 0 else 0)"
)

BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
COMPARE_OPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
FUNCTIONS = {"exp": math.exp}


class FormulaError(ValueError):
    pass


@dataclass(frozen=True)
class ScoringPlan:
    formula: str
    now: datetime
    warning: str | None = None


def _evaluate(node: ast.AST, values: dict[str, float]) -> float | bool:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in VARIABLES:
        return values[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        left = float(_evaluate(node.left, values))
        right = float(_evaluate(node.right, values))
        try:
            return BIN_OPS[type(node.op)](left, right)
        except (ArithmeticError, OverflowError) as error:
            raise FormulaError("Formula arithmetic failed") from error
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return UNARY_OPS[type(node.op)](float(_evaluate(node.operand, values)))
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left = float(_evaluate(node.left, values))
        right = float(_evaluate(node.comparators[0], values))
        operation = COMPARE_OPS.get(type(node.ops[0]))
        if operation is not None:
            return operation(left, right)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        results = [bool(_evaluate(value, values)) for value in node.values]
        return all(results) if isinstance(node.op, ast.And) else any(results)
    if isinstance(node, ast.IfExp):
        branch = node.body if bool(_evaluate(node.test, values)) else node.orelse
        return _evaluate(branch, values)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FUNCTIONS
        and len(node.args) == 1
        and not node.keywords
    ):
        argument = float(_evaluate(node.args[0], values))
        try:
            return FUNCTIONS[node.func.id](argument)
        except (ArithmeticError, OverflowError, ValueError) as error:
            raise FormulaError("Formula function failed") from error
    raise FormulaError("Formula contains an unsupported expression")


def evaluate_formula(formula: str, values: dict[str, float]) -> float:
    if not formula.strip() or len(formula) > 4000:
        raise FormulaError("Formula must contain between 1 and 4000 characters")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise FormulaError("Formula syntax is invalid") from error
    if sum(1 for _node in ast.walk(tree)) > 100:
        raise FormulaError("Formula is too complex")
    result = float(_evaluate(tree, values))
    if not math.isfinite(result):
        raise FormulaError("Formula must return a finite number")
    return result


def validate_formula(formula: str) -> None:
    examples = (
        {
            "priority": 1.0,
            "ageDays": 0.0,
            "idleDays": 0.0,
            "dueOffsetDays": 0.0,
            "hasDueDate": 0.0,
            "tagValue": 0.0,
        },
        {
            "priority": 3.0,
            "ageDays": 30.0,
            "idleDays": 7.0,
            "dueOffsetDays": 7.0,
            "hasDueDate": 1.0,
            "tagValue": -2.0,
        },
        {
            "priority": 2.0,
            "ageDays": 1.0,
            "idleDays": 0.0,
            "dueOffsetDays": -7.0,
            "hasDueDate": 1.0,
            "tagValue": 4.0,
        },
    )
    for values in examples:
        evaluate_formula(formula, values)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def score_variables(task: Task, now: datetime | None = None) -> dict[str, float]:
    now = now or datetime.now(UTC)
    created_at = _utc(task.created_at)
    last_worked_at = _utc(task.last_worked_at) if task.last_worked_at else created_at
    due_offset = float((now.astimezone().date() - task.due_date).days) if task.due_date else 0.0
    direct_ids = {tag.id for tag in task.tags}
    db = object_session(task)
    if db is not None and direct_ids:
        effective_ids = direct_ids | ancestor_ids(db, direct_ids)
        tag_value = sum(db.scalars(select(Tag.score_value).where(Tag.id.in_(effective_ids))))
    else:
        tag_value = sum(tag.score_value for tag in task.tags)
    return {
        "priority": float(task.priority),
        "ageDays": max(0.0, (now - created_at).total_seconds() / DAY_SECONDS),
        "idleDays": max(0.0, (now - last_worked_at).total_seconds() / DAY_SECONDS),
        "dueOffsetDays": due_offset,
        "hasDueDate": 1.0 if task.due_date else 0.0,
        "tagValue": float(tag_value),
    }


def score_task(task: Task, now: datetime | None = None, formula: str | None = None) -> float:
    if task.finished_at is not None:
        return 0.0
    if formula is None:
        formula = task.user.scoring_formula or DEFAULT_SCORING_FORMULA
    values = score_variables(task, now)
    return evaluate_formula(formula, values)


def plan_scoring(tasks: Iterable[Task], now: datetime | None = None) -> ScoringPlan:
    tasks = list(tasks)
    current_time = now or datetime.now(UTC)
    if not tasks:
        return ScoringPlan(DEFAULT_SCORING_FORMULA, current_time)
    custom_formula = tasks[0].user.scoring_formula
    if not custom_formula:
        return ScoringPlan(DEFAULT_SCORING_FORMULA, current_time)
    try:
        for task in tasks:
            score_task(task, current_time, custom_formula)
    except FormulaError as error:
        return ScoringPlan(
            DEFAULT_SCORING_FORMULA,
            current_time,
            f"Your scoring formula failed ({error}). "
            "All scores shown here use the default formula.",
        )
    return ScoringPlan(custom_formula, current_time)
