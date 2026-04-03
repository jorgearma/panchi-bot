from datetime import datetime


def get_demo_picker_data():
    """Genera los datos de picking demo con timestamps frescos."""
    now = datetime.utcnow().isoformat()
    return [
        {
            "picking_id": 1001,
            "pedido_id": 1001,
            "estado": "EN_PROCESO",
            "modo": "restaurant",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "cliente_nombre": "Carlos Martínez",
            "cliente_telefono": "612345678",
            "total": 28.50,
            "iniciado_en": now,
            "items_total": 3,
            "items_listos": 0,
            "items_pendientes": 3,
            "picking_completo": False,
            "listo_para_finalizar": False,
            "items": [
                {
                    "item_id": 1,
                    "producto_id": 101,
                    "nombre": "Bocadillo de jamón",
                    "cantidad": 2,
                    "ubicacion": "A-1",
                    "imagen": None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                    "notas": None,
                },
                {
                    "item_id": 2,
                    "producto_id": 102,
                    "nombre": "Refresco lata",
                    "cantidad": 2,
                    "ubicacion": "B-3",
                    "imagen": None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                    "notas": None,
                },
                {
                    "item_id": 3,
                    "producto_id": 103,
                    "nombre": "Patatas fritas",
                    "cantidad": 1,
                    "ubicacion": "A-2",
                    "imagen": None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                    "notas": None,
                },
            ],
        },
        {
            "picking_id": 1002,
            "pedido_id": 1002,
            "estado": "EN_PROCESO",
            "modo": "restaurant",
            "direccion_entrega": "Av. Constitución 45, Tarancón",
            "cliente_nombre": "Ana López",
            "cliente_telefono": "698765432",
            "total": 19.90,
            "iniciado_en": now,
            "items_total": 2,
            "items_listos": 0,
            "items_pendientes": 2,
            "picking_completo": False,
            "listo_para_finalizar": False,
            "items": [
                {
                    "item_id": 4,
                    "producto_id": 104,
                    "nombre": "Menú del día completo",
                    "cantidad": 1,
                    "ubicacion": "C-1",
                    "imagen": None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                    "notas": None,
                },
                {
                    "item_id": 5,
                    "producto_id": 105,
                    "nombre": "Agua mineral",
                    "cantidad": 2,
                    "ubicacion": "B-1",
                    "imagen": None,
                    "estado": "pendiente",
                    "cantidad_encontrada": None,
                    "notas": None,
                },
            ],
        },
    ]


def get_demo_repartidor_data():
    """Genera los datos de reparto demo con timestamps frescos."""
    now = datetime.utcnow().isoformat()
    return [
        {
            "reparto_id": 2001,
            "pedido_id": 1001,
            "estado_reparto": "asignado",
            "estado_pedido": "PREPARADO",
            "cliente_nombre": "Carlos Martínez",
            "cliente_telefono": "612345678",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "lat": 40.010120,
            "lng": -3.013713,
            "total": 28.50,
            "pago": {
                "estado": "cobrar_efectivo",
                "label": "Cobrar en efectivo",
                "importe": 28.50,
                "proveedor": None,
            },
            "items": [
                {"nombre": "Bocadillo de jamón", "cantidad": 2, "subtotal": 16.00},
                {"nombre": "Refresco lata", "cantidad": 2, "subtotal": 5.00},
                {"nombre": "Patatas fritas", "cantidad": 1, "subtotal": 7.50},
            ],
            "fecha_creacion": now,
            "hora_salida": None,
            "hora_estimada_entrega": None,
            "hora_entrega_real": None,
            "motivo_no_entrega": None,
            "notas": None,
        },
        {
            "reparto_id": 2002,
            "pedido_id": 1002,
            "estado_reparto": "asignado",
            "estado_pedido": "PREPARADO",
            "cliente_nombre": "Ana López",
            "cliente_telefono": "698765432",
            "direccion_entrega": "Av. Constitución 45, Tarancón",
            "lat": 40.013886,
            "lng": -3.015154,
            "total": 19.90,
            "pago": {
                "estado": "pagado_online",
                "label": "Pagado online",
                "importe": 19.90,
                "proveedor": "Monei",
            },
            "items": [
                {"nombre": "Menú del día completo", "cantidad": 1, "subtotal": 14.90},
                {"nombre": "Agua mineral", "cantidad": 2, "subtotal": 5.00},
            ],
            "fecha_creacion": now,
            "hora_salida": None,
            "hora_estimada_entrega": None,
            "hora_entrega_real": None,
            "motivo_no_entrega": None,
            "notas": None,
        },
    ]


