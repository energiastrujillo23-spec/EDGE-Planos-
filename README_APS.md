# Portal Cloud de Áreas y PDF con Autodesk Platform Services (APS)

Esta versión ejecuta tu AutoLISP directamente en la nube de Autodesk (`Design Automation API v3`), sin necesitar AutoCAD instalado en el servidor web.

## 1. Crear credenciales en Autodesk Platform Services
1. Entra a https://aps.autodesk.com/ e inicia sesión.
2. Crea una aplicación (**Traditional Web App** o **Server-to-Server**) con las APIs **Design Automation** y **Data Management** habilitadas.
3. Copia tu `Client ID` y `Client Secret`.

## 2. Registrar el Activity (una sola vez)
```cmd
pip install -r requirements.txt
set APS_CLIENT_ID=TU_CLIENT_ID
set APS_CLIENT_SECRET=TU_CLIENT_SECRET
python setup_aps_activity.py
```

## 3. Iniciar el portal web (local o en Render/Railway/VPS)
```cmd
uvicorn server_aps:app --host 0.0.0.0 --port 8000
```
Tu equipo solo abre la URL del servidor en Google Chrome, sube el `.dwg` y descarga el `.dwg` procesado y el `.pdf` en ISO A1.
