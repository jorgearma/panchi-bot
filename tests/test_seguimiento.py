"""
Tests para GET /api/seguimiento/<redis_id>
"""
from unittest.mock import patch, MagicMock


FAKE_REDIS_ID = "abc-uuid-1234"


def _patch_seguimiento(resultado):
    """Mockea gestor_pedidos.obtener_seguimiento en el blueprint de tracking."""
    mock_gp = MagicMock()
    mock_gp.obtener_seguimiento.return_value = resultado
    return patch("blueprints.api.tracking.gestor_pedidos", mock_gp)


class TestSeguimientoEndpoint:

    def test_pedido_no_encontrado_devuelve_404(self, client):
        with _patch_seguimiento(None):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_pedido_sin_reparto(self, client):
        datos = {"estado": "en_preparacion", "forma_pago": "online", "reparto": None}
        with _patch_seguimiento(datos):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "en_preparacion"
        assert data["reparto"] is None

    def test_pedido_en_reparto_con_repartidor(self, client):
        datos = {
            "estado": "en_reparto",
            "forma_pago": "online",
            "reparto": {
                "estado": "en_camino",
                "hora_salida": "14:52",
                "hora_estimada_entrega": "15:05",
                "repartidor_nombre": "Carlos Moreno",
                "repartidor_telefono": "612345678",
                "calle_destino": "Calle Mayor 5, Madrid",
            },
        }
        with _patch_seguimiento(datos):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "en_reparto"
        reparto = data["reparto"]
        assert reparto["repartidor_nombre"] == "Carlos Moreno"
        assert reparto["repartidor_telefono"] == "612345678"
        assert reparto["hora_estimada_entrega"] == "15:05"
        assert reparto["hora_salida"] == "14:52"
        assert reparto["calle_destino"] == "Calle Mayor 5, Madrid"

    def test_pedido_con_reparto_sin_repartidor_asignado(self, client):
        datos = {
            "estado": "preparado",
            "forma_pago": "online",
            "reparto": {
                "estado": "pendiente",
                "hora_salida": None,
                "hora_estimada_entrega": None,
                "repartidor_nombre": None,
                "repartidor_telefono": None,
                "calle_destino": "Calle Mayor 5, Madrid",
            },
        }
        with _patch_seguimiento(datos):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        reparto = resp.get_json()["reparto"]
        assert reparto["repartidor_nombre"] is None
        assert reparto["repartidor_telefono"] is None

    def test_pedido_entregado(self, client):
        datos = {
            "estado": "entregado",
            "forma_pago": "online",
            "reparto": {
                "estado": "entregado",
                "hora_salida": "14:52",
                "hora_estimada_entrega": "15:05",
                "repartidor_nombre": "Carlos Moreno",
                "repartidor_telefono": "612345678",
                "calle_destino": "Calle Mayor 5, Madrid",
            },
        }
        with _patch_seguimiento(datos):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "entregado"

    def test_respuesta_incluye_forma_pago(self, client):
        datos = {"estado": "en_preparacion", "forma_pago": "efectivo", "reparto": None}
        with _patch_seguimiento(datos):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.get_json()["forma_pago"] == "efectivo"
