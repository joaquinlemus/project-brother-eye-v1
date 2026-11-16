# VPC de tres capas: pública (ALB, gateway), app (ECS), datos (RDS).
# Evita 10.0.0.0/8 porque el esquema 10.(D+s) del proyecto puede ocuparlo.

variable "name" { type = string }
variable "cidr" {
  type    = string
  default = "172.20.0.0/20"
}
variable "azs" { type = list(string) }

locals {
  public = [for i, az in var.azs : cidrsubnet(var.cidr, 4, i)]      # 172.20.0.0/24, 172.20.1.0/24
  app    = [for i, az in var.azs : cidrsubnet(var.cidr, 4, i + 4)]  # 172.20.4.0/24, 172.20.5.0/24
  data   = [for i, az in var.azs : cidrsubnet(var.cidr, 4, i + 8)]  # 172.20.8.0/24, 172.20.9.0/24
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-public-${count.index}", Tier = "public" }
}

resource "aws_subnet" "app" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.app[count.index]
  availability_zone = var.azs[count.index]
  tags              = { Name = "${var.name}-app-${count.index}", Tier = "app" }
}

resource "aws_subnet" "data" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.data[count.index]
  availability_zone = var.azs[count.index]
  tags              = { Name = "${var.name}-data-${count.index}", Tier = "data" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Las rutas de app (0.0.0.0/0 y 172.16.0.0/24 del lab) las agrega el módulo wireguard_gw
resource "aws_route_table" "app" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name}-app" }
}

resource "aws_route_table_association" "app" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app.id
}

output "vpc_id" { value = aws_vpc.this.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "app_subnet_ids" { value = aws_subnet.app[*].id }
output "data_subnet_ids" { value = aws_subnet.data[*].id }
output "app_route_table_id" { value = aws_route_table.app.id }
