from kafka import KafkaConsumer
import json
from config import KAFKA_BOOTSTRAP_SERVERS, TOPIC_NAME
from validator import MessageValidator


def main():
    try:
        consumer = KafkaConsumer(
            TOPIC_NAME,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='cinema-consumer-group',
            value_deserializer=lambda v: v.decode('utf-8'),
            consumer_timeout_ms=1000
        )

        print(f"Consumer started. Listening to topic: {TOPIC_NAME}")
        print(f"Connected to Kafka at: {KAFKA_BOOTSTRAP_SERVERS}")

        for message in consumer:
            received_data = message.value

            # Валидация
            is_valid, validation_message = MessageValidator.validate(received_data)

            if is_valid:
                print(f"✓ VALID: {received_data}")
            else:
                print(f"✗ NOT VALID: {received_data} | Reason: {validation_message}")

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure Kafka is running on localhost:9092")


if __name__ == "__main__":
    main()