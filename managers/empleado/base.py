from database import get_db


class GestorEmpleadoBase:
    _ESTADOS_MANUALES = {'en_pausa', 'desconectado'}
    _MINUTOS_ANTES = 10
    _MINUTOS_DESPUES = 30
    _MARGEN_PUNTUALIDAD_MIN = 5
    _TIPOS_AUSENCIA = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}

    @property
    def session(self):
        return get_db()
