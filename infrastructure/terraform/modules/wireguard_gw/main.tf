# EC2 t4g.nano que hace NAT para las subredes privadas y termina el túnel WireGuard
# que inicia el Linux del laboratorio EVE-NG. Sin SSH: administración por SSM.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "vpc_cidr" { type = string }
variable "public_subnet_id" { type = string }
variable "app_route_table_id" { type = string }
variable "lab_cidr" {
  type    = string
  default = "172.16.0.0/24"
}
variable "wg_private_key_param" {
  description = "Nombre del SecureString en SSM con la llave privada WireGuard"
  type        = string
}

data "aws_ssm_parameter" "al2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_security_group" "gw" {
  name   = "${var.name}-wg-gw"
  vpc_id = var.vpc_id

  ingress {
    description = "WireGuard desde el lab (IP dinamica)"
    from_port   = 51820
    to_port     = 51820
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Trafico de las subredes privadas a NAT y al lab"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "gw" {
  name = "${var.name}-wg-gw"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.gw.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "wg_key" {
  role = aws_iam_role.gw.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:aws:ssm:*:*:parameter${var.wg_private_key_param}"
    }]
  })
}

resource "aws_iam_instance_profile" "gw" {
  role = aws_iam_role.gw.name
}

resource "aws_instance" "gw" {
  ami                    = data.aws_ssm_parameter.al2023_arm.value
  instance_type          = "t4g.nano"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [aws_security_group.gw.id]
  iam_instance_profile   = aws_iam_instance_profile.gw.name
  source_dest_check      = false # imprescindible para NAT y para enrutar hacia el lab
  metadata_options { http_tokens = "required" }
  root_block_device { encrypted = true }
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    vpc_cidr      = var.vpc_cidr
    lab_cidr      = var.lab_cidr
    wg_key_param  = var.wg_private_key_param
  })
  tags = { Name = "${var.name}-wg-gw" }
}

resource "aws_eip" "gw" {
  instance = aws_instance.gw.id
}

resource "aws_route" "default_via_nat" {
  route_table_id         = var.app_route_table_id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.gw.primary_network_interface_id
}

resource "aws_route" "lab" {
  route_table_id         = var.app_route_table_id
  destination_cidr_block = var.lab_cidr
  network_interface_id   = aws_instance.gw.primary_network_interface_id
}

output "public_ip" { value = aws_eip.gw.public_ip }
