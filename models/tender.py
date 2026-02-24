from pydantic import BaseModel, Field, field_validator

class TenderInput(BaseModel):
    text: str = Field(min_length=50, max_length=200_000)
    cost_price: float = Field(gt=0)
    planned_margin_percent: float = Field(ge=0, le=100)
    llm_provider: str | None = Field(default=None, max_length=32)

    @field_validator("text")
    @classmethod
    def validate_text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text cannot be blank")
        return value
