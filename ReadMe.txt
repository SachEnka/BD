создаем вирутал среду - активируем 


pip install kafka-python

через cmd:
pip install -r requirements.txt
bin\windows\zookeeper-server-start.bat config\zookeeper.properties


топики:
kafka-topics.bat --create --topic cinema-topic --bootstrap-server localhost:9092 --partitions 3 --replication-factor 1