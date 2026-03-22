import json
import random
import uuid
from datetime import datetime


class CinemaEventGenerator:
    @staticmethod
    def generate():
        event_types = ['view_movie', 'view_series', 'new_subscription', 'cancel_subscription', 'add_review']
        users = [f'user_{i}' for i in range(1, 101)]
        movies = ['Inception', 'The Matrix', 'Interstellar', 'Dune', 'Barbie']
        series = ['Stranger Things', 'The Crown', 'House of Dragons']

        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": random.choice(event_types),
            "user_id": random.choice(users),
            "data": {}
        }

        if event['event_type'] in ['view_movie', 'view_series']:
            if event['event_type'] == 'view_movie':
                event['data']['title'] = random.choice(movies)
            else:
                event['data']['title'] = random.choice(series)
            event['data']['progress_percent'] = random.randint(0, 100)
        elif event['event_type'] == 'new_subscription':
            event['data']['plan'] = random.choice(['Basic', 'Premium', 'Family'])
            event['data']['price'] = random.choice([7.99, 12.99, 17.99])
        elif event['event_type'] == 'cancel_subscription':
            event['data']['reason'] = random.choice(['too_expensive', 'not_using', 'technical_issues'])
        elif event['event_type'] == 'add_review':
            event['data']['rating'] = random.randint(1, 5)
            event['data']['comment'] = "Great content!" if random.random() > 0.3 else "Not bad"

        return json.dumps(event, ensure_ascii=False)