# Producción: mismos módulos que lab. Diferencias previstas: NAT Gateway por AZ, RDS Multi-AZ,
# WAF, Site-to-Site VPN en lugar de WireGuard (ver sección 14.2 del documento).
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
  backend "s3" {
    bucket       = "xyz-sdn-tfstate"          # creado una vez a mano o con bootstrap/
    key          = "prod/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true                       # bloqueo nativo en S3, sin DynamoDB
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = { Project = "xyz-sdn-portal", Environment = "prod", ManagedBy = "terraform" }
  }
}

locals {
  name = "xyz-prod"
  azs  = ["us-east-1a", "us-east-1b"]
}

module "network" {
  source = "../../modules/network"
  name   = local.name
  azs    = local.azs
}

module "wireguard_gw" {
  source               = "../../modules/wireguard_gw"
  name                 = local.name
  vpc_id               = module.network.vpc_id
  vpc_cidr             = "172.20.0.0/20"
  public_subnet_id     = module.network.public_subnet_ids[0]
  app_route_table_id   = module.network.app_route_table_id
  wg_private_key_param = "/xyz/prod/wireguard/private_key"
}

# Módulos siguientes (ver docs/ y el roadmap, semanas 3-7):
#  - modules/data:        RDS PostgreSQL 16 db.t4g.micro, cifrado KMS, subred de datos
#  - modules/ecs_cluster: cluster, ECR, task definitions (frontend, api, worker, runner)
#  - modules/edge:        ALB, ACM, Route 53, (WAF en prod)
#  - modules/identity:    Cognito User Pool con MFA TOTP obligatorio
#  - modules/messaging:   SQS jobs + DLQ, EventBridge para tareas programadas
#  - modules/secrets:     Secrets Manager xyz/network/* (sin valores en Terraform)
#  - modules/github_oidc: rol que asume GitHub Actions sin llaves estáticas

output "wireguard_endpoint" {
  value       = module.wireguard_gw.public_ip
  description = "Endpoint al que se conecta el Linux del laboratorio"
}

variable "image_tag" {
  description = "Commit cuyas imágenes se despliegan (lo pasa deploy.yml)"
  type        = string
  default     = "latest"
}
