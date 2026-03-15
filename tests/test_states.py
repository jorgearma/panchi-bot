"""
Tests de la máquina de estados: funciones puras, sin dependencias externas.
"""
import json
import pytest
from states import (
    EstadoRegistro,
    EstadoPedido,
    TRANSICIONES_PEDIDO,
    TRANSICIONES_REGISTRO,
    transicion_valida_pedido,
    transicion_valida_registro,
)


# ---------------------------------------------------------------------------
# EstadoPedido — valores y serialización
# ---------------------------------------------------------------------------

class TestEstadoPedidoEnum:
    def test_valores_string(self):
        assert EstadoPedido.PENDIENTE == "Pendiente"
        assert EstadoPedido.ENLACE == "enlace"
        assert EstadoPedido.ENLACE2 == "enlace2"
        assert EstadoPedido.CONFIRMANDO_PAGO == "confirmando-pago"
        assert EstadoPedido.PAGADO == "pagado"

    def test_comparacion_con_string_plano(self):
        """str,Enum: el valor devuelto por la DB (string) debe igualar al enum."""
        assert "Pendiente" == EstadoPedido.PENDIENTE
        assert "confirmando-pago" == EstadoPedido.CONFIRMANDO_PAGO

    def test_serializable_json(self):
        """json.dumps debe serializar los miembros como strings, no como 'EstadoPedido.X'."""
        resultado = json.dumps({"estado": EstadoPedido.PENDIENTE})
        assert resultado == '{"estado": "Pendiente"}'

    def test_construccion_desde_string(self):
        assert EstadoPedido("Pendiente") is EstadoPedido.PENDIENTE
        assert EstadoPedido("confirmando-pago") is EstadoPedido.CONFIRMANDO_PAGO

    def test_construccion_desde_string_invalido(self):
        with pytest.raises(ValueError):
            EstadoPedido("estado_inexistente")


# ---------------------------------------------------------------------------
# EstadoRegistro — valores y serialización
# ---------------------------------------------------------------------------

class TestEstadoRegistroEnum:
    def test_valores_string(self):
        assert EstadoRegistro.SALUDO_INICIAL == "saludo_inicial"
        assert EstadoRegistro.ESPERANDO_CONFIRMACION == "esperando_confirmacion"
        assert EstadoRegistro.ESPERANDO_NOMBRE == "esperando_nombre"
        assert EstadoRegistro.ESPERANDO_DIRECCION == "esperando_direccion"
        assert EstadoRegistro.CONFIRMANDO_DIRECCION == "confirmando_direccion"

    def test_serializable_json(self):
        resultado = json.dumps({"estado": EstadoRegistro.SALUDO_INICIAL})
        assert resultado == '{"estado": "saludo_inicial"}'

    def test_comparacion_con_string_plano(self):
        """El valor leído de Redis (string) debe igualar al enum."""
        assert "saludo_inicial" == EstadoRegistro.SALUDO_INICIAL


# ---------------------------------------------------------------------------
# transicion_valida_pedido — camino feliz
# ---------------------------------------------------------------------------

class TestTransicionValidaPedidoHappyPath:
    def test_pendiente_a_enlace(self):
        assert transicion_valida_pedido(EstadoPedido.PENDIENTE, EstadoPedido.ENLACE)

    def test_enlace_a_enlace2(self):
        assert transicion_valida_pedido(EstadoPedido.ENLACE, EstadoPedido.ENLACE2)

    def test_enlace2_a_confirmando_pago(self):
        assert transicion_valida_pedido(EstadoPedido.ENLACE2, EstadoPedido.CONFIRMANDO_PAGO)

    def test_confirmando_pago_a_pagado(self):
        assert transicion_valida_pedido(EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.PAGADO)

    def test_enlace_a_pendiente_rollback_error(self):
        """Rollback de error interno cuando falla guardar_enlace."""
        assert transicion_valida_pedido(EstadoPedido.ENLACE, EstadoPedido.PENDIENTE)

    def test_enlace2_a_enlace_boton_atras(self):
        """Navegación UI: botón atrás en confirmacion_pago.html."""
        assert transicion_valida_pedido(EstadoPedido.ENLACE2, EstadoPedido.ENLACE)

    def test_acepta_strings_planos_como_origen(self):
        """El estado_actual llega como string desde la DB, no como enum."""
        assert transicion_valida_pedido("Pendiente", EstadoPedido.ENLACE)
        assert transicion_valida_pedido("enlace2", EstadoPedido.CONFIRMANDO_PAGO)


# ---------------------------------------------------------------------------
# transicion_valida_pedido — transiciones inválidas bloqueadas
# ---------------------------------------------------------------------------

