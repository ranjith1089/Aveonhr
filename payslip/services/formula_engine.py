"""Safe, Decimal-only formula evaluator for configurable payroll components.

Formulas are authored as data (never code) and evaluated here without
`eval()`. Each formula is parsed with the stdlib `ast` module and only a
strict whitelist of nodes is allowed:

    - numeric literals
    - names: other component codes and the context variables below
    - + - * / and unary minus, parentheses
    - comparisons (< <= > >= == !=) and and/or/not
    - a fixed function set: ROUND(x, n), ROUNDUP(x, n), ROUNDDOWN(x, n),
      MIN(...), MAX(...), IF(cond, a, b)

Anything else - attribute access, arbitrary calls, subscripts, lambdas,
comprehensions - raises FormulaError. All arithmetic is done in Decimal.

Context variables exposed to every formula (mirroring the legacy
compute_entry inputs):

    PACKAGE, TWD, PAY_DAYS, PRESENT_DAYS, LOP_DAYS, EMP_LEAVE_DAYS,
    INTERNET, ARREAR, ADVANCE, TDS, IS_ESI, IS_PF

Booleans are represented as Decimal 1 / 0 so they compose with arithmetic.
"""
from __future__ import annotations

import ast
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

# Context-variable names available inside every formula. Kept as a frozenset
# so callers and the validator agree on what's legal without a component code.
CONTEXT_VARS = frozenset({
    "PACKAGE", "TWD", "PAY_DAYS", "PRESENT_DAYS", "LOP_DAYS", "EMP_LEAVE_DAYS",
    "INTERNET", "ARREAR", "ADVANCE", "TDS", "IS_ESI", "IS_PF",
})

_ONE = Decimal("1")
_ZERO = Decimal("0")


class FormulaError(ValueError):
    """Raised for an unparseable, unsafe, or unresolvable formula."""


