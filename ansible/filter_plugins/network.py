"""Filtros propios usados por los roles."""


def only_present(lines: list[str], running: str) -> list[str]:
    """Devuelve solo las negaciones ('no X') cuyo X existe en la configuración.

    La baja envía únicamente lo que está presente: una segunda ejecución no envía
    nada y reporta changed=0 (idempotencia).
    """
    cfg = [c.strip() for c in running.splitlines()]
    result = []
    for line in lines:
        target = line[3:] if line.startswith("no ") else line
        if any(c.startswith(target) for c in cfg):
            result.append(line)
    return result


class FilterModule:
    def filters(self):
        return {"only_present": only_present}
