from pydantic import BaseModel, EmailStr, validator
import re


class Lead(BaseModel):
    name: str
    email: EmailStr
    phone: str
    vehicle: dict

    @validator("phone")
    def validate_phone(cls, v):
        pattern = r"^(514|438|450|581|418|819|873)[- ]?\d{3}[- ]?\d{4}$"
        if not re.match(pattern, v):
            raise ValueError("Numéro invalide (format QC requis)")
        return v


def create_lead(state, user_info):
    lead = Lead(
        name=user_info["name"],
        email=user_info["email"],
        phone=user_info["phone"],
        vehicle=state.selected_vehicle
    )
    return lead.dict()
