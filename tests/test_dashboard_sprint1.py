def test_macros_ui_cargable_en_jinja2(app):
    """El archivo de macros existe y expone los 4 macros esperados."""
    with app.app_context():
        env = app.jinja_env
        template = env.get_template('macros/ui.html')
        modulo = template.module
        assert hasattr(modulo, 'status_badge'), "Falta macro status_badge"
        assert hasattr(modulo, 'empty_state'),  "Falta macro empty_state"
        assert hasattr(modulo, 'loading_skeleton'), "Falta macro loading_skeleton"
        assert hasattr(modulo, 'error_banner'), "Falta macro error_banner"


def test_nav_partial_cargable_en_jinja2(app):
    """El parcial de navegación existe y Jinja2 puede cargarlo sin error."""
    with app.app_context():
        env = app.jinja_env
        # Lanza TemplateNotFound si el archivo no existe
        template = env.get_template('dashboard/_nav.html')
        assert template is not None


def test_dashboard_index_contiene_links_de_navegacion(client):
    """GET /dashboard renderiza HTML con links a todas las secciones."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    resp = client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode()

    rutas_esperadas = [
        '/dashboard/historial',
        '/dashboard/turnos',
        '/dashboard/rendimiento',
        '/dashboard/estadisticas',
        '/dashboard/monitor',
    ]
    for ruta in rutas_esperadas:
        assert ruta in html, f"Link '{ruta}' no encontrado en /dashboard"


def test_dashboard_monitor_contiene_links_de_navegacion(client):
    """GET /dashboard/monitor renderiza HTML con links a todas las secciones."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    # La ruta /dashboard/monitor solo hace render_template — sin queries a BD.
    # Alpine.js llama a /dashboard/monitor/datos en el cliente (JS), no en el render.
    resp = client.get('/dashboard/monitor')
    assert resp.status_code == 200
    html = resp.data.decode()

    rutas_esperadas = [
        '/dashboard',
        '/dashboard/historial',
        '/dashboard/turnos',
        '/dashboard/rendimiento',
        '/dashboard/estadisticas',
    ]
    for ruta in rutas_esperadas:
        assert ruta in html, f"Link '{ruta}' no encontrado en /dashboard/monitor"
