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
            "lat": 40.0053,
            "lng": -2.9956,
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
            "lat": 40.0071,
            "lng": -2.9934,
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
                "lat": 40.0045,
                "lng": -2.9970,
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
                "lat": 40.0062,
                "lng": -2.9945,
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
    """Pedidos activos para el dashboard en modo demo."""
    now = datetime.utcnow().isoformat()
    return [
        {
            "pedido_id": 1001,
            "cliente_nombre": "Carlos Martínez",
            "cliente_telefono": "612345678",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "lat": 40.0053,
            "lng": -2.9956,
            "estado": "EN_PREPARACION",
            "forma_pago": "efectivo",
            "total": 28.50,
            "fecha_creacion": now,
            "minutos_en_estado": 8,
            "picking": {
                "picking_id": 1001,
                "picker_nombre": "Luis R.",
                "estado": "EN_PROCESO",
                "items_listos": 1,
                "items_total": 3,
            },
            "reparto": None,
            "items": [
                {"nombre": "Bocadillo de jamón", "cantidad": 2, "precio_unitario": 8.00, "subtotal": 16.00},
                {"nombre": "Refresco lata", "cantidad": 2, "precio_unitario": 2.50, "subtotal": 5.00},
                {"nombre": "Patatas fritas", "cantidad": 1, "precio_unitario": 7.50, "subtotal": 7.50},
            ],
        },
        {
            "pedido_id": 1002,
            "cliente_nombre": "Ana López",
            "cliente_telefono": "698765432",
            "direccion_entrega": "Av. Constitución 45, Tarancón",
            "lat": 40.0071,
            "lng": -2.9934,
            "estado": "PREPARADO",
            "forma_pago": "online",
            "total": 19.90,
            "fecha_creacion": now,
            "minutos_en_estado": 3,
            "picking": {
                "picking_id": 1002,
                "picker_nombre": "Luis R.",
                "estado": "COMPLETADO",
                "items_listos": 2,
                "items_total": 2,
            },
            "reparto": None,
            "items": [
                {"nombre": "Menú del día completo", "cantidad": 1, "precio_unitario": 14.90, "subtotal": 14.90},
                {"nombre": "Agua mineral", "cantidad": 2, "precio_unitario": 2.50, "subtotal": 5.00},
            ],
        },
        {
            "pedido_id": 1003,
            "cliente_nombre": "María García",
            "cliente_telefono": "655123456",
            "direccion_entrega": "Calle Corta 5, Tarancón",
            "lat": 40.0045,
            "lng": -2.9970,
            "estado": "EN_REPARTO",
            "forma_pago": "efectivo",
            "total": 35.75,
            "fecha_creacion": now,
            "minutos_en_estado": 12,
            "picking": {
                "picking_id": 1003,
                "picker_nombre": "Luis R.",
                "estado": "COMPLETADO",
                "items_listos": 4,
                "items_total": 4,
            },
            "reparto": {
                "reparto_id": 2003,
                "repartidor_nombre": "Pedro M.",
                "estado": "EN_CAMINO",
            },
            "items": [
                {"nombre": "Sándwich mixto", "cantidad": 2, "precio_unitario": 7.00, "subtotal": 14.00},
                {"nombre": "Zumo natural", "cantidad": 2, "precio_unitario": 3.00, "subtotal": 6.00},
                {"nombre": "Ensalada", "cantidad": 1, "precio_unitario": 8.50, "subtotal": 8.50},
                {"nombre": "Postre casero", "cantidad": 1, "precio_unitario": 7.25, "subtotal": 7.25},
            ],
        },
        {
            "pedido_id": 1004,
            "cliente_nombre": "Roberto Sánchez",
            "cliente_telefono": "678456789",
            "direccion_entrega": "Avenida Central 22, Tarancón",
            "lat": 40.0062,
            "lng": -2.9945,
            "estado": "EN_PREPARACION",
            "forma_pago": "online",
            "total": 12.50,
            "fecha_creacion": now,
            "minutos_en_estado": 5,
            "picking": {
                "picking_id": 1004,
                "picker_nombre": None,
                "estado": "PENDIENTE",
                "items_listos": 0,
                "items_total": 2,
            },
            "reparto": None,
            "items": [
                {"nombre": "Tarta de chocolate", "cantidad": 1, "precio_unitario": 6.50, "subtotal": 6.50},
                {"nombre": "Café", "cantidad": 2, "precio_unitario": 3.00, "subtotal": 6.00},
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
    """Eventos recientes del sistema para el dashboard en modo demo."""
    now = datetime.utcnow().isoformat()
    return [
        {"id": 1, "tipo": "pedido_nuevo", "descripcion": "Nuevo pedido #1004 de Roberto Sánchez (12,50 €)", "fecha": now},
        {"id": 2, "tipo": "picking_completado", "descripcion": "Picking #1003 completado por Luis R.", "fecha": now},
        {"id": 3, "tipo": "reparto_salida", "descripcion": "Pedro M. salió a entregar pedido #1003", "fecha": now},
        {"id": 4, "tipo": "pedido_pagado", "descripcion": "Pago online confirmado para pedido #1002 (19,90 €)", "fecha": now},
        {"id": 5, "tipo": "pedido_nuevo", "descripcion": "Nuevo pedido #1003 de María García (35,75 €)", "fecha": now},
    ]


def get_demo_dashboard_picking():
    """Estado del picking para el dashboard en modo demo."""
    now = datetime.utcnow().isoformat()
    return [
        {
            "picking_id": 1001,
            "pedido_id": 1001,
            "estado": "EN_PROCESO",
            "picker_nombre": "Luis R.",
            "picker_id": 11,
            "cliente_nombre": "Carlos Martínez",
            "direccion_entrega": "Calle Mayor 12, Tarancón",
            "total": 28.50,
            "items_listos": 1,
            "items_total": 3,
            "iniciado_en": now,
        },
        {
            "picking_id": 1004,
            "pedido_id": 1004,
            "estado": "PENDIENTE",
            "picker_nombre": None,
            "picker_id": None,
            "cliente_nombre": "Roberto Sánchez",
            "direccion_entrega": "Avenida Central 22, Tarancón",
            "total": 12.50,
            "items_listos": 0,
            "items_total": 2,
            "iniciado_en": now,
        },
    ]


def get_demo_dashboard_repartidores():
    """Estado de repartidores para el dashboard en modo demo."""
    now = datetime.utcnow().isoformat()
    return {
        "empleados": [
            {
                "empleado_id": 21,
                "nombre": "Pedro M.",
                "estado": "en_reparto",
                "pedidos_asignados": 1,
                "repartos": [
                    {
                        "reparto_id": 2003,
                        "pedido_id": 1003,
                        "cliente_nombre": "María García",
                        "direccion_entrega": "Calle Corta 5, Tarancón",
                        "estado": "EN_CAMINO",
                        "hora_salida": now,
                    }
                ],
            },
            {
                "empleado_id": 22,
                "nombre": "Sara V.",
                "estado": "disponible",
                "pedidos_asignados": 0,
                "repartos": [],
            },
        ],
        "pedidos_sin_asignar": [
            {
                "pedido_id": 1002,
                "cliente_nombre": "Ana López",
                "direccion_entrega": "Av. Constitución 45, Tarancón",
                "total": 19.90,
                "estado": "PREPARADO",
                "minutos_esperando": 3,
            }
        ],
    }
