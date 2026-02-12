from pydantic import BaseModel

class TenderInput(BaseModel):
    text: str
    cost_price: float
    planned_margin_percent: float
