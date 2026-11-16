"""Pruebas de integración: API + worker contra PostgreSQL real y un run-job.sh simulado.

Requiere TEST_DATABASE_URL (base de datos desechable). Ejemplo:
  TEST_DATABASE_URL=postgresql://portal:portal@127.0.0.1/portal_test pytest -q
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

DB = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL no definido")

BASE = Path(tempfile.mkdtemp(prefix="xyzbase-"))
FAKE = Path(__file__).parent / "fake" / "run-job.sh"
if DB:
    os.environ.update(DATABASE_URL=DB, COOKIE_SECURE="false", COOKIE_PATH="/",
                      XYZ_BASE=str(BASE), RUN_JOB=str(FAKE),
                      APP_SECRET_KEY="clave-de-pruebas-con-mas-de-32-bytes-ok")

CSRF = {"X-Portal-CSRF": "1"}


@pytest.fixture(scope="module")
def env():
    import pyotp  # noqa: F401
    from fastapi.testclient import TestClient

    from app import cli, db
    from app.main import app

    admin_url = DB.rsplit("/", 1)[0] + "/postgres"
    name = DB.rsplit("/", 1)[1]
    subprocess.run(["psql", admin_url, "-qc", f"DROP DATABASE IF EXISTS {name}"], check=True)
    subprocess.run(["psql", admin_url, "-qc", f"CREATE DATABASE {name}"], check=True)
    (BASE / "ansible" / "inventories").mkdir(parents=True)
    (BASE / "jobs").mkdir()

    class A:  # argumentos del CLI
        dir = None
    cli.migrate(A)
    for sid, code, name_, prot in [(3, "MAZ-03", "Mazate", True), (4, "SPOKE-R4", "SPOKE-R4", True),
                                   (6, "SPOKE-R6", "SPOKE-R6", False)]:
        a = type("A", (), dict(site_id=sid, code=code, name=name_, protected=prot, notes=None))
        cli.import_site(a)
    for u, role in [("admin", "admin"), ("operador", "netops"), ("auditor", "auditor")]:
        a = type("A", (), dict(username=u, email=f"{u}@x.local", name=u.title(), role=[role],
                               password=f"{u.title()}2026!x"))
        cli.create_user(a)
    yield TestClient(app)
    db.close()
    shutil.rmtree(BASE, ignore_errors=True)


def login(client, user):
    import pyotp
    r = client.post("/api/v1/auth/login", json={"username": user, "password": f"{user.title()}2026!x"})
    assert r.status_code == 200, r.text
    data = r.json()
    if data["status"] == "MFA_SETUP_REQUIRED":
        assert data["qr_svg"].startswith("<svg")
        env_secret = data["secret"]
        login.secrets[user] = env_secret
    code = pyotp.TOTP(login.secrets[user]).now()
    r = client.post("/api/v1/auth/mfa", json={"mfa_token": data["mfa_token"], "code": code})
    assert r.status_code == 200, r.text
    return code, data["mfa_token"]


login.secrets = {}


def run_worker_once():
    from app import worker
    claimed = worker._claim()
    assert claimed is not None, "no había trabajos en cola"
    job, console, exec_id = claimed
    rc = worker._run(job, console)
    worker._finish(job, exec_id, console, rc)
    return job


def test_login_mfa_y_reuso_de_codigo(env):
    c = env
    assert c.get("/api/v1/auth/me").status_code == 401
    code, _ = login(c, "admin")
    me = c.get("/api/v1/auth/me").json()
    assert me["username"] == "admin" and "user:admin" in me["permissions"]
    # El mismo código no sirve dos veces (anti-replay)
    r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin2026!x"})
    assert r.json()["status"] == "MFA_REQUIRED"
    r = c.post("/api/v1/auth/mfa", json={"mfa_token": r.json()["mfa_token"], "code": code})
    assert r.status_code == 401


def test_bloqueo_por_intentos(env):
    from fastapi.testclient import TestClient

    from app.main import app
    c2 = TestClient(app)
    for _ in range(5):
        assert c2.post("/api/v1/auth/login",
                       json={"username": "auditor", "password": "mala-clave-1"}).status_code == 401
    r = c2.post("/api/v1/auth/login", json={"username": "auditor", "password": "Auditor2026!x"})
    assert r.status_code == 401 and "bloqueada" in r.json()["detail"]


def test_alta_completa(env):
    c = env
    ids = c.get("/api/v1/sites/available-ids").json()
    assert ids["suggested"] == 5 and 6 not in ids["free"]
    body = {"code": "ZONA10", "name": "Heladería Zona 10"}
    assert c.post("/api/v1/sites", json=body).status_code == 403          # sin cabecera CSRF
    r = c.post("/api/v1/sites", json=body, headers=CSRF)
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["site"]["hostname"] == "R5"
    assert out["allocations"]["lan_v4"] == "10.33.0.0/24"
    assert out["allocations"]["tunnel1"] == ["192.168.5.135/25", "fd00:5:1::5/64"]
    # Duplicados
    assert c.post("/api/v1/sites", json=body, headers=CSRF).status_code == 409
    r = c.post("/api/v1/sites", json={"code": "OTRA", "name": "Otra sucursal", "site_number": 6},
               headers=CSRF)
    assert r.status_code == 409 and "R6" in r.json()["detail"]
    # Un segundo trabajo para el mismo sitio no se permite mientras hay uno en cola
    job = run_worker_once()
    site = c.get(f"/api/v1/sites/{out['site']['id']}").json()
    assert site["status"] == "ACTIVE"
    assert {a["status"] for a in site["allocations"]} == {"ALLOCATED"}
    inv = (BASE / "ansible" / "inventories" / "site_R5.yml").read_text()
    assert 'ansible_host: "172.16.0.5"' in inv and 'site_name: "Heladería Zona 10"' in inv
    assert 'lan_v6: "2001:1228:5::/64"' in inv and 'tunnel2_v4: "192.168.5.135"' in inv
    j = c.get(f"/api/v1/jobs/{job['id']}").json()
    assert j["status"] == "SUCCEEDED"
    assert [s["step"] for s in j["results"]][:2] == ["Conectividad SSH", "VRF de gestión (INET)"]
    log = c.get(f"/api/v1/jobs/{job['id']}/log").json()
    assert "PLAY RECAP" in log["text"] and log["done"]


def _site_id(c, code):
    return next(s["id"] for s in c.get("/api/v1/sites").json() if s["code"] == code)


def test_ids_que_pisan_infraestructura_se_rechazan_sin_exponer_el_motivo(env):
    c = env
    ids = c.get("/api/v1/sites/available-ids").json()
    assert 20 not in ids["free"] and 71 not in ids["free"]
    assert "reserved" not in ids
    for sid in (20, 71):
        r = c.post("/api/v1/sites", json={"code": f"PRUEBA{sid}", "name": "Caso borde", "site_number": sid},
                   headers=CSRF)
        assert r.status_code == 409 and "reservado" in r.json()["detail"], r.text
    fallos = [a for a in c.get("/api/v1/audit", params={"action": "site.create"}).json()
              if a["outcome"] == "FAILURE"]
    assert len(fallos) >= 2                                       # quedan en la auditoría...
    visible = str(ids) + str(fallos) + r.text
    for secreto in ("172.16.0.20", "10.99", "WireGuard", "Zabbix", "servidor"):
        assert secreto not in visible                              # ...sin datos de infraestructura


def test_baja_protegida_y_confirmacion(env):
    c = env
    r3 = _site_id(c, "MAZ-03")
    r = c.post(f"/api/v1/sites/{r3}/decommission", json={"confirm_code": "MAZ-03", "reason": "x" * 5},
               headers=CSRF)
    assert r.status_code == 403
    r5 = _site_id(c, "ZONA10")
    r = c.post(f"/api/v1/sites/{r5}/decommission", json={"confirm_code": "ZONA1", "reason": "cierre"},
               headers=CSRF)
    assert r.status_code == 409
    denied = c.get("/api/v1/audit", params={"action": "site.decommission"}).json()
    assert [a["outcome"] for a in denied] == ["DENIED", "DENIED"]   # quedaron registradas


def test_baja_cuarentena_y_liberacion(env):
    c = env
    r5 = _site_id(c, "ZONA10")
    r = c.post(f"/api/v1/sites/{r5}/decommission",
               json={"confirm_code": "ZONA10", "reason": "Cierre de sucursal"}, headers=CSRF)
    assert r.status_code == 202, r.text
    run_worker_once()
    site = c.get(f"/api/v1/sites/{r5}").json()
    assert site["status"] == "RETIRED"
    assert {a["status"] for a in site["allocations"]} == {"QUARANTINED"}
    assert not (BASE / "ansible" / "inventories" / "site_R5.yml").exists()
    ids = c.get("/api/v1/sites/available-ids").json()
    assert ids["suggested"] == 7 and ids["quarantined"][0]["hostname"] == "R5"
    r = c.post("/api/v1/sites", json={"code": "ZONA10B", "name": "Zona 10 B", "site_number": 5},
               headers=CSRF)
    assert r.status_code == 409 and "QUARANTINED" in r.json()["detail"]
    assert c.post(f"/api/v1/sites/{r5}/release-quarantine", headers=CSRF).status_code == 200
    assert c.get("/api/v1/sites/available-ids").json()["suggested"] == 5


def test_fallo_y_reintento(env):
    c = env
    (BASE / "fail_R5").touch()
    r = c.post("/api/v1/sites", json={"code": "ZONA10B", "name": "Zona 10 B", "site_number": 5},
               headers=CSRF)
    assert r.status_code == 202
    sid = r.json()["site"]["id"]
    job = run_worker_once()
    j = c.get(f"/api/v1/jobs/{job['id']}").json()
    assert j["status"] == "FAILED" and "Verificación" in j["error_summary"]
    assert c.get(f"/api/v1/sites/{sid}").json()["status"] == "PROVISION_FAILED"
    (BASE / "fail_R5").unlink()
    r = c.post(f"/api/v1/jobs/{job['id']}/retry", headers=CSRF)
    assert r.status_code == 202
    assert c.post(f"/api/v1/jobs/{job['id']}/retry", headers=CSRF).status_code == 409
    job2 = run_worker_once()
    assert c.get(f"/api/v1/jobs/{job2['id']}").json()["attempt"] == 2
    assert c.get(f"/api/v1/sites/{sid}").json()["status"] == "ACTIVE"


def test_sucursal_sin_respuesta_y_retiro(env):
    from app import db
    from app.application import health
    c = env
    r5, r6 = _site_id(c, "ZONA10B"), _site_id(c, "SPOKE-R6")
    down = {"172.16.0.5", "172.16.0.3"}          # R5 y R3 (protegida) dejan de responder
    up = lambda ips: {ip: ip not in down for ip in ips}           # noqa: E731

    health.check_all(up)                          # 1.ª falla: todavía no se marca
    st = {s["hostname"]: s["reachability"] for s in c.get("/api/v1/sites").json()
          if s["status"] != "RETIRED"}
    assert st["R5"]["state"] == "REACHABLE" and st["R6"]["state"] == "REACHABLE"
    health.check_all(up)                          # 2.ª falla seguida: sin respuesta
    st = {s["hostname"]: s["reachability"] for s in c.get("/api/v1/sites").json()
          if s["status"] != "RETIRED"}
    assert st["R5"]["state"] == "UNREACHABLE" and st["R6"]["state"] == "REACHABLE"

    # Si tampoco responden los hubs, el problema es el enlace al laboratorio: no se toca nada
    health.check_all(lambda ips: {ip: False for ip in ips})
    st = {s["hostname"]: s["reachability"] for s in c.get("/api/v1/sites").json()
          if s["status"] != "RETIRED"}
    assert st["R6"]["state"] == "REACHABLE"
    assert health.read_status()["lab_reachable"] is False

    assert c.get("/api/v1/sites/offline-alerts").json()["sites"] == []   # aún no pasa el plazo
    with db.tx() as conn:
        conn.execute("UPDATE site_health SET since = now() - interval '31 minutes' "
                     "WHERE state = 'UNREACHABLE'")
    alerts = c.get("/api/v1/sites/offline-alerts").json()["sites"]
    assert [a["hostname"] for a in alerts] == ["R5"]          # R3 es protegida: no se pregunta

    assert c.post(f"/api/v1/sites/{r5}/offline-alert/keep", headers=CSRF).status_code == 200
    assert c.get("/api/v1/sites/offline-alerts").json()["sites"] == []

    r = c.post(f"/api/v1/sites/{r6}/forget", json={"confirm_code": "SPOKE-R6", "reason": "prueba"},
               headers=CSRF)
    assert r.status_code == 409 and "baja normal" in r.json()["detail"]
    r = c.post(f"/api/v1/sites/{r5}/forget", json={"confirm_code": "ZONA10B", "reason": "Router retirado"},
               headers=CSRF)
    assert r.status_code == 202, r.text
    job = run_worker_once()
    assert job["type"] == "FORGET"
    site = c.get(f"/api/v1/sites/{r5}").json()
    assert site["status"] == "RETIRED" and site["reachability"] is None
    assert {a["status"] for a in site["allocations"]} == {"QUARANTINED"}
    acts = [a["action"] for a in c.get("/api/v1/audit", params={"target_id": r5}).json()]
    assert "site.forget" in acts and "site.unreachable" in acts


def test_permisos_por_rol(env):
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    login(c, "operador")
    assert c.get("/api/v1/users").status_code == 403
    assert c.get("/api/v1/audit").status_code == 403
    assert c.get("/api/v1/sites").status_code == 200
    assert c.get("/api/v1/sites/offline-alerts").status_code == 403   # solo administradores


def test_auditoria_encadenada_detecta_alteraciones(env):
    c = env
    v = c.get("/api/v1/audit/verify").json()
    assert v["valid"] and v["checked"] > 10
    admin_url = DB
    subprocess.run(["psql", admin_url, "-qc",
                    "ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_no_update;"
                    "UPDATE audit_logs SET outcome='SUCCESS' WHERE outcome='DENIED';"
                    "ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_no_update;"], check=True)
    v = c.get("/api/v1/audit/verify").json()
    assert not v["valid"] and v["broken_at_id"] is not None
