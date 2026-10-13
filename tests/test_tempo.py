from datetime import datetime, timedelta, timezone

import pytest

from app.tempo import agora, ler, texto


def test_grava_sempre_em_utc():
    brasilia = timezone(timedelta(hours=-3))
    assert texto(datetime(2026, 10, 13, 12, 0, tzinfo=brasilia)) == "2026-10-13T15:00:00+00:00"


def test_recusa_data_sem_fuso():
    with pytest.raises(ValueError):
        texto(datetime(2026, 10, 13, 12, 0))


def test_ordem_alfabetica_e_cronologica():
    # O SQL compara texto; isso só vale porque todo mundo é gravado em UTC.
    a = texto(datetime(2026, 10, 13, 23, 0, tzinfo=timezone(timedelta(hours=-3))))  # 02:00 UTC do dia 14
    b = texto(datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc))
    assert b < a and ler(b) < ler(a)


def test_le_linha_antiga_sem_fuso_como_utc():
    assert ler("2026-10-13T12:00:00") == datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert agora().tzinfo is not None
