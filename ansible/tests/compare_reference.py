"""Compara la salida de las plantillas con la configuración probada de los routers.

Para cada bloque (línea padre + hijas) generado por una plantilla, verifica que cada
línea exista bajo el mismo padre en tests/reference/<host>.cfg. Las líneas que faltan
son las que Ansible agregaría a un router que ya está bien configurado.
Uso: python3 compare_reference.py out/
"""
import pathlib
import sys

# Plantillas cuya salida debe coincidir con la configuración probada
CHECK = {"tunnels.cfg", "ospf.cfg", "lan.cfg", "ikev2.cfg", "keyring.cfg", "hub_tunnel.cfg"}
IGNORE = {"<PSK>", "PSK-DE-PRUEBA"}


def blocks(text: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    parent = "(global)"
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() == "!":
            continue
        if not line.startswith(" "):
            parent = line
            result.setdefault(parent, set())
        else:
            result.setdefault(parent, set()).add(line.strip())
    return result


def norm(s: str) -> str:
    for token in IGNORE:
        s = s.replace(token, "<PSK>")
    return s


def main(out_dir: str) -> int:
    failures = 0
    for host_dir in sorted(pathlib.Path(out_dir).iterdir()):
        ref = pathlib.Path(__file__).parent / "reference" / f"{host_dir.name}.cfg"
        if not ref.exists():
            continue
        ref_blocks = blocks(norm(ref.read_text()))
        for f in sorted(host_dir.iterdir()):
            if f.name not in CHECK:
                continue
            for parent, children in blocks(norm(f.read_text())).items():
                if parent not in ref_blocks:
                    print(f"{host_dir.name}/{f.name}: FALTA bloque '{parent}'")
                    failures += 1
                    continue
                for child in sorted(children - ref_blocks[parent]):
                    print(f"{host_dir.name}/{f.name}: '{parent}' -> agregaría '{child}'")
                    failures += 1
    print("OK: las plantillas reproducen la configuración probada" if not failures
          else f"{failures} diferencia(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))
