from unittest.mock import patch, MagicMock, PropertyMock
from managers.gestor_dashboard import GestorDashboard


def test_marcar_entregado_rechaza_sin_cobro(app):
    """marcar_entregado debe retornar error si el reparto no tiene cobro registrado
    y el pedido es contra reembolso (efectivo o tarjeta)."""
    gd = GestorDashboard()
    mock_reparto = MagicMock()
    mock_reparto.metodo_cobro = None

    mock_pedido = MagicMock()
    mock_pedido.forma_pago = 'efectivo'
    mock_reparto.pedido = mock_pedido

    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_reparto

    with app.app_context():
        with patch.object(type(gd), 'session', new_callable=PropertyMock, return_value=mock_session):
            ok, msg, telefono = gd.marcar_entregado(1)
            assert not ok
            assert 'cobro' in msg.lower()
