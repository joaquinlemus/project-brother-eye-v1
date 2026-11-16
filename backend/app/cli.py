"""Administración desde la terminal de la EC2.

  python -m app.cli migrate
  python -m app.cli create-user --username admin --email admin@heladeria.local \
        --name "Administrador" --role admin
  python -m app.cli import-site --site-id 3 --code MAZ-03 --name "Mazate" --protected
  python -m app.cli reset-mfa --username admin
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from app.application import security as sec
from app.application import sites as uc
from app.db import tx
from app.domain.errors import DomainError
from app.infrastructure.repos import AuditRepo, UserRepo

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"


def migrate(args) -> None:
    folder = Path(args.dir) if args.dir else MIGRATIONS
    with tx() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                          version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    for f in sorted(folder.glob("*.sql")):
        if f.stem in done:
            continue
        print(f"Aplicando {f.name} ...")
        with tx() as conn:
            conn.execute(f.read_text())
            conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (f.stem,))
    print("Base de datos al día.")


def create_user(args) -> None:
    pw = args.password or getpass.getpass("Contraseña (mín. 10, letras y números): ")
    with tx() as conn:
        users = UserRepo(conn)
        uid = users.create(args.username.lower(), args.email, args.name, sec.hash_password(pw))
        users.set_roles(uid, args.role)
        AuditRepo(conn).write(None, "user.create", "User", str(uid), "SUCCESS", actor_type="SYSTEM",
                              after={"username": args.username, "roles": args.role, "via": "cli"})
    print(f"Usuario {args.username} creado. En el primer ingreso deberá escanear el QR de MFA.")


def reset_mfa(args) -> None:
    with tx() as conn:
        users = UserRepo(conn)
        u = users.by_username(args.username)
        if not u:
            sys.exit("No existe el usuario")
        users.update(u["id"], mfa_enabled=False, mfa_secret_enc=None, mfa_last_step=None,
                     failed_logins=0, locked_until=None)
        AuditRepo(conn).write(None, "user.reset_mfa", "User", str(u["id"]), "SUCCESS",
                              actor_type="SYSTEM", after={"via": "cli"})
    print("MFA reiniciado: en el próximo ingreso se mostrará un QR nuevo.")


def import_site(args) -> None:
    with tx() as conn:
        sid = uc.import_site(conn, AuditRepo(conn), site_number=args.site_id, code=args.code,
                             name=args.name, protected=args.protected, notes=args.notes)
    print(f"R{args.site_id} importado como {args.code} (id {sid})"
          + (" - PROTEGIDO" if args.protected else ""))


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(required=True)
    m = sub.add_parser("migrate")
    m.add_argument("--dir")
    m.set_defaults(fn=migrate)
    u = sub.add_parser("create-user")
    u.add_argument("--username", required=True)
    u.add_argument("--email", required=True)
    u.add_argument("--name", required=True)
    u.add_argument("--role", action="append", required=True,
                   choices=["admin", "netops", "auditor", "viewer"])
    u.add_argument("--password", help="(solo para scripts; si se omite, se pide)")
    u.set_defaults(fn=create_user)
    r = sub.add_parser("reset-mfa")
    r.add_argument("--username", required=True)
    r.set_defaults(fn=reset_mfa)
    i = sub.add_parser("import-site")
    i.add_argument("--site-id", type=int, required=True)
    i.add_argument("--code", required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--protected", action="store_true",
                   help="el portal no permitirá darlo de baja (configurado a mano)")
    i.add_argument("--notes")
    i.set_defaults(fn=import_site)
    args = p.parse_args()
    try:
        args.fn(args)
    except DomainError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
