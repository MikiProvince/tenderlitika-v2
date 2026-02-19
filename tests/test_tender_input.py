import pytest
from pydantic import ValidationError

from models.tender import TenderInput


def test_tender_input_rejects_blank_text():
    with pytest.raises(ValidationError):
        TenderInput(
            text=" " * 60,
            cost_price=1000,
            planned_margin_percent=10,
        )


def test_tender_input_rejects_out_of_range_margin():
    with pytest.raises(ValidationError):
        TenderInput(
            text="Tender text " * 10,
            cost_price=1000,
            planned_margin_percent=101,
        )


def test_tender_input_accepts_valid_payload():
    model = TenderInput(
        text="Tender text " * 10,
        cost_price=1000,
        planned_margin_percent=15,
    )

    assert model.cost_price == 1000
    assert model.planned_margin_percent == 15
