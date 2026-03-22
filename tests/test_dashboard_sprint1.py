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
