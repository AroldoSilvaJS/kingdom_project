import os

# Archivos y carpetas que NO queremos que la IA lea (basura)
IGNORAR_CARPETAS = ['__pycache__', 'venv', 'env', 'migrations', '.git']
IGNORAR_ARCHIVOS = ['db.sqlite3', 'empaquetar.py', '.DS_Store']
EXTENSIONES_PERMITIDAS = ['.py', '.html', '.css', '.js']

with open('proyecto_completo.txt', 'w', encoding='utf-8') as archivo_salida:
    for raiz, carpetas, archivos in os.walk('.'):
        # Filtramos las carpetas que no sirven
        carpetas[:] = [c for c in carpetas if c not in IGNORAR_CARPETAS]
        
        for archivo in archivos:
            if archivo in IGNORAR_ARCHIVOS:
                continue
                
            extension = os.path.splitext(archivo)[1]
            if extension in EXTENSIONES_PERMITIDAS:
                ruta_completa = os.path.join(raiz, archivo)
                
                # Escribimos el nombre del archivo como título para la IA
                archivo_salida.write(f"\n{'='*50}\n")
                archivo_salida.write(f"ARCHIVO: {ruta_completa}\n")
                archivo_salida.write(f"{'='*50}\n\n")
                
                # Copiamos el contenido
                try:
                    with open(ruta_completa, 'r', encoding='utf-8') as f:
                        archivo_salida.write(f.read())
                        archivo_salida.write("\n")
                except Exception as e:
                    print(f"No se pudo leer {ruta_completa}")

print("¡Listo! Se ha creado el archivo 'proyecto_completo.txt'")