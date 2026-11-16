#!/usr/bin/env bash
# Ejecuta 'alembic upgrade head' como tarea ECS de un solo uso con la imagen del backend.
set -euo pipefail
ENV="${1:?ambiente}"; TAG="${2:?tag}"
CLUSTER="xyz-$ENV"
SUBNETS=$(aws ssm get-parameter --name "/xyz/$ENV/app_subnets" --query Parameter.Value --output text)
SG=$(aws ssm get-parameter --name "/xyz/$ENV/api_sg" --query Parameter.Value --output text)
TASK=$(aws ecs run-task --cluster "$CLUSTER" --launch-type FARGATE \
  --task-definition "xyz-$ENV-migrate" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG]}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"api\",\"command\":[\"alembic\",\"upgrade\",\"head\"]}]}" \
  --query 'tasks[0].taskArn' --output text)
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK"
EXIT=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[0].containers[0].exitCode' --output text)
[ "$EXIT" = "0" ] || { echo "Migración falló (exit $EXIT) con imagen $TAG"; exit 1; }
