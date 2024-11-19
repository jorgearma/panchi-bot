estado_usuarios = {}

def obtener_estado_usuario(numero_cliente):
    return estado_usuarios[numero_cliente]

def actualizar_estado_usuario(numero_cliente):
    estado_usuarios[numero_cliente] = {"recien_registrado": True}
