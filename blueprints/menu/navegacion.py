import logging

import config
from flask import render_template, redirect, request

from blueprints.menu._helpers import _extraer_calle
from services import menu_session

logger = logging.getLogger(__name__)


def register(bp):
    """Registra la entrada al menú web a partir del token enviado por WhatsApp."""
    @bp.route('/menu/<token>', methods=['GET'])
    def quiniela(token=None):
        """Valida el token, recupera el pedido activo y decide qué pantalla mostrar."""
        logger.debug("token recibido: %s", token)
        ip = request.remote_addr
        resultado = menu_session.resolver_sesion_menu(token, ip=ip)

        if resultado['tipo'] == 'error':
            return render_template(
                "error.html",
                titulo=resultado['titulo'],
                mensaje=resultado['mensaje'],
            ), resultado['status']

        if resultado['tipo'] == 'enlace2':
            return redirect(f'/confirmacion_pago?pedido_id={resultado["pedido_id"]}')

        usuario = resultado['usuario']
        return render_template(
            'quiniela.html',
            usuario=usuario,
            calle=_extraer_calle(usuario.direccion),
            public_url=config.PUBLIC_URL or "",
        )
