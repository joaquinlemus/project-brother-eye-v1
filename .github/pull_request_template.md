## Qué cambia

## Checklist
- [ ] Pruebas agregadas o actualizadas
- [ ] ¿Cambia una plantilla IOS? → `tests/golden` actualizado y playbook corrido **dos veces** en el lab (`changed=0`)
- [ ] ¿Cambia el esquema? → migración reversible (expand/contract)
- [ ] ¿Cambia infraestructura? → `terraform plan` revisado en el comentario del PR
- [ ] Sin secretos ni IPs reales de clientes en el diff
