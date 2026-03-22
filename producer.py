from kafka import KafkaProducer
import time
from config import KAFKA_BOOTSTRAP_SERVERS, TOPIC_NAME
from data_generator import CinemaEventGenerator


def main():
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: v.encode('utf-8')
        )

        print(f"Producer started. Sending messages to topic: {TOPIC_NAME}")
        print(f"Connected to Kafka at: {KAFKA_BOOTSTRAP_SERVERS}")

        counter = 0
        while True:
            # Генерация сообщения
            message = CinemaEventGenerator.generate()

            # Отправка в Kafka
            future = producer.send(TOPIC_NAME, value=message)
            result = future.get(timeout=10)

            counter += 1
            print(f"[{counter}] Sent: {message} | Partition: {result.partition}, Offset: {result.offset}")

            time.sleep(2)  # Пауза между сообщениями

    except KeyboardInterrupt:
        print("\nProducer stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure Kafka is running on localhost:9092")
    finally:
        producer.close()


if __name__ == "__main__":
    main()