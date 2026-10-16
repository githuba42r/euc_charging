"""Gotway/Begode model table, extracted from EUC World 2.68.0 (res/raw/gotway_euc_list.json).

EUC World selects one of these entries per wheel - by matching the name the wheel
returns for the "N" request against ``match_by_name``, else its firmware string
("V" request) against ``match_by_firmware`` (wh/s.java h(), frame type 0 branch).
Every Gotway/Begode wheel reports voltage scaled as if it were a 16S (67.2 V)
pack, so the entry's ``full_voltage`` is needed to recover the real pack voltage.

Fields: name, make, full_voltage (batteryFullVoltage), empty_voltage
(batteryEmptyVoltage, None = EUC World default of full * 0.7857), speed_correction,
distance_correction (EUC World defaults 1.0), match_by_name, match_by_firmware.
Generated verbatim from the APK resource; do not edit by hand.
"""

from __future__ import annotations

from typing import NamedTuple


class GotwayModel(NamedTuple):
    """One EUC World gotway_euc_list entry."""

    name: str
    make: str | None
    full_voltage: float
    empty_voltage: float | None
    speed_correction: float
    distance_correction: float
    match_by_name: tuple[str, ...]
    match_by_firmware: tuple[str, ...]


GOTWAY_MODELS: tuple[GotwayModel, ...] = (
    GotwayModel('A1', None, 42.0, 32.0, 1.0, 1.0, ('^A1$',), ()),
    GotwayModel('A2', None, 84.0, 62.0, 1.0, 1.0, ('^A2$',), ('^(GW|CF)15110\\d{2}$',)),
    GotwayModel('A5', None, 84.0, 62.0, 1.0, 1.0, ('^A5$',), ()),
    GotwayModel('ACM 16', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('ACM S+', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Blitz', None, 134.4, 99.0, 1.0, 1.0, ('^Blitz$',), ('^(GW|CF)20351\\d{2}$',)),
    GotwayModel('Blitz Pro (134 V)', None, 134.4, 99.0, 1.0, 1.0, ('^Blitz PRO134$',), ('^(GW|CF)20361\\d{2}$',)),
    GotwayModel('Blitz Pro (168 V)', None, 168.0, 124.0, 1.0, 1.0, ('^Blitz PRO$',), ()),
    GotwayModel('C8', None, 84.0, 62.0, 1.0, 1.0, ('^C8$',), ()),
    GotwayModel('Commander C30', 'Extreme Bull', 100.8, 74.0, 1.0, 1.0, ('^Commander C30$',), ()),
    GotwayModel('Commander C38', 'Extreme Bull', 100.8, 74.0, 1.0, 1.0, ('^Commander C38$',), ()),
    GotwayModel('Commander GT', 'Extreme Bull', 134.4, 97.6, 1.0, 1.0, ('^Commander GT$',), ()),
    GotwayModel('Commander Max', 'Extreme Bull', 168.0, 116.0, 1.0, 1.0, ('^MAX$',), ()),
    GotwayModel('Commander Mini', 'Extreme Bull', 134.4, 100.0, 1.0, 1.0, ('^Commander mini$', '^Commander Mini$'), ()),
    GotwayModel('Commander Mini Pro', 'Extreme Bull', 134.4, 100.0, 1.0, 1.0, ('^Commander Mini PRO$',), ()),
    GotwayModel('Commander Pro', 'Extreme Bull', 134.4, 97.6, 1.0, 1.0, ('^Commander Pro$',), ('^JN20122\\d{2}$',)),
    GotwayModel('Commander Pro 50S', 'Extreme Bull', 134.4, 97.6, 1.0, 1.0, ('^CommanderPRO50s$',), ()),
    GotwayModel('EX', None, 100.8, 78.0, 1.0, 1.0, ('^EX$',), ()),
    GotwayModel('EX Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('EX.N', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('EX.N Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('EX.N C30', None, 100.8, 72.0, 1.0, 1.0, (), ('^(GW|CF)20020\\d{2}$',)),
    GotwayModel('EX.N C38', None, 100.8, 72.0, 1.0, 1.0, (), ('^(GW|CF)20120\\d{2}$',)),
    GotwayModel('EX20S C30', None, 100.8, 76.0, 1.0, 1.0, (), ('^(GW|CF)20030\\d{2}$',)),
    GotwayModel('EX20S C38', None, 100.8, 76.0, 1.0, 1.0, (), ('^(GW|CF)20130\\d{2}$',)),
    GotwayModel('EX30 C40', None, 134.4, 99.2, 1.0, 1.0, (), ('^(GW|CF)20250\\d{2}$',)),
    GotwayModel('Extreme', None, 134.4, 99.0, 1.0, 1.0, ('^EXTREME$',), ('^(GW|CF)18250\\d{2}$',)),
    GotwayModel('ET Max', None, 168.0, 124.0, 1.0, 1.0, ('^ET MAX$',), ('^(GW|CF)20260\\d{2}$',)),
    GotwayModel('Falcon', None, 100.8, 72.0, 1.0, 1.0, ('^Falcon$',), ('^(GW|CF)16210\\d{2}$',)),
    GotwayModel('Falcon Pro', None, 100.8, 72.0, 1.0, 1.0, ('^Falcon PRO$',), ('^GW16340\\d{2}$',)),
    GotwayModel('Future', None, 42.0, 32.0, 1.0, 1.0, ('^Future$',), ()),
    GotwayModel('Griffin', 'Extreme Bull', 151.2, 111.6, 1.0, 1.0, ('^Griffin$',), ()),
    GotwayModel('GT Pro', 'Extreme Bull', 168.0, 124.0, 1.0, 1.0, ('^GT PRO$',), ('^JN20260\\d{2}$',)),
    GotwayModel('Hero C30', None, 100.8, 78.0, 1.0, 1.0, (), ('^(GW|CF)20022\\d{2}$',)),
    GotwayModel('Hero C38', None, 100.8, 78.0, 1.0, 1.0, (), ('^(GW|CF)20122\\d{2}$',)),
    GotwayModel('Luffy', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('Master', None, 134.4, 104.0, 1.0, 1.0, (), ('^(GW|CF)20140\\d{2}$', '^(GW|CF)20145\\d{2}$', '^(GW|CF)20148\\d{2}$', '^(GW|CF)20149\\d{2}$', '^(GW|CF)20150\\d{2}$', '^(GW|CF)20151\\d{2}$')),
    GotwayModel('Master Pro', None, 134.4, 99.2, 1.0, 1.0, ('^Master Pro$', '^Master PRO$', '^Master pro 3$', '^Master PRO 3$'), ('^(GW|CF)23040\\d{2}$', '^(GW|CF)23250\\d{2}$')),
    GotwayModel('Master X', None, 134.4, 99.2, 1.0, 1.0, (), ('^(GW|CF)23041\\d{2}$',)),
    GotwayModel('MCM 3', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 4', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 4 HS', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 4 Pro', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 5 (67 V)', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 5 (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('MCM 5 V2', None, 84.0, None, 1.0, 1.0, ('^MCM5$',), ('^(GW|CF)14010\\d{2}$',)),
    GotwayModel('Monster (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Monster (100 V)', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('Monster Pro', None, 100.8, 72.0, 1.0, 1.0, (), ('^(GW|CF)24020\\d{2}$',)),
    GotwayModel('Monster Sport', None, 100.8, None, 1.2, 1.2, (), ()),
    GotwayModel('Monster V2 (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Monster V2 (100 V)', None, 100.8, None, 1.0, 1.0, (), ()),
    GotwayModel('Monster V3 (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Monster V3 (100 V)', None, 100.8, None, 1.0, 1.0, (), ()),
    GotwayModel('Monster V3 Plus', None, 100.8, None, 1.0, 1.0, (), ()),
    GotwayModel('Msuper 3 (67 V)', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('Msuper 3 (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Msuper Pro C30', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('Msuper Pro C30 Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('Msuper Pro C38', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('Msuper Pro C38 Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('Msuper Sport', None, 100.8, None, 1.0, 1.0, (), ()),
    GotwayModel('Msuper V3S+', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Msuper X (84 V)', None, 84.0, None, 1.0, 1.0, (), ('^(GW|CF)19310\\d{2}$',)),
    GotwayModel('Msuper X (100 V)', None, 100.8, None, 1.0, 1.0, (), ('^(GW|CF)19320\\d{2}$',)),
    GotwayModel('Msuper X Plus', None, 100.8, None, 1.0, 1.0, (), ()),
    GotwayModel('Mten 3 (67 V)', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('Mten 3 (84 V)', None, 84.0, 64.0, 1.0, 1.0, (), ('^(GW|CF)10010\\d{2}$',)),
    GotwayModel('Mten 3 Plus', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Mten 4', None, 84.0, 62.0, 1.0, 1.0, (), ('^(GW|CF)10110\\d{2}$',)),
    GotwayModel('Mten 5', None, 84.0, 62.0, 1.0, 1.0, (), ('^(GW|CF)12110\\d{2}$',)),
    GotwayModel('Mten Mini', None, 42.0, 31.0, 1.0, 1.0, ('^Mten mini$',), ('^(GW|CF)11210\\d{2}$',)),
    GotwayModel('Nikola', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Nikola Plus', None, 100.8, 72.0, 1.0, 1.0, (), ('^(GW|CF)17020\\d{2}$',)),
    GotwayModel('Nikola Plus Plus', None, 100.8, 72.0, 1.0, 1.0, (), ()),
    GotwayModel('Panther', None, 168.0, 116.0, 1.0, 1.0, ('^Panther$',), ()),
    GotwayModel('RACE', None, 210.0, 155.0, 1.0, 1.0, ('^RACE$',), ()),
    GotwayModel('Rocket', 'Extreme Bull', 168.0, 120.0, 1.0, 1.0, ('^ROCKET$',), ()),
    GotwayModel('RS C30', None, 100.8, 78.0, 1.0, 1.0, (), ('^(GW|CF)19020\\d{2}$', '^(GW|CF)19030\\d{2}$', '^(GW|CF)19040\\d{2}$')),
    GotwayModel('RS C30 Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('RS C38', None, 100.8, 78.0, 1.0, 1.0, (), ('^(GW|CF)19120\\d{2}$', '^(GW|CF)19130\\d{2}$')),
    GotwayModel('RS C38 Plus', None, 100.8, 78.0, 1.0, 1.0, (), ()),
    GotwayModel('T4', None, 100.8, 72.0, 1.0, 1.0, ('^T4$',), ('^(GW|CF)16121\\d{2}$', '^(GW|CF)16122\\d{2}$')),
    GotwayModel('T4 Pro', None, 100.8, 72.0, 1.0, 1.0, ('^T4 Pro$',), ('^(GW|CF)16125\\d{2}$',)),
    GotwayModel('Tesla (67 V)', None, 67.2, None, 1.0, 1.0, (), ()),
    GotwayModel('Tesla (84 V)', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Tesla 2', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Tesla 2 Plus', None, 84.0, None, 1.0, 1.0, (), ()),
    GotwayModel('Tesla T3', None, 84.0, 65.0, 1.0, 1.0, (), ('^(GW|CF)16010\\d{2}$', '^(GW|CF)16110\\d{2}$')),
    GotwayModel('X-Max', None, 252.0, 186.0, 1.0, 1.0, ('^X PRO$',), ('^GW20282\\d{2}$',)),
    GotwayModel('X-Men C30', 'Extreme Bull', 100.8, 78.0, 1.0, 1.0, ('^X-Men C30$',), ()),
    GotwayModel('X-Men C38', 'Extreme Bull', 100.8, 78.0, 1.0, 1.0, ('^X-Men C38$',), ()),
    GotwayModel('X-Way (134 V)', None, 134.4, 99.2, 1.0, 1.0, ('^XWAY-134$',), ()),
    GotwayModel('X-Way (168 V)', None, 168.0, 124.0, 1.0, 1.0, ('^XWAY-168$',), ()),
)
