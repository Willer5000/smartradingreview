#!/bin/bash
echo "Instalando dependencias..."
pip install -r requirements.txt

echo "Creando directorios necesarios..."
mkdir -p static templates

echo "Configuración completada."
echo "Para ejecutar localmente: python app.py"
echo "Para producción: gunicorn app:app"
