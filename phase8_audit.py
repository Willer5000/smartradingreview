"""
phase8_audit.py

FASE 8.1 — Auditoría de integridad SmartradingReview

Objetivo:
- detectar regresiones estructurales;
- comprobar sintaxis;
- comprobar que las protecciones 7D–7G siguen presentes;
- NO ejecutar mercado;
- NO ejecutar Flask;
- NO conectar Supabase;
- NO importar módulos de producción.

Se analiza únicamente el código fuente mediante:
    ast
    py_compile
    lectura de archivos locales
"""

from __future__ import annotations

import ast
import py_compile
import sys

from pathlib import Path
from typing import Dict, Optional, Set


ROOT = Path(__file__).resolve().parent


CORE_FILES = (
    "app.py",
    "review_trader.py",
    "futures_system.py",
    "portfolio_guardian.py",
    "saved_signals.py",
    "supabase_client.py",
)


passed = []
failed = []


def _pass(message: str) -> None:
    passed.append(message)
    print(
        f"✅ PASS — {message}"
    )


def _fail(
    message: str,
    detail: str = ""
) -> None:
    failed.append(
        (
            message,
            detail
        )
    )

    suffix = (
        f" | {detail}"
        if detail
        else ""
    )

    print(
        f"❌ FAIL — {message}{suffix}"
    )


def _check(
    condition: bool,
    message: str,
    detail: str = ""
) -> None:

    if condition:
        _pass(
            message
        )

    else:
        _fail(
            message,
            detail
        )


def _read(
    filename: str
) -> str:

    path = (
        ROOT
        / filename
    )

    return path.read_text(
        encoding="utf-8"
    )


def _tree(
    filename: str
) -> ast.AST:

    return ast.parse(
        _read(
            filename
        ),
        filename=filename
    )


def _function_names(
    tree: ast.AST
) -> Set[str]:

    names = set()

    for node in ast.walk(
        tree
    ):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        ):

            names.add(
                node.name
            )

    return names


def _numeric_assignment(
    tree: ast.AST,
    name: str
) -> Optional[float]:
    """
    Busca:
        VARIABLE = numero

    Funciona tanto a nivel global como dentro de clases.
    """

    for node in ast.walk(
        tree
    ):

        target_name = None
        value_node = None

        if isinstance(
            node,
            ast.Assign
        ):

            if len(
                node.targets
            ) != 1:

                continue

            target = (
                node.targets[0]
            )

            if isinstance(
                target,
                ast.Name
            ):

                target_name = (
                    target.id
                )

                value_node = (
                    node.value
                )

        elif isinstance(
            node,
            ast.AnnAssign
        ):

            if isinstance(
                node.target,
                ast.Name
            ):

                target_name = (
                    node.target.id
                )

                value_node = (
                    node.value
                )

        if (
            target_name != name
            or value_node is None
        ):

            continue

        try:

            value = (
                ast.literal_eval(
                    value_node
                )
            )

            if isinstance(
                value,
                (
                    int,
                    float
                )
            ):

                return float(
                    value
                )

        except Exception:

            continue

    return None


def section(
    title: str
) -> None:

    print(
        "\n"
        + "=" * 72
    )

    print(
        title
    )

    print(
        "=" * 72
    )


# ============================================================================
# 1. ARCHIVOS + SINTAXIS
# ============================================================================

section(
    "1. ARCHIVOS Y SINTAXIS"
)


trees: Dict[
    str,
    ast.AST
] = {}

sources: Dict[
    str,
    str
] = {}


for filename in CORE_FILES:

    path = (
        ROOT
        / filename
    )

    if not path.exists():

        _fail(
            f"{filename} existe",
            "archivo ausente"
        )

        continue

    _pass(
        f"{filename} existe"
    )

    try:

        py_compile.compile(
            str(
                path
            ),
            doraise=True
        )

        _pass(
            f"{filename} compila"
        )

    except Exception as exc:

        _fail(
            f"{filename} compila",
            str(
                exc
            )
        )

    try:

        source = (
            _read(
                filename
            )
        )

        tree = (
            ast.parse(
                source,
                filename=filename
            )
        )

        sources[
            filename
        ] = source

        trees[
            filename
        ] = tree

        _pass(
            f"{filename} AST válido"
        )

    except Exception as exc:

        _fail(
            f"{filename} AST válido",
            str(
                exc
            )
        )


