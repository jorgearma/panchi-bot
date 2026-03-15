# LEGACY — dict en memoria sin importaciones activas en ningún blueprint.
# Los pedidos activos se consultan directamente via GestorPedidos (SQLAlchemy).
# Candidato a eliminación en Fase 4.

pedidos_activos = {}