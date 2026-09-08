import pandas as pd
import base64

def parse_accelerometer_file(contents, filename):
    content_type, content_string = contents.split(',')
    
    # Decodificar el archivo
    decoded = base64.b64decode(content_string).decode('utf-8')
    
    # Separar en líneas
    lines = decoded.splitlines()
    
    # Extraer la cabecera
    metadata = {}
    data_start = False
    data = []
    for line in lines:
        if line.startswith('#'):
            # Extraer metadatos de la cabecera
            if '=' in line:
                key, value = line.replace('# ', '').split('=')
                metadata[key.strip()] = value.strip()
        elif not line.startswith('#'):
            # Inicia el procesamiento de los datos después de la cabecera
            data_start = True
        if data_start:
            try:
                data.append([float(x) for x in line.split()])
            except ValueError:
                continue

    # Convertir los datos a un DataFrame
    if data:
        df = pd.DataFrame(data, columns=["Time", "X", "Y", "Z"])
    else:
        df = pd.DataFrame()

    return metadata, df
