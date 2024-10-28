usuarios_registrados = {
    "whatsapp:+453182209": {"nombre": "pendejo", "numero": "whatsapp:+4531822092", "direccion": "Calle Falsa 123"},
}

def registrar_usuario(numero, nombre, direccion):
    usuarios_registrados[numero] = {
        "nombre": nombre,
        "numero": numero,
        "direccion": direccion
    }
    return usuarios_registrados[numero]
