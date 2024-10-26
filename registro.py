# Función para generar el enlace de Google Maps a partir de una dirección
def generar_enlace_google_maps(direccion):
    direccion_codificada = urllib.parse.quote(direccion)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    return url

# Función para registrar un nuevo usuario
def registrar_usuario(numero):
    print("\nNo estás registrado, por favor proporciona tus datos para continuar.")
    nombre = input("Por favor, ingresa tu nombre: ")
    
    # Comprobación de dirección válida
    direccion = ingresar_direccion()
    
    # Guardamos los datos del nuevo usuario en nuestra "base de datos"
    usuarios_registrados[numero] = {
        "nombre": nombre,
        "numero": numero,
        "direccion": direccion
    }
    
    print(f"\n¡Gracias {nombre}! Ahora estás registrado.\n")
    return usuarios_registrados[numero]

# Función para comprobar si el usuario ya está registrado
def comprobar_usuario():
    numero = input("Por favor, ingresa tu número de teléfono: ").strip()  # Limpiamos espacios extra
    
    if numero in usuarios_registrados:
        usuario = usuarios_registrados[numero]
        print(f"\n¡Bienvenido de nuevo, {usuario['nombre']}!")
        return usuario
    else:
        return registrar_usuario(numero)

# Función para ingresar y validar la dirección
def ingresar_direccion():
    while True:
        calle = input("Ingresa el nombre de tu calle: ").strip()

        # Generamos el enlace de Google Maps
        enlace_maps = generar_enlace_google_maps(calle)
        print(f"\nAquí tienes un enlace de Google Maps con la ubicación de tu calle: {enlace_maps}")

        # Preguntamos si la dirección es correcta
        confirmacion = input("¿Es esta tu dirección? Escribe 'si' para confirmar o 'no' para volver a ingresarla: ").strip().lower()

        if confirmacion == 'si':
            print(f"\nDirección válida: {calle}")
            return calle  # Si es correcta, la retornamos
        else:
            print("\nVamos a intentar de nuevo.\n")