from pydantic import BaseModel, Field, field_validator

class chat_payload(BaseModel):
    query: str
    session_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value
