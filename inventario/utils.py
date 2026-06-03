import math

# Coordenadas permitidas (Ajusta con las de tu oficina o punto de control real)
LATITUD_PERMITIDA = 7.8891   
LONGITUD_PERMITIDA = -72.5061 
RADIO_MAXIMO_METROS = 10000.0  # Rango de 10 km (puedes ajustarlo si es necesario)

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    # Radio de la Tierra en metros
    R = 6371000.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c