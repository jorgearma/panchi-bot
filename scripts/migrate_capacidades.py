"""
Migración: poblar empleado_capacidades desde rol_id actual.

Ejecutar UNA vez al desplegar:
    python scripts/migrate_capacidades.py

Hace:
1. Para cada empleado con rol picker/repartidor → añade una fila en empleado_capacidades
2. Para empleados conectados → pre-pobla rol_activo con su rol actual
3. Nada para manager/admin (no tienen capacidades operativas)

Es idempotente: verifica antes de insertar duplicados.
"""
import sys
import os

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from main import create_app
    from database import get_db
    from models import Empleado, EmpleadoCapacidad, Rol

    app = create_app()
    with app.app_context():
        db = get_db()

        empleados_op = (
            db.query(Empleado)
            .join(Rol)
            .filter(Rol.nombre.in_(['picker', 'repartidor']))
            .all()
        )

        creadas = 0
        actualizados = 0

        for emp in empleados_op:
            rol = emp.rol.nombre

            # Verificar si ya existe la capacidad
            existe = db.query(EmpleadoCapacidad).filter_by(
                empleado_id=emp.EmpleadoID, rol=rol
            ).first()

            if not existe:
                db.add(EmpleadoCapacidad(empleado_id=emp.EmpleadoID, rol=rol))
                creadas += 1
                print(f"  + {emp.Nombre} {emp.Apellido} → capacidad '{rol}'")

            # Pre-poblar rol_activo para empleados activos
            if emp.rol_activo is None and emp.estado_operativo != 'desconectado':
                emp.rol_activo = rol
                actualizados += 1
                print(f"  ~ {emp.Nombre} {emp.Apellido} → rol_activo='{rol}' (estaba activo)")

        db.commit()
        print(f"\nMigración completada: {creadas} capacidades creadas, {actualizados} rol_activo actualizados.")

        # También ejecutar el ALTER TABLE si es necesario
        # (solo si la columna aún no existe — SQLAlchemy create_all no añade columnas)
        print("\nNota: ejecutar manualmente en SQL Server si las columnas no existen:")
        print("  ALTER TABLE empleados ADD rol_activo VARCHAR(20) NULL;")
        print("  ALTER TABLE audit_log ALTER COLUMN pedido_id INT NULL;")
        print("  CREATE TABLE empleado_capacidades (id INT PRIMARY KEY IDENTITY(1,1), empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID), rol VARCHAR(20) NOT NULL, UNIQUE(empleado_id, rol));")


if __name__ == '__main__':
    main()
