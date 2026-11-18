# Despliegue en Railway (Portal Web de Áreas y PDF)

## 1. Preparar credenciales de Autodesk (APS)
1. Entra a https://aps.autodesk.com/ y crea una aplicación con **Design Automation** y **Data Management** habilitados.
2. Copia `Client ID` y `Client Secret`.
3. En tu PC (o en la terminal de Railway), registra el Activity una sola vez:
   ```cmd
   pip install -r requirements.txt
   set APS_CLIENT_ID=TU_CLIENT_ID
   set APS_CLIENT_SECRET=TU_CLIENT_SECRET
   python setup_aps_activity.py
   ```

## 2. Subir y desplegar en Railway
1. Sube estos archivos a un repositorio de **GitHub** (o instala Railway CLI y ejecuta `railway up` dentro de la carpeta).
2. En **Railway** (https://railway.com/), crea **New Project -> Deploy from GitHub Repo** y selecciona tu repo.
3. Ve a la pestaña **Variables** del servicio y agrega:
   - `APS_CLIENT_ID` = tu Client ID
   - `APS_CLIENT_SECRET` = tu Client Secret
4. Ve a **Settings -> Networking -> Generate Domain** para obtener tu enlace público `https://...up.railway.app` y compártelo con tu equipo en Google Chrome.
