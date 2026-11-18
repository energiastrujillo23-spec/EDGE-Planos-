"""
Script de configuracion unica para registrar el Activity de AutoCAD en Autodesk Platform Services (APS).
Ejecutar una sola vez:
  set APS_CLIENT_ID=tu_client_id
  set APS_CLIENT_SECRET=tu_client_secret
  python setup_aps_activity.py
"""
import os
import httpx

APS_BASE = "https://developer.api.autodesk.com"
CLIENT_ID = os.environ["APS_CLIENT_ID"]
CLIENT_SECRET = os.environ["APS_CLIENT_SECRET"]
NICKNAME = os.environ.get("APS_NICKNAME", CLIENT_ID[:16].lower())
ACTIVITY_NAME = os.environ.get("APS_ACTIVITY_NAME", "RobotAreasActivity")
ENGINE = os.environ.get("APS_ENGINE", "Autodesk.AutoCAD+24_3")


def get_token() -> str:
    r = httpx.post(
        f"{APS_BASE}/authentication/v2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "code:all",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Intentar registrar nickname (si ya existe, ignorar 409)
    httpx.patch(
        f"{APS_BASE}/da/us-east/v3/forgeapps/me",
        headers=headers,
        json={"nickname": NICKNAME},
        timeout=30,
    )

    # Crear Activity
    activity_payload = {
        "id": ACTIVITY_NAME,
        "commandLine": [
            '$(engine.path)\accoreconsole.exe /i "$(args[inputDwg].path)" /s "$(settings[script].path)"'
        ],
        "parameters": {
            "inputDwg": {"verb": "get", "description": "Plano DWG de entrada", "required": True, "localName": "input.dwg"},
            "lispFile": {"verb": "get", "description": "Script AutoLISP", "required": True, "localName": "robot_areas_batch.lsp"},
            "extraZones": {"verb": "get", "description": "Zonas extra", "required": False, "localName": "extra_zones.txt"},
            "outputDwg": {"verb": "put", "description": "Plano DWG procesado", "required": True, "localName": "input.dwg"},
            "outputPdf": {"verb": "put", "description": "PDF A1 generado", "required": True, "localName": "output_AREAS.pdf"},
        },
        "engine": ENGINE,
        "settings": {
            "script": {
                "value": '(setq *APS-OUTPUT-PDF* "output_AREAS.pdf")\n(load "robot_areas_batch.lsp")\nROBOTAREAS_BATCH\n_QSAVE\n'
            }
        },
        "description": "Procesa zonas, tabla de 3 columnas al 70% de transparencia y exporta PDF ISO A1.",
    }

    r = httpx.post(f"{APS_BASE}/da/us-east/v3/activities", headers=headers, json=activity_payload, timeout=30)
    if r.status_code == 409:
        print("Activity ya existe, creando nueva version...")
        r = httpx.post(f"{APS_BASE}/da/us-east/v3/activities/{ACTIVITY_NAME}/versions", headers=headers, json=activity_payload, timeout=30)
    r.raise_for_status()
    version = r.json()["version"]

    # Crear/actualizar alias 'prod'
    alias_url = f"{APS_BASE}/da/us-east/v3/activities/{ACTIVITY_NAME}/aliases"
    r_al = httpx.post(alias_url, headers=headers, json={"id": "prod", "version": version}, timeout=30)
    if r_al.status_code == 409:
        r_al = httpx.patch(f"{alias_url}/prod", headers=headers, json={"version": version}, timeout=30)
    r_al.raise_for_status()

    print(f"Activity listo: {NICKNAME}.{ACTIVITY_NAME}+prod (version {version})")


if __name__ == "__main__":
    main()
