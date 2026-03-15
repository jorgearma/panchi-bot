# LEGACY — solo usado por controllers/registro_de_usuarios/registro.py (también legacy).
# El estado real de usuarios se gestiona en Redis via managers/gestor_redis.py.
# Candidato a eliminación en Fase 4.

estado_usuarios = {}

def obtener_estado_usuario(numero_cliente):
    return estado_usuarios[numero_cliente]

def actualizar_estado_usuario(numero_cliente):
    estado_usuarios[numero_cliente] = {"recien_registrado": True}