# ============================================================================
# 2. FASE 7D
# ============================================================================

section(
    "2. FASE 7D — MFE / MAE / EARLY EXIT"
)


saved_tree = trees.get(
    "saved_signals.py"
)

saved_source = sources.get(
    "saved_signals.py",
    ""
)

review_tree = trees.get(
    "review_trader.py"
)

review_source = sources.get(
    "review_trader.py",
    ""
)


if saved_tree:

    saved_functions = (
        _function_names(
            saved_tree
        )
    )

    required_saved = (
        "get_saved_signal",
        "update_saved_signal",
        "_calculate_open_excursions",
        "_calculate_trade_r",
        "_build_early_exit_comparison",
        "_observe_early_exit_shadow",
        "_build_early_exit_learning_summary",
        "evaluate_saved_signals",
    )

    for name in required_saved:

        _check(
            name
            in saved_functions,
            f"saved_signals.{name} existe"
        )

    max_wait = (
        _numeric_assignment(
            saved_tree,
            "SAVED_SIGNAL_MAX_WAIT_BARS"
        )
    )

    _check(
        max_wait == 6.0,
        "vigencia señal guardada = 6 velas",
        f"actual={max_wait}"
    )

    # ==============================================================
    # EARLY EXIT DEBE EVALUARSE EN:
    #
    # manual
    # LONG SL
    # LONG TP
    # SHORT SL
    # SHORT TP
    #
    # + la propia definición de la función.
    #
    # Por tanto esperamos al menos 6 apariciones.
    # ==============================================================

    comparison_count = (
        saved_source.count(
            "_build_early_exit_comparison("
        )
    )

    _check(
        comparison_count >= 6,
        "Early Exit cubre todos los cierres",
        (
            "esperado >= 6 apariciones; "
            f"actual={comparison_count}"
        )
    )

    # Verificación específica de SHORT TP.
    short_tp_marker = (
        "elif low <= tp:"
    )

    short_tp_index = (
        saved_source.find(
            short_tp_marker
        )
    )

    if short_tp_index >= 0:

        short_tp_window = (
            saved_source[
                short_tp_index:
                short_tp_index
                + 3000
            ]
        )

        _check(
            "_build_early_exit_comparison"
            in short_tp_window,
            "SHORT TP evalúa Early Exit"
        )

    else:

        _fail(
            "SHORT TP evalúa Early Exit",
            "no se encontró 'elif low <= tp:'"
        )


if review_tree:

    review_functions = (
        _function_names(
            review_tree
        )
    )

    _check(
        "_check_tp_sl_hit"
        in review_functions,
        "ReviewTrader conserva evaluación TP/SL"
    )

    _check(
        "_get_previous_candle_timestamp"
        in review_functions,
        "ReviewTrader conserva vela anterior"
    )

    _check(
        "return times[-2]"
        in review_source,
        "ReviewTrader usa realmente la penúltima vela"
    )


# ============================================================================
# 3. FASE 7E
# ============================================================================

section(
    "3. FASE 7E — EXECUTION SAFETY"
)


futures_tree = trees.get(
    "futures_system.py"
)

futures_source = sources.get(
    "futures_system.py",
    ""
)


if review_tree:

    review_functions = (
        _function_names(
            review_tree
        )
    )

    for name in (
        "_build_execution_safety_calibration",
        "_build_execution_safety_shadow_policy",
        "get_execution_safety_operational_policy",
    ):

        _check(
            name
            in review_functions,
            f"ReviewTrader.{name} existe"
        )


if futures_tree:

    futures_functions = (
        _function_names(
            futures_tree
        )
    )

    _check(
        "_mark_levels_non_executable"
        in futures_functions,
        "Futures conserva niveles en ANALYSIS_ONLY"
    )

    _check(
        "'minimum_execution_safety': 65.0"
        in futures_source,
        "Execution Safety base permanece en 65"
    )

    _check(
        "execution_safety=leverage_safety_score"
        in futures_source,
        "leverage utiliza Safety protegido"
    )

    _check(
        "leverage_safety_score = min("
        in futures_source,
        "Safety aprendido no puede bonificar leverage"
    )


# ============================================================================
# 4. FASE 7F
# ============================================================================

