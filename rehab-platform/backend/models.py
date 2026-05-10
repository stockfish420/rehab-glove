from pydantic import BaseModel


class RepKPI(BaseModel):
    rep_number: int
    angle_sensor: float
    angle_optical: float
    accuracy_delta: float
    pressure: float
    timestamp: float
