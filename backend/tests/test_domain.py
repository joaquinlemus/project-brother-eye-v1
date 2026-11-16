import ipaddress

import pytest

from app.domain.errors import DomainError, InvalidTransition
from app.domain.ipam.addressing import AddressingPlan, TeamBirthday, first_free
from app.domain.site.model import Site, SiteCode, SiteStatus

BD = TeamBirthday(month=12, day=28)
PLAN = AddressingPlan(BD)


def test_mmdd_sin_ceros_a_la_izquierda():
    assert BD.mmdd == "1228"
    assert TeamBirthday(3, 5).mmdd == "305"


def test_derivacion_sitio_7():
    a = PLAN.derive(7)
    assert a.lan_v4 == [ipaddress.IPv4Network("10.35.0.0/24")]
    assert a.lan_v6 == [ipaddress.IPv6Network("2001:1228:7::/64")]
    assert str(a.loopback0) == "10.254.0.7/32"
    assert str(a.tunnel1_v4) == "192.168.5.7/25"
    assert str(a.tunnel2_v4) == "192.168.5.137/25"
    assert str(a.tunnel1_v6) == "fd00:5::7/64"
    assert str(a.tunnel2_v6) == "fd00:5:1::7/64"


def test_sitio_mediano_tiene_segunda_lan():
    a = PLAN.derive(7, medium=True)
    assert [str(n) for n in a.lan_v4] == ["10.35.0.0/24", "10.35.1.0/24"]
    assert str(a.lan_v6[1]) == "2001:1228:7:1::/64"


def test_limite_evita_colision_con_loopbacks_y_tuneles():
    assert BD.max_site_id == 124            # 130 + 124 = 254, último host del /25 del Hub 2
    PLAN.derive(124)
    with pytest.raises(DomainError):
        PLAN.derive(125)                    # 192.168.5.255 es broadcast
    # con cualquier D <= 129 limita el túnel, no la LAN
    assert TeamBirthday(12, 1).max_site_id == 124
    with pytest.raises(DomainError):
        PLAN.derive(2)                      # reservado para hubs


def test_lan_nunca_solapa_infraestructura():
    infra = [ipaddress.ip_network("10.254.0.0/24"), ipaddress.ip_network("192.168.5.0/24")]
    for s in range(3, BD.max_site_id + 1):
        lan = PLAN.derive(s).lan_v4[0]
        assert not any(lan.overlaps(n) for n in infra), s


def test_tuneles_quedan_en_su_nube():
    n1, n2 = ipaddress.ip_network("192.168.5.0/25"), ipaddress.ip_network("192.168.5.128/25")
    hubs = {ipaddress.ip_address("192.168.5.1"), ipaddress.ip_address("192.168.5.132")}
    for s in range(3, BD.max_site_id + 1):
        a = PLAN.derive(s)
        assert a.tunnel1_v4.ip in n1 and a.tunnel1_v4.network == n1
        assert a.tunnel2_v4.ip in n2 and a.tunnel2_v4.network == n2
        assert a.tunnel2_v4.ip != n2.broadcast_address
        assert not {a.tunnel1_v4.ip, a.tunnel2_v4.ip} & hubs


def test_first_fit_respeta_cuarentena():
    assert first_free(range(3, 10), {3, 4, 6}) == 5
    assert first_free(range(3, 5), {3, 4}) is None


def test_maquina_de_estados():
    import uuid
    site = Site(code=SiteCode("ANT-07"), name="Antigua", site_number=7, created_by=uuid.uuid4())
    with pytest.raises(InvalidTransition):
        site.mark_retired()                 # no se puede retirar algo que no está activo
    site.mark_active()
    with pytest.raises(DomainError):
        site.request_decommission("OTRO")   # confirmación incorrecta
    site.request_decommission("ANT-07")
    site.mark_retired()
    assert site.status is SiteStatus.RETIRED
    assert site.hostname == "R7"


@pytest.mark.parametrize("bad", ["ant-07", "A;", "R7\nshutdown", "X" * 17])
def test_codigo_de_sitio_rechaza_inyeccion(bad):
    with pytest.raises(DomainError):
        SiteCode(bad)


def test_ids_reservados_se_calculan_contra_la_infraestructura():
    from app.domain.ipam.addressing import reserved_site_ids
    r = reserved_site_ids(PLAN, range(3, 125), ["172.16.0.20"], ["10.99.0.0/24", "10.254.0.0/24"])
    assert set(r) == {20, 71}
    assert "172.16.0.20" in r[20]                 # underlay = Ubuntu de Zabbix
    assert "10.99.0.0/24" in r[71]                # LAN 10.(28+71) = WireGuard
    # Con otro cumpleaños cambia el ID que choca con WireGuard: no está fijo a mano
    otro = AddressingPlan(TeamBirthday(month=3, day=5))
    assert 94 in reserved_site_ids(otro, range(3, 125), [], ["10.99.0.0/24"])