def get_demo_cola_picker():
    """Genera la cola de pickings sin asignar."""
    now = datetime.utcnow().isoformat()
    return {
        "cola": [
            {
                "picking_id": 1003,
                "pedido_id": 1003,
                "estado": "EN_PROCESO",
                "modo": "restaurant",
                "direccion_entrega": "Calle Corta 5, Tarancón",
                "cliente_nombre": "María García",
                "cliente_telefono": "655123456",
                "total": 35.75,
                "iniciado_en": now,
                "items_total": 4,
                "items_listos": 0,
                "items_pendientes": 4,
                "picking_completo": False,
                "listo_para_finalizar": False,
                "items": [
                    {
                        "item_id": 6,
                        "producto_id": 106,
                        "nombre": "Sándwich mixto",
                        "cantidad": 2,
                        "ubicacion": "A-3",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                    {
                        "item_id": 7,
                        "producto_id": 107,
                        "nombre": "Zumo natural",
                        "cantidad": 2,
                        "ubicacion": "C-2",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                    {
                        "item_id": 8,
                        "producto_id": 108,
                        "nombre": "Ensalada",
                        "cantidad": 1,
                        "ubicacion": "B-2",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                    {
                        "item_id": 9,
                        "producto_id": 109,
                        "nombre": "Postre casero",
                        "cantidad": 1,
                        "ubicacion": "A-4",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                ],
            },
            {
                "picking_id": 1004,
                "pedido_id": 1004,
                "estado": "EN_PROCESO",
                "modo": "restaurant",
                "direccion_entrega": "Avenida Central 22, Tarancón",
                "cliente_nombre": "Roberto Sánchez",
                "cliente_telefono": "678456789",
                "total": 12.50,
                "iniciado_en": now,
                "items_total": 2,
                "items_listos": 0,
                "items_pendientes": 2,
                "picking_completo": False,
                "listo_para_finalizar": False,
                "items": [
                    {
                        "item_id": 10,
                        "producto_id": 110,
                        "nombre": "Tarta de chocolate",
                        "cantidad": 1,
                        "ubicacion": "C-3",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                    {
                        "item_id": 11,
                        "producto_id": 111,
                        "nombre": "Café",
                        "cantidad": 2,
                        "ubicacion": "B-4",
                        "imagen": None,
                        "estado": "pendiente",
                        "cantidad_encontrada": None,
                        "notas": None,
                    },
                ],
            },
        ],
        "total": 2,
    }


def get_demo_cola_repartidor():
    """Genera la cola de repartos sin asignar."""
    now = datetime.utcnow().isoformat()
    return {
        "cola": [
            {
                "reparto_id": 2003,
                "pedido_id": 1003,
                "estado_reparto": "asignado",
                "estado_pedido": "PREPARADO",
                "cliente_nombre": "María García",
                "cliente_telefono": "655123456",
                "direccion_entrega": "Calle Corta 5, Tarancón",
                "lat": 40.013238,
                "lng": -3.007401,
                "total": 35.75,
                "pago": {
                    "estado": "cobrar_efectivo",
                    "label": "Cobrar en efectivo",
                    "importe": 35.75,
                    "proveedor": None,
                },
                "items": [
                    {"nombre": "Sándwich mixto", "cantidad": 2, "subtotal": 14.00},
                    {"nombre": "Zumo natural", "cantidad": 2, "subtotal": 6.00},
                    {"nombre": "Ensalada", "cantidad": 1, "subtotal": 8.50},
                    {"nombre": "Postre casero", "cantidad": 1, "subtotal": 7.25},
                ],
                "fecha_creacion": now,
                "hora_salida": None,
                "hora_estimada_entrega": None,
                "hora_entrega_real": None,
                "motivo_no_entrega": None,
                "notas": None,
            },
            {
                "reparto_id": 2004,
                "pedido_id": 1004,
                "estado_reparto": "asignado",
                "estado_pedido": "PREPARADO",
                "cliente_nombre": "Roberto Sánchez",
                "cliente_telefono": "678456789",
                "direccion_entrega": "Avenida Central 22, Tarancón",
                "lat": 40.008333,
                "lng": -3.007813,
                "total": 12.50,
                "pago": {
                    "estado": "pagado_online",
                    "label": "Pagado online",
                    "importe": 12.50,
                    "proveedor": "Monei",
                },
                "items": [
                    {"nombre": "Tarta de chocolate", "cantidad": 1, "subtotal": 8.00},
                    {"nombre": "Café", "cantidad": 2, "subtotal": 4.50},
                ],
                "fecha_creacion": now,
                "hora_salida": None,
                "hora_estimada_entrega": None,
                "hora_entrega_real": None,
                "motivo_no_entrega": None,
                "notas": None,
            },
        ],
        "total": 2,
    }


DEMO_COLA_PICKER = get_demo_cola_picker()
DEMO_COLA_REPARTIDOR = get_demo_cola_repartidor()


def get_demo_dashboard_pedidos():
    """Pedidos activos para el dashboard en modo demo.

    Estados en minúscula como espera el JS del dashboard.
    picking.picker_nombre + picking.estado (lowercase) para columna Asignación.
    reparto.repartidor_nombre + reparto.estado ('en_camino') para columna Asignación.
    """
    now = datetime.utcnow().isoformat()
    return [
        {
            "pedido_id": 1001,
            "cliente_nombre": "Carlos Martínez",
            "cliente_telefono": "612345678",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "lat": 40.010120, "lng": -3.013713,
            "estado": "en_preparacion",
            "forma_pago": "efectivo",
            "total": 28.50,
            "fecha_creacion": now,
            "minutos_en_estado": 8,
            "es_alerta": False,
            "picking": {
                "picking_id": 1001,
                "picker_nombre": "Luis R.",
                "estado": "en_proceso",
                "items_listos": 1,
                "items_total": 3,
            },
            "reparto": None,
            "items": [
                {"nombre": "Bocadillo de jamón", "cantidad": 2, "precio_unitario": 8.00, "subtotal": 16.00},
                {"nombre": "Refresco lata",       "cantidad": 2, "precio_unitario": 2.50, "subtotal": 5.00},
                {"nombre": "Patatas fritas",       "cantidad": 1, "precio_unitario": 7.50, "subtotal": 7.50},
            ],
        },
        {
            "pedido_id": 1002,
            "cliente_nombre": "Ana López",
            "cliente_telefono": "698765432",
            "direccion_entrega": "Av. Constitución 45, Tarancón",
            "lat": 40.013886, "lng": -3.015154,
            "estado": "preparado",
            "forma_pago": "online",
            "total": 19.90,
            "fecha_creacion": now,
            "minutos_en_estado": 3,
            "es_alerta": False,
            "picking": {
                "picking_id": 1002,
                "picker_nombre": "Luis R.",
                "estado": "completado",
                "items_listos": 2,
                "items_total": 2,
            },
            "reparto": None,
            "items": [
                {"nombre": "Menú del día completo", "cantidad": 1, "precio_unitario": 14.90, "subtotal": 14.90},
                {"nombre": "Agua mineral",           "cantidad": 2, "precio_unitario": 2.50,  "subtotal": 5.00},
            ],
        },
        {
            "pedido_id": 1003,
            "cliente_nombre": "María García",
            "cliente_telefono": "655123456",
            "direccion_entrega": "Calle Corta 5, Tarancón",
            "lat": 40.013238, "lng": -3.007401,
            "estado": "en_reparto",
            "forma_pago": "efectivo",
            "total": 35.75,
            "fecha_creacion": now,
            "minutos_en_estado": 12,
            "es_alerta": False,
            "picking": {
                "picking_id": 1003,
                "picker_nombre": "Luis R.",
                "estado": "completado",
                "items_listos": 4,
                "items_total": 4,
            },
            "reparto": {
                "reparto_id": 2003,
                "repartidor_nombre": "Pedro M.",
                "estado": "en_camino",
            },
            "items": [
                {"nombre": "Sándwich mixto", "cantidad": 2, "precio_unitario": 7.00, "subtotal": 14.00},
                {"nombre": "Zumo natural",   "cantidad": 2, "precio_unitario": 3.00, "subtotal": 6.00},
                {"nombre": "Ensalada",        "cantidad": 1, "precio_unitario": 8.50, "subtotal": 8.50},
                {"nombre": "Postre casero",   "cantidad": 1, "precio_unitario": 7.25, "subtotal": 7.25},
            ],
        },
        {
            "pedido_id": 1004,
            "cliente_nombre": "Roberto Sánchez",
            "cliente_telefono": "678456789",
            "direccion_entrega": "Avenida Central 22, Tarancón",
            "lat": 40.008333, "lng": -3.007813,
            "estado": "en_preparacion",
            "forma_pago": "online",
            "total": 12.50,
            "fecha_creacion": now,
            "minutos_en_estado": 5,
            "es_alerta": False,
            "picking": {
                "picking_id": 1004,
                "picker_nombre": None,
                "estado": "pendiente",
                "items_listos": 0,
                "items_total": 2,
            },
            "reparto": None,
            "items": [
                {"nombre": "Tarta de chocolate", "cantidad": 1, "precio_unitario": 6.50, "subtotal": 6.50},
                {"nombre": "Café",               "cantidad": 2, "precio_unitario": 3.00, "subtotal": 6.00},
            ],
        },
    ]


def get_demo_dashboard_metricas():
    """Métricas resumidas para el dashboard en modo demo."""
    return {
        "pedidos_hoy": 17,
        "pedidos_activos": 4,
        "ingresos_hoy": 386.40,
        "tiempo_medio_entrega": 28,
        "pedidos_en_preparacion": 2,
        "pedidos_preparados": 1,
        "pedidos_en_reparto": 1,
        "cancelados_hoy": 0,
    }


def get_demo_dashboard_alertas():
    """Alertas activas para el dashboard en modo demo."""
    return [
        {
            "id": 1,
            "tipo": "pedido_retrasado",
            "nivel": "warning",
            "pedido_id": 1001,
            "cliente_nombre": "Carlos Martínez",
            "minutos": 8,
            "mensaje": "Pedido #1001 lleva 8 min en preparación sin completar",
        },
    ]


def get_demo_dashboard_eventos():
    """Eventos recientes del sistema para el dashboard en modo demo.

    El template usa: e.timestamp, e.pedido_id, e.estado_anterior, e.estado_nuevo, e.notas
    """
    now = datetime.utcnow().isoformat()
    return [
        {"id": 1, "pedido_id": 1004, "timestamp": now, "estado_anterior": "confirmando_pago", "estado_nuevo": "en_preparacion", "notas": "Pedido Roberto Sánchez — 12,50 €"},
        {"id": 2, "pedido_id": 1003, "timestamp": now, "estado_anterior": "en_preparacion",   "estado_nuevo": "en_reparto",      "notas": "Asignado a Pedro M."},
        {"id": 3, "pedido_id": 1003, "timestamp": now, "estado_anterior": "preparado",         "estado_nuevo": "en_preparacion",  "notas": None},
        {"id": 4, "pedido_id": 1002, "timestamp": now, "estado_anterior": "confirmando_pago",  "estado_nuevo": "preparado",       "notas": "Completado por Luis R."},
        {"id": 5, "pedido_id": 1001, "timestamp": now, "estado_anterior": "confirmando_pago",  "estado_nuevo": "en_preparacion",  "notas": "Pedido Carlos Martínez — 28,50 €"},
    ]


def get_demo_dashboard_picking():
    """Estado del picking para el dashboard en modo demo.

    El JS usa: pk.empleado.id / pk.empleado.nombre, pk.estado_picking (lowercase),
    pk.tipo ('sin_asignar' para mostrar en bloqueos), pk.items_completados / pk.items_total.
    """
    now = datetime.utcnow().isoformat()
    return [
        {
            "picking_id": 1001,
            "pedido_id": 1001,
            "estado_picking": "en_proceso",
            "tipo": "asignado",
            "empleado": {"id": 11, "nombre": "Luis R."},
            "cliente_nombre": "Carlos Martínez",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "total": 28.50,
            "items_completados": 1,
            "items_total": 3,
            "items_pendientes": 2,
            "iniciado_en": now,
            "fecha_creacion": now,
        },
        {
            "picking_id": 1004,
            "pedido_id": 1004,
            "estado_picking": "pendiente",
            "tipo": "sin_asignar",
            "empleado": None,
            "cliente_nombre": "Roberto Sánchez",
            "direccion_entrega": "Avenida Central 22, Tarancón",
            "total": 12.50,
            "items_completados": 0,
            "items_total": 2,
            "items_pendientes": 2,
            "iniciado_en": now,
            "fecha_creacion": now,
        },
    ]


def get_demo_dashboard_repartidores():
    """Estado de empleados (pickers + repartidores) para el dashboard en modo demo.

    El JS construye pickersEquipo filtrando empleados cuyo rol.includes('picker'),
    y repartidoresEquipo con rol.includes('repart').
    Cada empleado necesita: empleado_id, nombre, rol, tiene_checkin, entregados_hoy,
    pedidos_activos (array de repartos para repartidores, vacío para pickers).
    Cada reparto en pedidos_activos: reparto_id, pedido_id, total, direccion,
    estado_reparto ('asignado'|'en_camino'), hora_salida.
    pedidos_sin_asignar usa: pedido_id, repartidor_nombre, direccion.
    """
    now = datetime.utcnow().isoformat()
    return {
        "empleados": [
            # ── Pickers (fichados) ──
            {
                "empleado_id": 11,
                "nombre": "Luis R.",
                "rol": "picker",
                "tiene_checkin": True,
                "entregados_hoy": 0,
                "pedidos_activos": [],   # pickers no llevan repartos
            },
            {
                "empleado_id": 31,
                "nombre": "Jorge P.",
                "rol": "picker",
                "tiene_checkin": False,  # sin fichar → aparece opaco
                "entregados_hoy": 0,
                "pedidos_activos": [],
            },
            # ── Repartidores (fichados) ──
            {
                "empleado_id": 21,
                "nombre": "Pedro M.",
                "rol": "repartidor",
                "tiene_checkin": True,
                "entregados_hoy": 3,
                "pedidos_activos": [
                    {
                        "reparto_id": 2003,
                        "pedido_id": 1003,
                        "total": 35.75,
                        "direccion": "Calle Corta 5, Tarancón",
                        "estado_reparto": "en_camino",
                        "hora_salida": now,
                    }
                ],
            },
            {
                "empleado_id": 22,
                "nombre": "Sara V.",
                "rol": "repartidor",
                "tiene_checkin": True,
                "entregados_hoy": 2,
                "pedidos_activos": [],   # disponible
            },
        ],
        "pedidos_sin_asignar": [
            {
                "pedido_id": 1002,
                "repartidor_nombre": None,
                "direccion": "Av. Constitución 45, Tarancón",
                "total": 19.90,
                "estado": "preparado",
                "minutos_esperando": 3,
            }
        ],
    }


def get_demo_historial_pedidos():
    """Historial paginado de pedidos para demo."""
    now = datetime.utcnow().isoformat()
    pedidos = [
        {"pedido_id": 1000, "cliente_nombre": "Lucía Fernández",   "direccion_entrega": "Calle Nueva 3, Tarancón",       "estado": "ENTREGADO",       "forma_pago": "online",   "total": 22.50, "fecha_creacion": now},
        {"pedido_id": 999,  "cliente_nombre": "Javier Ruiz",       "direccion_entrega": "Plaza Mayor 1, Tarancón",        "estado": "ENTREGADO",       "forma_pago": "efectivo", "total": 14.00, "fecha_creacion": now},
        {"pedido_id": 998,  "cliente_nombre": "Elena Castro",      "direccion_entrega": "Calle Sol 8, Tarancón",          "estado": "ENTREGADO",       "forma_pago": "online",   "total": 31.80, "fecha_creacion": now},
        {"pedido_id": 997,  "cliente_nombre": "Miguel Torres",     "direccion_entrega": "Av. España 17, Tarancón",        "estado": "ENTREGADO",       "forma_pago": "online",   "total": 18.90, "fecha_creacion": now},
        {"pedido_id": 996,  "cliente_nombre": "Carmen Vega",       "direccion_entrega": "Ronda Norte 6, Tarancón",        "estado": "CANCELADO",       "forma_pago": "efectivo", "total": 9.50,  "fecha_creacion": now},
        {"pedido_id": 995,  "cliente_nombre": "Pablo Moreno",      "direccion_entrega": "Calle Real 22, Tarancón",        "estado": "ENTREGADO",       "forma_pago": "online",   "total": 27.40, "fecha_creacion": now},
        {"pedido_id": 994,  "cliente_nombre": "Isabel Jiménez",    "direccion_entrega": "Calle Mayor 44, Tarancón",       "estado": "ENTREGADO",       "forma_pago": "efectivo", "total": 16.20, "fecha_creacion": now},
        {"pedido_id": 993,  "cliente_nombre": "Antonio Navarro",   "direccion_entrega": "C/ Tarancón 9, Tarancón",        "estado": "REEMBOLSADO",     "forma_pago": "online",   "total": 12.00, "fecha_creacion": now},
        {"pedido_id": 992,  "cliente_nombre": "Rosa Díaz",         "direccion_entrega": "Calle Larga 30, Tarancón",       "estado": "ENTREGADO",       "forma_pago": "efectivo", "total": 33.70, "fecha_creacion": now},
        {"pedido_id": 991,  "cliente_nombre": "Fernando Gil",      "direccion_entrega": "Paseo del Prado 2, Tarancón",    "estado": "ENTREGADO",       "forma_pago": "online",   "total": 20.10, "fecha_creacion": now},
        {"pedido_id": 990,  "cliente_nombre": "Marta Serrano",     "direccion_entrega": "Calle Ancha 15, Tarancón",       "estado": "ENTREGADO",       "forma_pago": "online",   "total": 41.00, "fecha_creacion": now},
        {"pedido_id": 989,  "cliente_nombre": "Diego Molina",      "direccion_entrega": "C/ Olmo 4, Tarancón",            "estado": "ENTREGADO",       "forma_pago": "efectivo", "total": 8.50,  "fecha_creacion": now},
    ]
    return {"pedidos": pedidos, "total": len(pedidos), "page": 1, "pages": 1}


def get_demo_pedido_detalle(pedido_id):
    """Detalle de un pedido concreto para demo."""
    now = datetime.utcnow().isoformat()
    return {
        "pedido_id": pedido_id,
        "cliente_nombre": "Demo Cliente",
        "cliente_telefono": "600000000",
        "direccion_entrega": "Calle Mayor 12, Tarancón",
        "estado": "ENTREGADO",
        "forma_pago": "online",
        "total": 22.50,
        "fecha_creacion": now,
        "items": [
            {"nombre": "Bocadillo de jamón", "cantidad": 2, "precio_unitario": 8.00, "subtotal": 16.00},
            {"nombre": "Refresco lata",      "cantidad": 1, "precio_unitario": 2.50, "subtotal": 2.50},
            {"nombre": "Patatas fritas",     "cantidad": 1, "precio_unitario": 4.00, "subtotal": 4.00},
        ],
        "historial_estados": [
            {"estado": "PENDIENTE",      "fecha": now, "empleado": None},
            {"estado": "EN_PREPARACION", "fecha": now, "empleado": "Luis R."},
            {"estado": "PREPARADO",      "fecha": now, "empleado": "Luis R."},
            {"estado": "EN_REPARTO",     "fecha": now, "empleado": "Pedro M."},
            {"estado": "ENTREGADO",      "fecha": now, "empleado": "Pedro M."},
        ],
    }


def get_demo_turnos_hoy():
    """Turnos del día de hoy para demo."""
    return {
        "empleados": [
            {"id": 11, "nombre": "Luis R.",   "rol": "picker",      "tiene_turno": True,  "activo": True,  "turno": {"hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal"}},
            {"id": 21, "nombre": "Pedro M.",  "rol": "repartidor",  "tiene_turno": True,  "activo": True,  "turno": {"hora_inicio": "10:00", "hora_fin": "18:00", "tipo": "normal"}},
            {"id": 22, "nombre": "Sara V.",   "rol": "repartidor",  "tiene_turno": True,  "activo": False, "turno": {"hora_inicio": "14:00", "hora_fin": "22:00", "tipo": "normal"}},
            {"id": 31, "nombre": "Jorge P.",  "rol": "picker",      "tiene_turno": False, "activo": False, "turno": None},
        ],
        "resumen": {
            "total_empleados": 4,
            "con_turno": 3,
            "activos_ahora": 2,
            "pickers": 1,
            "repartidores": 2,
        },
    }


def get_demo_turnos_historial():
    """Historial de turnos paginado para demo."""
    now = datetime.utcnow().isoformat()
    turnos = [
        {"id": 101, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-04-03", "hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
        {"id": 102, "empleado_id": 21, "empleado": "Pedro M.", "rol": "repartidor", "fecha": "2026-04-03", "hora_inicio": "10:00", "hora_fin": "18:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
        {"id": 103, "empleado_id": 22, "empleado": "Sara V.",  "rol": "repartidor", "fecha": "2026-04-03", "hora_inicio": "14:00", "hora_fin": "22:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
        {"id": 104, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-04-02", "hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
        {"id": 105, "empleado_id": 31, "empleado": "Jorge P.", "rol": "picker",     "fecha": "2026-04-02", "hora_inicio": "11:00", "hora_fin": "15:00", "tipo": "parcial",   "estado": "completado", "duracion_min": 240},
        {"id": 106, "empleado_id": 21, "empleado": "Pedro M.", "rol": "repartidor", "fecha": "2026-04-01", "hora_inicio": "10:00", "hora_fin": "18:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
        {"id": 107, "empleado_id": 22, "empleado": "Sara V.",  "rol": "repartidor", "fecha": "2026-04-01", "hora_inicio": "14:00", "hora_fin": "22:00", "tipo": "normal",    "estado": "cancelado",  "duracion_min": None},
        {"id": 108, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-03-31", "hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal",    "estado": "completado", "duracion_min": 480},
    ]
    return {"turnos": turnos, "total": len(turnos), "page": 1, "pages": 1}


def get_demo_turnos_planificacion():
    """Planificación semanal de turnos para demo."""
    turnos = [
        {"id": 201, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-04-04", "hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 202, "empleado_id": 21, "empleado": "Pedro M.", "rol": "repartidor", "fecha": "2026-04-04", "hora_inicio": "10:00", "hora_fin": "18:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 203, "empleado_id": 22, "empleado": "Sara V.",  "rol": "repartidor", "fecha": "2026-04-04", "hora_inicio": "14:00", "hora_fin": "22:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 204, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-04-05", "hora_inicio": "09:00", "hora_fin": "17:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 205, "empleado_id": 31, "empleado": "Jorge P.", "rol": "picker",     "fecha": "2026-04-05", "hora_inicio": "13:00", "hora_fin": "21:00", "tipo": "tarde",   "estado": "planificado"},
        {"id": 206, "empleado_id": 21, "empleado": "Pedro M.", "rol": "repartidor", "fecha": "2026-04-06", "hora_inicio": "10:00", "hora_fin": "18:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 207, "empleado_id": 22, "empleado": "Sara V.",  "rol": "repartidor", "fecha": "2026-04-06", "hora_inicio": "14:00", "hora_fin": "22:00", "tipo": "normal",  "estado": "planificado"},
        {"id": 208, "empleado_id": 11, "empleado": "Luis R.",  "rol": "picker",     "fecha": "2026-04-07", "hora_inicio": "09:00", "hora_fin": "13:00", "tipo": "parcial", "estado": "planificado"},
    ]
    return {"turnos": turnos, "total": len(turnos), "page": 1, "pages": 1}


def get_demo_rendimiento_resumen():
    """Ranking de rendimiento para demo."""
    return {
        "empleados": [
            {
                "id": 21, "nombre": "Pedro M.", "rol": "repartidor",
                "pedidos": 8, "tiempo_medio_min": 24, "entregas_a_tiempo": 7,
                "pct_a_tiempo": 87.5, "horas_trabajadas": 8.0,
                "pedidos_por_hora": 1.0, "incidencias": 0,
            },
            {
                "id": 11, "nombre": "Luis R.", "rol": "picker",
                "pedidos": 11, "tiempo_medio_min": 9, "entregas_a_tiempo": 10,
                "pct_a_tiempo": 90.9, "horas_trabajadas": 8.0,
                "pedidos_por_hora": 1.4, "incidencias": 1,
            },
            {
                "id": 22, "nombre": "Sara V.", "rol": "repartidor",
                "pedidos": 5, "tiempo_medio_min": 27, "entregas_a_tiempo": 5,
                "pct_a_tiempo": 100.0, "horas_trabajadas": 4.0,
                "pedidos_por_hora": 1.25, "incidencias": 0,
            },
            {
                "id": 31, "nombre": "Jorge P.", "rol": "picker",
                "pedidos": 3, "tiempo_medio_min": 12, "entregas_a_tiempo": 3,
                "pct_a_tiempo": 100.0, "horas_trabajadas": 4.0,
                "pedidos_por_hora": 0.75, "incidencias": 0,
            },
        ]
    }


def get_demo_rendimiento_empleado(empleado_id):
    """Detalle de rendimiento por empleado para demo."""
    nombres = {11: "Luis R.", 21: "Pedro M.", 22: "Sara V.", 31: "Jorge P."}
    roles   = {11: "picker",  21: "repartidor", 22: "repartidor", 31: "picker"}
    nombre  = nombres.get(empleado_id, "Empleado Demo")
    rol     = roles.get(empleado_id, "picker")
    return {
        "empleado": {"id": empleado_id, "nombre": nombre, "rol": rol},
        "resumen": {
            "pedidos": 11, "tiempo_medio_min": 9, "pct_a_tiempo": 90.9,
            "horas_trabajadas": 40.0, "incidencias": 1,
        },
        "serie_pedidos_dia": [
            {"fecha": "2026-03-29", "pedidos": 2},
            {"fecha": "2026-03-30", "pedidos": 3},
            {"fecha": "2026-03-31", "pedidos": 1},
            {"fecha": "2026-04-01", "pedidos": 2},
            {"fecha": "2026-04-02", "pedidos": 1},
            {"fecha": "2026-04-03", "pedidos": 2},
        ],
    }


def get_demo_estadisticas():
    """Estadísticas agregadas para demo (última semana)."""
    dias = ["2026-03-29", "2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04"]
    serie = [
        {"fecha": d, "pedidos": p, "ingresos": round(p * 21.5, 2)}
        for d, p in zip(dias, [12, 15, 9, 18, 14, 17, 6])
    ]
    return {
        "kpis": {
            "pedidos_total": 91,
            "ingresos_total": 1958.50,
            "ticket_medio": 21.52,
            "tiempo_medio_entrega_min": 26,
            "pct_entregados": 94.5,
            "cancelados": 5,
        },
        "serie_pedidos_ingresos": serie,
        "distribucion_estados": [
            {"estado": "ENTREGADO",   "total": 86},
            {"estado": "CANCELADO",   "total": 4},
            {"estado": "REEMBOLSADO", "total": 1},
        ],
        "forma_pago": [
            {"forma": "online",   "total": 61, "importe": 1312.42},
            {"forma": "efectivo", "total": 30, "importe": 646.08},
        ],
        "serie_tiempos": [
            {"fecha": d, "tiempo_medio_min": t}
            for d, t in zip(dias, [28, 25, 31, 24, 27, 26, 23])
        ],
    }


def get_demo_monitor_datos():
    """Datos completos para el monitor operativo en modo demo.

    Campos requeridos por monitor.html / monitor() Alpine:
    - pickers[]: empleado_id, nombre, estado, has_checked_in, rendimiento,
                 pickings_activos[], completados_hoy, tiempo_medio_min,
                 incidencias_hoy, ultima_actividad, historial_hoy[], telefono
    - repartidores[]: empleado_id, nombre, estado, has_checked_in, rendimiento,
                      carga, entregas_activas[], entregados_hoy, tiempo_medio_min,
                      pedidos_activos (int), tiempo_inactivo_min, ultima_actividad,
                      historial_hoy[], telefono
    - metricas: pedidos_hoy, pedidos_activos, en_preparacion, en_reparto,
                entregados_hoy, ingresos_hoy_eur, ingresos_por_metodo,
                cancelaciones_hoy, tiempo_medio_preparacion_min, tiempo_medio_entrega_min
    - alertas[], eventos[], incidencias_abiertas
    - pedidos_sin_picker[], pedidos_sin_repartidor[]
    """
    now = datetime.utcnow().isoformat()
    return {
        # ── Métricas header ────────────────────────────────────────────
        "metricas": {
            "pedidos_hoy": 17,
            "pedidos_activos": 4,
            "en_preparacion": 2,
            "en_reparto": 1,
            "entregados_hoy": 13,
            "ingresos_hoy_eur": 386.40,
            "ingresos_por_metodo": {"online": 259.30, "efectivo": 127.10},
            "cancelaciones_hoy": {},
            "tiempo_medio_preparacion_min": 11,
            "tiempo_medio_entrega_min": 26,
        },

        # ── Bloqueos ───────────────────────────────────────────────────
        "incidencias_abiertas": 2,
        "pedidos_sin_picker": [
            {
                "pedido_id": 1004,
                "cliente_nombre": "Roberto Sánchez",
                "n_items": 2,
                "total": 12.50,
                "minutos_espera": 5,
            },
        ],
        "pedidos_sin_repartidor": [
            {
                "pedido_id": 1002,
                "cliente_nombre": "Ana López",
                "total": 19.90,
                "forma_pago": "online",
                "minutos_espera": 3,
            },
        ],

        # ── Pickers ────────────────────────────────────────────────────
        "pickers": [
            {
                "empleado_id": 11,
                "nombre": "Luis R.",
                "estado": "activo",
                "has_checked_in": True,
                "rendimiento": "alto",
                "telefono": "611000011",
                "completados_hoy": 9,
                "tiempo_medio_min": 9,
                "incidencias_hoy": 0,
                "ultima_actividad": now,
                "pickings_activos": [
                    {
                        "picking_id": 1001,
                        "pedido_id": 1001,
                        "estado": "en_proceso",
                        "items_completados": 1,
                        "items_total": 3,
                        "items_sin_stock": 0,
                        "minutos_activo": 8,
                        "progreso_pct": 33,
                    },
                ],
                "historial_hoy": [
                    {"pedido_id": 991, "duracion_min": 8},
                    {"pedido_id": 992, "duracion_min": 10},
                    {"pedido_id": 993, "duracion_min": 7},
                    {"pedido_id": 994, "duracion_min": 9},
                    {"pedido_id": 995, "duracion_min": 11},
                ],
            },
            {
                "empleado_id": 31,
                "nombre": "Jorge P.",
                "estado": "sin_carga",
                "has_checked_in": False,   # sin fichar
                "rendimiento": "medio",
                "telefono": "611000031",
                "completados_hoy": 0,
                "tiempo_medio_min": None,
                "incidencias_hoy": 0,
                "ultima_actividad": None,
                "pickings_activos": [],
                "historial_hoy": [],
            },
        ],

        # ── Repartidores ───────────────────────────────────────────────
        "repartidores": [
            {
                "empleado_id": 21,
                "nombre": "Pedro M.",
                "estado": "activo",
                "has_checked_in": True,
                "rendimiento": "alto",
                "carga": "media",
                "telefono": "611000021",
                "entregados_hoy": 3,
                "pedidos_activos": 1,
                "tiempo_medio_min": 24,
                "tiempo_inactivo_min": None,
                "ultima_actividad": now,
                "entregas_activas": [
                    {
                        "reparto_id": 2003,
                        "pedido_id": 1003,
                        "estado": "en_camino",
                        "direccion": "Calle Corta 5, Tarancón",
                        "total": 35.75,
                        "forma_pago": "efectivo",
                        "minutos_en_ruta": 12,
                    },
                ],
                "historial_hoy": [
                    {"pedido_id": 993, "duracion_min": 22},
                    {"pedido_id": 995, "duracion_min": 25},
                    {"pedido_id": 999, "duracion_min": 24},
                ],
            },
            {
                "empleado_id": 22,
                "nombre": "Sara V.",
                "estado": "inactivo",
                "has_checked_in": True,
                "rendimiento": "medio",
                "carga": "libre",
                "telefono": "611000022",
                "entregados_hoy": 2,
                "pedidos_activos": 0,
                "tiempo_medio_min": 27,
                "tiempo_inactivo_min": 8,
                "ultima_actividad": now,
                "entregas_activas": [],
                "historial_hoy": [
                    {"pedido_id": 991, "duracion_min": 29},
                    {"pedido_id": 994, "duracion_min": 25},
                ],
            },
        ],

        # ── Alertas ────────────────────────────────────────────────────
        "alertas": [
            {
                "id": 1,
                "nivel": "error",
                "tipo": "sin_repartidor",
                "pedido_id": 1002,
                "mensaje": "Pedido #1002 preparado sin repartidor asignado",
                "minutos": 3,
            },
            {
                "id": 2,
                "nivel": "warning",
                "tipo": "pedido_retrasado",
                "pedido_id": 1001,
                "mensaje": "Pedido #1001 lleva 8 min en preparación",
                "minutos": 8,
            },
        ],

        # ── Feed de eventos ────────────────────────────────────────────
        "eventos": [
            {"id": 1, "pedido_id": 1004, "timestamp": now, "estado_nuevo": "en_preparacion",  "estado_anterior": "confirmando_pago"},
            {"id": 2, "pedido_id": 1003, "timestamp": now, "estado_nuevo": "en_reparto",      "estado_anterior": "preparado"},
            {"id": 3, "pedido_id": 1003, "timestamp": now, "estado_nuevo": "preparado",       "estado_anterior": "en_preparacion"},
            {"id": 4, "pedido_id": 1002, "timestamp": now, "estado_nuevo": "preparado",       "estado_anterior": "en_preparacion"},
            {"id": 5, "pedido_id": 1001, "timestamp": now, "estado_nuevo": "en_preparacion",  "estado_anterior": "confirmando_pago"},
            {"id": 6, "pedido_id": 1000, "timestamp": now, "estado_nuevo": "entregado",       "estado_anterior": "en_reparto"},
            {"id": 7, "pedido_id": 999,  "timestamp": now, "estado_nuevo": "entregado",       "estado_anterior": "en_reparto"},
        ],
    }