def _d(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return _ONE if value else _ZERO
    return Decimal(str(value))


def _rounded(value: Decimal, places) -> Decimal:
    places = int(places)
    quant = Decimal(1) if places <= 0 else Decimal(1).scaleb(-places)
    return _d(value).quantize(quant, rounding=ROUND_HALF_UP)


def _round_up(value: Decimal, places=0) -> Decimal:
    places = int(places)
    quant = Decimal(1) if places <= 0 else Decimal(1).scaleb(-places)
    return _d(value).quantize(quant, rounding=ROUND_CEILING)


def _round_down(value: Decimal, places=0) -> Decimal:
    places = int(places)
    quant = Decimal(1) if places <= 0 else Decimal(1).scaleb(-places)
    return _d(value).quantize(quant, rounding=ROUND_FLOOR)


def _fn_if(cond, a, b):
    return _d(a) if _d(cond) != _ZERO else _d(b)


# name -> (callable, arity check). Arity is validated at call time for a
# friendly error rather than a Python TypeError.
FUNCTIONS = {
    "ROUND": (_rounded, (1, 2)),
    "ROUNDUP": (_round_up, (1, 2)),
    "ROUNDDOWN": (_round_down, (1, 2)),
    "MIN": (lambda *xs: min(_d(x) for x in xs), (1, None)),
    "MAX": (lambda *xs: max(_d(x) for x in xs), (1, None)),
    "IF": (_fn_if, (3, 3)),
}


# --- static reference extraction (for dependency graph + validation) -------

def referenced_names(formula: str) -> set[str]:
    """Every bare Name in the expression (component codes + context vars +
    function names). Raises FormulaError if the text won't even parse."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Could not parse formula: {exc.msg}") from exc
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def component_dependencies(formula: str, known_codes: set[str]) -> set[str]:
    """Just the referenced names that are other component codes (i.e. not a
    context var and not a function name) - the edges of the dependency graph."""
    names = referenced_names(formula)
    return {n for n in names if n in known_codes}


def validate_formula(formula: str, known_codes: set[str]) -> None:
    """Static check used by the structure editor before saving. Confirms the
    formula parses, uses only whitelisted constructs, and references only
    known component codes / context vars / functions. Does NOT detect
    cycles - that needs the whole component set (see order_components)."""
    _compile(formula)  # raises on unsafe nodes
    for name in referenced_names(formula):
        if name in FUNCTIONS or name in CONTEXT_VARS or name in known_codes:
            continue
        raise FormulaError(
            f"Unknown reference '{name}'. Use a component code, a context "
            f"variable, or a supported function.")


# --- evaluation ------------------------------------------------------------

def _compile(formula: str) -> ast.Expression:
    """Parse and reject any node outside the safe whitelist."""
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Could not parse formula: {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
            ast.Name, ast.Load, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
            ast.And, ast.Or, ast.Not,
            ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
        )):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise FormulaError("Only ROUND, ROUNDUP, ROUNDDOWN, MIN, MAX "
                                   "and IF may be called in a formula.")
            if node.keywords:
                raise FormulaError("Formula functions take positional arguments only.")
            continue
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise FormulaError("Only numbers are allowed as literals.")
        raise FormulaError(
            f"'{type(node).__name__}' is not allowed in a formula.")
    return tree


def evaluate(formula: str, context: dict) -> Decimal:
    """Evaluate a single formula against a fully-populated context dict
    (context vars + already-computed component codes -> Decimal)."""
    tree = _compile(formula)
    return _d(_eval_node(tree.body, context))


def _eval_node(node, ctx):
    if isinstance(node, ast.Constant):
        return _d(node.value)
    if isinstance(node, ast.Name):
        if node.id not in ctx:
            raise FormulaError(f"'{node.id}' has no value at evaluation time.")
        return _d(ctx[node.id])
    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand, ctx)
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return val
        if isinstance(node.op, ast.Not):
            return _ONE if val == _ZERO else _ZERO
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == _ZERO:
                return _ZERO  # payroll convention: divide-by-zero -> 0, not error
            return left / right
    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return _ONE if all(v != _ZERO for v in vals) else _ZERO
        if isinstance(node.op, ast.Or):
            return _ONE if any(v != _ZERO for v in vals) else _ZERO
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        result = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, ctx)
            result = result and _compare(op, left, right)
            left = right
        return _ONE if result else _ZERO
    if isinstance(node, ast.Call):
        fn, arity = FUNCTIONS[node.func.id]
        args = [_eval_node(a, ctx) for a in node.args]
        _check_arity(node.func.id, len(args), arity)
        return _d(fn(*args))
    raise FormulaError(f"Cannot evaluate node '{type(node).__name__}'.")


def _compare(op, left, right) -> bool:
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    raise FormulaError("Unsupported comparison.")


def _check_arity(name, count, arity):
    low, high = arity
    if count < low or (high is not None and count > high):
        want = f"{low}" if low == high else (
            f"at least {low}" if high is None else f"{low}-{high}")
        raise FormulaError(f"{name} expects {want} argument(s), got {count}.")


# --- dependency ordering + cycle detection ---------------------------------

def order_components(edges: dict[str, set[str]]) -> list[str]:
    """Topologically sort component codes so every code comes after the codes
    it depends on. `edges[code]` is the set of component codes that `code`
    references. Raises FormulaError naming a cycle if one exists.

    Deterministic: ties broken alphabetically so output is stable for tests.
    """
    ordered: list[str] = []
    # states: 0 = unvisited, 1 = on the current DFS path, 2 = done
    state = {code: 0 for code in edges}

    def visit(code, trail):
        st = state.get(code, 0)
        if st == 2:
            return
        if st == 1:
            cycle = " -> ".join(trail[trail.index(code):] + [code])
            raise FormulaError(f"Circular reference detected: {cycle}")
        state[code] = 1
        for dep in sorted(edges.get(code, ())):
            if dep in edges:  # ignore edges to context vars / unknowns
                visit(dep, trail + [code])
        state[code] = 2
        ordered.append(code)

    for code in sorted(edges):
        visit(code, [])
    return ordered
