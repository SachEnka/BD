import json


class MessageValidator:
    REQUIRED_FIELDS = ['event_id', 'timestamp', 'event_type', 'user_id', 'data']
    VALID_EVENT_TYPES = ['view_movie', 'view_series', 'new_subscription', 'cancel_subscription', 'add_review']

    @staticmethod
    def validate(message_str):
        try:
            data = json.loads(message_str)

            # Проверка наличия всех полей
            for field in MessageValidator.REQUIRED_FIELDS:
                if field not in data:
                    return False, f"Missing field: {field}"

            # Проверка типа события
            if data['event_type'] not in MessageValidator.VALID_EVENT_TYPES:
                return False, f"Invalid event_type: {data['event_type']}"

            # Проверка структуры data
            if not isinstance(data['data'], dict):
                return False, "data must be a dictionary"

            return True, "Valid"

        except json.JSONDecodeError:
            return False, "Invalid JSON format"