section(
    "4. FASE 7F — ROTACIÓN TGP"
)


guardian_tree = trees.get(
    "portfolio_guardian.py"
)


if guardian_tree:

    guardian_functions = (
        _function_names(
            guardian_tree
        )
    )

    for name in (
        "_apply_rotation_anti_whipsaw",
        "_build_gradual_btc_reentry_plan",
        "_ensure_rotation_state_loaded",
        "_persist_rotation_state_if_dirty",
        "_rotation_memory_contradicts_portfolio",
    ):

        _check(
            name
            in guardian_functions,
            f"PortfolioGuardian.{name} existe"
        )

    guardian_expected_constants = {
        "ROTATION_COOLDOWN_MINUTES":
            240.0,

        "REVERSAL_MIN_TIMEFRAMES":
            3.0,

        "REVERSAL_EDGE_THRESHOLD":
            28.0,

        "BTC_REENTRY_STAGE_1_MAX_PCT":
            0.08,

        "BTC_REENTRY_STAGE_2_MAX_PCT":
            0.15,

        "BTC_REENTRY_STAGE_3_MAX_PCT":
            0.25,
    }

    for (
        name,
        expected
    ) in guardian_expected_constants.items():

        actual = (
            _numeric_assignment(
                guardian_tree,
                name
            )
        )

        _check(
            actual == expected,
            f"{name} = {expected}",
            f"actual={actual}"
        )


supabase_tree = trees.get(
    "supabase_client.py"
)


if supabase_tree:

    supabase_functions = (
        _function_names(
            supabase_tree
        )
    )

    _check(
        "get_user_rotation_state"
        in supabase_functions,
        "persistencia TGP puede restaurarse"
    )

    _check(
        "update_user_rotation_state"
        in supabase_functions,
        "persistencia TGP puede actualizarse"
    )


# ============================================================================
# 5. FASE 7G
# ============================================================================

section(
    "5. FASE 7G — RECURSOS / VIGENCIA / CONCURRENCIA"
)


app_tree = trees.get(
    "app.py"
)

app_source = sources.get(
    "app.py",
    ""
)


if app_tree:

    app_functions = (
        _function_names(
            app_tree
        )
    )

    _check(
        "_analysis_cache_purge_expired_locked"
        in app_functions,
        "7G.1 purga caché expirado"
    )

    _check(
        "_run_previous_signals_background"
        in app_functions,
        "previous_signals corre en background"
    )

    _check(
        "_trigger_futures_refresh_async"
        in app_functions,
        "Futures refresh corre en background"
    )

    _check(
        "_HEAVY_ANALYSIS_LOCK"
        in app_source,
        "7G.3 coordinador pesado existe"
    )

    _check(
        "if len(_ANALYSIS_CACHE) > 20:"
        in app_source,
        "caché pesado limitado a 20 entradas"
    )

    _check(
        "FASE 7G.2 — VIGENCIA REAL DE LA VELA ANTERIOR"
        in app_source,
        "Spot controla vigencia de vela anterior"
    )

    _check(
        "FASE 7G.2 — VIGENCIA DE VELA ANTERIOR FUTURES"
        in app_source,
        "Futures controla vigencia de vela anterior"
    )


# ============================================================================
# RESULTADO FINAL
# ============================================================================

section(
    "RESULTADO FASE 8.1"
)


total = (
    len(
        passed
    )
    +
    len(
        failed
    )
)


print(
    f"\nPruebas totales: {total}"
)

print(
    f"PASS: {len(passed)}"
)

print(
    f"FAIL: {len(failed)}"
)


if failed:

    print(
        "\n❌ AUDITORÍA NO APROBADA"
    )

    print(
        "\nFallos:"
    )

    for (
        index,
        (
            message,
            detail
        )
    ) in enumerate(
        failed,
        start=1
    ):

        if detail:

            print(
                f"  {index}. "
                f"{message} "
                f"→ {detail}"
            )

        else:

            print(
                f"  {index}. "
                f"{message}"
            )

    sys.exit(
        1
    )


print(
    "\n✅ AUDITORÍA 8.1 APROBADA"
)

print(
    "Las invariantes estructurales críticas "
    "de Fases 7D–7G permanecen presentes."
)

sys.exit(
    0
)
