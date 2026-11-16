# ADR 0002 — Ansible como tarea efímera de ECS Fargate

- **Estado:** aceptado
- **Fecha:** 2026-11-04

## Contexto

El motor de automatización debe vivir en AWS. Opciones: AWX, Ansible Automation Platform,
Ansible en ECS, Ansible en EC2.

## Decisión

Cada job lanza una tarea ECS Fargate (`RunTask`) con una imagen inmutable (Execution Environment)
que ejecuta un playbook y termina. El backend depende del puerto `AutomationRunner`; el adaptador
`EcsRunTaskRunner` es el de producción.

## Alternativas descartadas

- **AWX:** requiere Kubernetes (operador) y duplica UI, RBAC e historial que el portal ya tiene.
  Se conserva la posibilidad con un adaptador `AwxRunner`.
- **AAP:** costo de suscripción fuera del alcance académico.
- **EC2:** servidor persistente con deriva de configuración y mantenimiento.

## Consecuencias

- Arranque de 30–60 s por job.
- No hay UI de Ansible: el callback `portal_events` envía cada tarea a la API.
- El runner necesita ruta hacia el lab (WireGuard) y un rol IAM mínimo.
