from database import get_all_vehicles


class VehicleRepository:

    @staticmethod
    def get_all():
        return get_all_vehicles()