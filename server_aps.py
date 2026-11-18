import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Dict

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

BASE_DIR = Path(__file__).resolve().parent
LISP_PATH = BASE_DIR / "robot_areas_batch.lsp"

APS_BASE = "https://developer.api.autodesk.com"
CLIENT_ID = os.environ.get("APS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("APS_CLIENT_SECRET", "")
NICKNAME = os.environ.get("APS_NICKNAME", CLIENT_ID[:16].lower() if CLIENT_ID else "")
ACTIVITY_ID = f"{NICKNAME}.{os.environ.get('APS_ACTIVITY_NAME', 'RobotAreasActivity')}+prod"
BUCKET_KEY = os.environ.get("APS_BUCKET_KEY", f"portal_areas_{NICKNAME}".lower()[:60])

app = FastAPI(title="Portal Cloud de Areas y PDF (APS)")
JOBS_CACHE: Dict[str, Dict[str, str]] = {}


async def get_aps_token(client: httpx.AsyncClient) -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Faltan variables APS_CLIENT_ID / APS_CLIENT_SECRET.")
    r = await client.post(
        f"{APS_BASE}/authentication/v2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "code:all data:read data:write bucket:create bucket:read",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def ensure_bucket(client: httpx.AsyncClient, token: str):
    r = await client.post(
        f"{APS_BASE}/oss/v2/buckets",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"bucketKey": BUCKET_KEY, "policyKey": "transient"},
        timeout=30,
    )
    if r.status_code not in (200, 409):
        r.raise_for_status()


async def upload_bytes_to_oss(client: httpx.AsyncClient, token: str, object_key: str, data: bytes) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get(
        f"{APS_BASE}/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3upload",
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    info = r.json()
    upload_url = info["urls"][0]
    upload_key = info["uploadKey"]

    r_put = await client.put(upload_url, content=data, timeout=120)
    r_put.raise_for_status()

    r_fin = await client.post(
        f"{APS_BASE}/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3upload",
        headers={**headers, "Content-Type": "application/json"},
        json={"uploadKey": upload_key},
        timeout=30,
    )
    r_fin.raise_for_status()

    r_dl = await client.get(
        f"{APS_BASE}/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3download",
        headers=headers,
        timeout=30,
    )
    r_dl.raise_for_status()
    return r_dl.json()["url"]


async def create_signed_put_url(client: httpx.AsyncClient, token: str, object_key: str) -> str:
    r = await client.post(
        f"{APS_BASE}/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signed?access=write",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"minutesExpiration": 30},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["signedUrl"]


async def get_signed_download_url(client: httpx.AsyncClient, token: str, object_key: str) -> str:
    r = await client.get(
        f"{APS_BASE}/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3download",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["url"]


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=(BASE_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/api/procesar")
async def procesar_plano(archivo: UploadFile = File(...), zonas_extra: str = Form("[]")):
    if not archivo.filename or not archivo.filename.lower().endswith(".dwg"):
        raise HTTPException(status_code=400, detail="Solo se admiten archivos .dwg")

    job_id = uuid.uuid4().hex[:10]
    dwg_bytes = await archivo.read()
    lisp_bytes = LISP_PATH.read_bytes()

    try:
        zonas_list = json.loads(zonas_extra) if zonas_extra else []
    except json.JSONDecodeError:
        zonas_list = []

    async with httpx.AsyncClient() as client:
        token = await get_aps_token(client)
        await ensure_bucket(client, token)

        in_dwg_key = f"{job_id}_input.dwg"
        lisp_key = f"{job_id}_robot_areas_batch.lsp"
        out_dwg_key = f"{job_id}_output.dwg"
        out_pdf_key = f"{job_id}_output_AREAS.pdf"

        in_dwg_url = await upload_bytes_to_oss(client, token, in_dwg_key, dwg_bytes)
        lisp_url = await upload_bytes_to_oss(client, token, lisp_key, lisp_bytes)
        out_dwg_put = await create_signed_put_url(client, token, out_dwg_key)
        out_pdf_put = await create_signed_put_url(client, token, out_pdf_key)

        arguments = {
            "inputDwg": {"url": in_dwg_url},
            "lispFile": {"url": lisp_url},
            "outputDwg": {"verb": "put", "url": out_dwg_put},
            "outputPdf": {"verb": "put", "url": out_pdf_put},
        }

        if zonas_list:
            lines = []
            for z in zonas_list:
                nom = str(z.get("nombre", "")).strip().replace("|", "-")
                col = int(z.get("color", 7))
                if nom and 1 <= col <= 255:
                    lines.append(f"{nom}|{col}")
            if lines:
                extra_url = await upload_bytes_to_oss(
                    client, token, f"{job_id}_extra_zones.txt", ("\n".join(lines) + "\n").encode("utf-8")
                )
                arguments["extraZones"] = {"url": extra_url}

        r_wi = await client.post(
            f"{APS_BASE}/da/us-east/v3/workitems",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"activityId": ACTIVITY_ID, "arguments": arguments},
            timeout=30,
        )
        r_wi.raise_for_status()
        wi_id = r_wi.json()["id"]

        status = "pending"
        report_url = None
        for _ in range(90):
            await asyncio.sleep(2)
            r_poll = await client.get(
                f"{APS_BASE}/da/us-east/v3/workitems/{wi_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            r_poll.raise_for_status()
            wi_data = r_poll.json()
            status = wi_data["status"]
            report_url = wi_data.get("reportUrl")
            if status in ("success", "failedCancelled", "failedDownload", "failedInstructions", "failedUpload", "cancelled"):
                break

        if status != "success":
            return JSONResponse(
                status_code=500,
                content={"ok": False, "detail": f"WorkItem fallo con estado: {status}", "report_url": report_url},
            )

        pdf_dl = await get_signed_download_url(client, token, out_pdf_key)
        dwg_dl = await get_signed_download_url(client, token, out_dwg_key)

    safe_stem = Path(archivo.filename).stem
    JOBS_CACHE[job_id] = {
        "pdf_url": pdf_dl,
        "dwg_url": dwg_dl,
        "pdf_name": f"{safe_stem}_AREAS.pdf",
        "dwg_name": Path(archivo.filename).name,
    }
    return {
        "ok": True,
        "job_id": job_id,
        "pdf_url": f"/api/descargar/{job_id}/pdf",
        "dwg_url": f"/api/descargar/{job_id}/dwg",
        "pdf_name": JOBS_CACHE[job_id]["pdf_name"],
        "dwg_name": JOBS_CACHE[job_id]["dwg_name"],
    }


@app.get("/api/descargar/{job_id}/{tipo}")
async def descargar(job_id: str, tipo: str):
    job = JOBS_CACHE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    url = job.get("pdf_url") if tipo == "pdf" else job.get("dwg_url")
    fname = job.get("pdf_name") if tipo == "pdf" else job.get("dwg_name")
    media = "application/pdf" if tipo == "pdf" else "application/acad"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=120)
        r.raise_for_status()
    return Response(content=r.content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