class TestTransicionValidaPedidoInvalidas:
    def test_saltar_estados(self):
        assert not transicion_valida_pedido(EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMANDO_PAGO)
        assert not transicion_valida_pedido(EstadoPedido.PENDIENTE, EstadoPedido.PAGADO)
        assert not transicion_valida_pedido(EstadoPedido.ENLACE, EstadoPedido.PAGADO)

    def test_pagado_es_terminal(self):
        assert not transicion_valida_pedido(EstadoPedido.PAGADO, EstadoPedido.ENLACE)
        assert not transicion_valida_pedido(EstadoPedido.PAGADO, EstadoPedido.PENDIENTE)
        assert not transicion_valida_pedido(EstadoPedido.PAGADO, EstadoPedido.CONFIRMANDO_PAGO)

    def test_confirmando_pago_no_retrocede(self):
        assert not transicion_valida_pedido(EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.ENLACE)
        assert not transicion_valida_pedido(EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.ENLACE2)

    def test_estado_origen_desconocido(self):
        """Un valor legacy en BD que no esté en el enum debe bloquear la transición."""
        assert not transicion_valida_pedido("estado_legacy_desconocido", EstadoPedido.ENLACE)
        assert not transicion_valida_pedido("", EstadoPedido.ENLACE)

    def test_nuevo_estado_desconocido(self):
        assert not transicion_valida_pedido(EstadoPedido.PENDIENTE, "inventado")


# ---------------------------------------------------------------------------
# transicion_valida_registro — camino feliz
# ---------------------------------------------------------------------------

class TestTransicionValidaRegistroHappyPath:
    def test_flujo_completo_hacia_adelante(self):
        assert transicion_valida_registro(EstadoRegistro.SALUDO_INICIAL, EstadoRegistro.ESPERANDO_CONFIRMACION)
        assert transicion_valida_registro(EstadoRegistro.ESPERANDO_CONFIRMACION, EstadoRegistro.ESPERANDO_NOMBRE)
        assert transicion_valida_registro(EstadoRegistro.ESPERANDO_NOMBRE, EstadoRegistro.ESPERANDO_DIRECCION)
        assert transicion_valida_registro(EstadoRegistro.ESPERANDO_DIRECCION, EstadoRegistro.CONFIRMANDO_DIRECCION)

    def test_rollback_direccion(self):
        """El usuario dice 'no' a la dirección sugerida → vuelve a pedirla."""
        assert transicion_valida_registro(EstadoRegistro.CONFIRMANDO_DIRECCION, EstadoRegistro.ESPERANDO_DIRECCION)

    def test_acepta_strings_planos_como_origen(self):
        assert transicion_valida_registro("saludo_inicial", EstadoRegistro.ESPERANDO_CONFIRMACION)
        assert transicion_valida_registro("confirmando_direccion", EstadoRegistro.ESPERANDO_DIRECCION)


# ---------------------------------------------------------------------------
# transicion_valida_registro — transiciones inválidas bloqueadas
# ---------------------------------------------------------------------------

class TestTransicionValidaRegistroInvalidas:
    def test_saltar_estados(self):
        assert not transicion_valida_registro(EstadoRegistro.SALUDO_INICIAL, EstadoRegistro.CONFIRMANDO_DIRECCION)
        assert not transicion_valida_registro(EstadoRegistro.ESPERANDO_CONFIRMACION, EstadoRegistro.ESPERANDO_DIRECCION)

    def test_no_retroceder_desde_nombre(self):
        assert not transicion_valida_registro(EstadoRegistro.ESPERANDO_NOMBRE, EstadoRegistro.ESPERANDO_CONFIRMACION)

    def test_estado_origen_desconocido(self):
        assert not transicion_valida_registro("estado_inventado", EstadoRegistro.ESPERANDO_NOMBRE)
        assert not transicion_valida_registro("", EstadoRegistro.ESPERANDO_CONFIRMACION)

    def test_nuevo_estado_desconocido(self):
        assert not transicion_valida_registro(EstadoRegistro.SALUDO_INICIAL, "inventado")


# ---------------------------------------------------------------------------
# Cobertura de los mapas — integridad declarativa
# ---------------------------------------------------------------------------

class TestMapasTransicion:
    def test_todos_los_estados_pedido_tienen_entrada(self):
        """Ningún EstadoPedido debe quedar fuera del mapa."""
        for estado in EstadoPedido:
            assert estado in TRANSICIONES_PEDIDO, f"{estado} no tiene entrada en TRANSICIONES_PEDIDO"

    def test_todos_los_estados_registro_tienen_entrada(self):
        for estado in EstadoRegistro:
            assert estado in TRANSICIONES_REGISTRO, f"{estado} no tiene entrada en TRANSICIONES_REGISTRO"

    def test_destinos_pedido_son_estados_validos(self):
        for origen, destinos in TRANSICIONES_PEDIDO.items():
            for destino in destinos:
                assert destino in EstadoPedido, f"Destino inválido {destino} desde {origen}"

    def test_destinos_registro_son_estados_validos(self):
        for origen, destinos in TRANSICIONES_REGISTRO.items():
            for destino in destinos:
                assert destino in EstadoRegistro, f"Destino inválido {destino} desde {origen}"

    def test_pagado_es_terminal(self):
        assert TRANSICIONES_PEDIDO[EstadoPedido.PAGADO] == []
