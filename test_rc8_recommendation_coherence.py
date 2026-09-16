from pathlib import Path

ROOT=Path(__file__).resolve().parent
SRC=(ROOT/'app.py').read_text(encoding='utf-8')


def section(a,b):
    i=SRC.index(a); j=SRC.index(b,i); return SRC[i:j]


def test_spot_and_futures_have_distinct_action_theses():
    bank=section("def _initialize_justification_bank", "# === FIN _initialize_justification_bank")
    assert "'tesis_compra_spot'" in bank and 'sin abrir una posición apalancada' in bank
    assert "'tesis_venta_spot'" in bank and 'no abre una posición SHORT' in bank
    assert "'tesis_long_futures'" in bank and 'FUTURES LONG' in bank
    assert "'tesis_short_futures'" in bank and 'FUTURES SHORT' in bank
    assert "'reflexion_compra_spot_oportunidad'" in bank
    assert "'reflexion_venta_spot_oportunidad'" in bank
    assert "'reflexion_long_oportunidad'" in bank
    assert "'reflexion_short_oportunidad'" in bank


def test_no_operar_esperar_caution_have_distinct_explanations():
    selector=section('def seleccionar_plantillas_por_condiciones', 'def _mapear_condiciones_activas')
    assert "'NO_OPERAR': 'tesis_no_operar'" in selector
    assert "'ESPERAR': 'tesis_esperar'" in selector
    assert "'CAUTION': 'tesis_caution'" in selector
    assert "generic_id = 'generica_esperar'" in selector
    assert "generic_id = 'generica_caution'" in selector
    assert "generic_id = 'generica_no_operar'" in selector
    assert 'La entrada queda pendiente porque' in selector
    assert 'La operación exige PRECAUCIÓN porque' in selector


def test_committee_reasons_are_filtered_for_final_action():
    helper=section('def _razones_consenso_coherentes', 'def seleccionar_plantillas_por_condiciones')
    assert "'NO_OPERAR': ('riesgo'" in helper
    assert "'COMPRA_SPOT': ('alcista'" in helper
    assert "'SHORT': ('bajista'" in helper
    generator=section('def generate_professional_message_with_consenso', 'def _get_sentiment_description')
    assert '_razones_consenso_coherentes(decision, razones_consenso' in generator
    assert 'Motivo de la compra Spot' in generator
    assert 'Motivo del SHORT Futures' in generator


def test_recommendation_labels_do_not_equate_spot_and_futures():
    bank=section("def _initialize_justification_bank", "# === FIN _initialize_justification_bank")
    assert 'COMPRA SPOT del ratio PAXG/BTC' in bank
    assert 'VENTA SPOT del ratio PAXG/BTC' in bank
    assert 'LONG FUTURES de {par}' in bank
    assert 'SHORT FUTURES de {par}' in bank
    assert "'recomendacion_no_operar'" in bank


def test_template_guard_blocks_spot_futures_semantic_crossovers():
    guard=section('def _plantilla_coherente_con_accion', 'def _razones_consenso_coherentes')
    assert "'COMPRA_SPOT': ('long futures'" in guard
    assert "'VENTA_SPOT': ('short futures'" in guard
    selector=section('def seleccionar_plantillas_por_condiciones', 'def _mapear_condiciones_activas')
    assert '_plantilla_coherente_con_accion(decision' in selector
