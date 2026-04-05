"""Helpers compartidos para rutas PWA (manifest, service worker, iconos) y demo bootstrap.

Elimina la duplicación de las mismas 3-5 funciones en picker, repartidor y cocina.
"""
import logging
import os
import uuid

from flask import Response, current_app, redirect, render_template, send_from_directory, session

logger = logging.getLogger(__name__)


def icon_response(subdir: str):
    """Sirve icon-180.png desde static/{subdir}/."""
    return send_from_directory(
        os.path.join(current_app.root_path, "static", subdir),
        "icon-180.png",
        mimetype="image/png",
    )


def manifest_response(template: str, **kwargs):
    """Renderiza el manifest JSON de la PWA con los kwargs proporcionados."""
    return Response(
        render_template(template, **kwargs),
        mimetype="application/manifest+json",
    )


def sw_response(template: str, scope: str):
    """Entrega el service worker con las cabeceras PWA correctas."""
    response = Response(
        render_template(template),
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = scope
    return response


def setup_demo_session(dest: str):
    """Inicializa la sesión demo y redirige al destino indicado."""
    from services.demo_state import DemoState
    if 'demo_session_id' not in session:
        session['demo_session_id'] = str(uuid.uuid4())
        try:
            DemoState.init_session(session['demo_session_id'])
        except Exception:
            pass
    session['empleado_id'] = 0
    session['empleado_nombre'] = 'Demo'
    session['rol'] = 'manager'
    session['demo_mode'] = True
    session.permanent = False
    return redirect(dest)
