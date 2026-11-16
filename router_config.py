from netmiko import ConnectHandler
import signal, sys, time
from getpass import getpass

def signal_handler(sig, frame):
    print("\n[!] Exitting...\n")
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)

def get_router_config(hostname, octet, password):
    with open("router-template.cfg", "r") as f:
        router_template = f.read()
    router_config = (router_template
                .replace("R<N>", f"R{hostname}")
                .replace("<N>", octet)
                .replace("<PASSWORD>", password))
    return router_config             

def get_vpc_config(hostname):
    with open("vpc-template.cfg", "r") as f:
        vpc_template = f.read()
    N = int(hostname) + 28
    vpc_config = (vpc_template.replace("PC-<N>", f"PC-R{hostname}")
                .replace("10.<N>.0.10/24", f"10.{N}.0.10/24")
                .replace("10.<N>.0.1", f"10.{N}.0.1")
                .replace("2001:1228:<R>::10/64", f"2001:1228:{hostname}::10/64"))
    return vpc_config             

def init_router(router_port, hostname, octet, password):
    router = {
        "device_type": "cisco_ios_telnet",
        "host": "192.168.11.128",
        "port": router_port,
        "username": "",
        "password": "",
    }

    with ConnectHandler(**router) as conn:
        conn.enable()
        router_configuration = conn.send_config_set(
            get_router_config(hostname, octet, password).splitlines(),
            read_timeout=60
        )
        print(router_configuration)
        conn.set_base_prompt()
        conn.save_config()

def init_vpc(hostname, vpc_port):
    vpc = {
        "device_type": "generic_termserver_telnet",
        "host": "192.168.11.128",
        "port": vpc_port
    }

    with ConnectHandler(**vpc) as conn:
        conn.write_channel("\r\n")
        time.sleep(1)
        conn.read_channel()

        for config in get_vpc_config(hostname).splitlines():
            print(conn.send_command_timing(config))

def ask_int(prompt):
    while True:
        valor = input(prompt).strip()
        if valor.isdigit():
            return int(valor)
        print("  -> Must be an integer, try again.")


def configure_router():
    router_port = ask_int("Enter EVE-NG router port: ")
    hostname = ask_int("Enter router hostname number: ")
    octet = ask_int("Enter router octet: ")
    password = getpass("Enter router password: ")
    print(repr(password), len(password))
    init_router(router_port, str(hostname), str(octet), password)


def configure_vpc():
    vpc_port = ask_int("Enter EVE-NG VPC port: ")
    hostname = ask_int("Enter VPC/Router number: ")
    init_vpc(str(hostname), vpc_port)


MENU = {
    "1": ("Router configuration", configure_router),
    "2": ("VPC configuration", configure_vpc),
}

def main():
    while True:
        print("\n" + "=" * 40)
        for key, (label, _) in MENU.items():
            print(f"  {key}. {label}")
        print("  q. Quit")
        print("=" * 40)

        choice = input("Select an option: ").strip().lower()

        if choice == "q":
            break
        if choice not in MENU:
            print("Invalid option.")
            continue

        _, action = MENU[choice]
        try:
            action()
        except Exception as e:
            print(f"Error: {e}")
    
if __name__=='__main__':
    main()