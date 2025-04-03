import osmnx as ox

# Descarga el grafo vial de Tarancón
G = ox.graph_from_place("Tarancón, Cuenca, Spain", network_type='all')

# Extrae los nombres de las calles (edges)
edges = ox.graph_to_gdfs(G, nodes=False)
calles = set()

for nombres in edges['name']:
    if isinstance(nombres, list):
        calles.update([n.lower() for n in nombres])
    elif isinstance(nombres, str):
        calles.add(nombres.lower())

# Resultado limpio
calles = sorted(calles)


import json

# Guardar las calles en un archivo JSON
with open("calles_tarancon.json", "w", encoding="utf-8") as file:
    json.dump(calles, file, ensure_ascii=False, indent=4)

print("Calles guardadas en 'calles_tarancon.json'")