import json
import sqlite3
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum



logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('airflow_simulator.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)



class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TaskInstance:
    
    task_id: str
    python_callable: Callable
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    start_time: datetime = None
    end_time: datetime = None
    result: Any = None
    error: str = None

@dataclass
class DAGRun:
    """Запуск DAG"""
    dag_id: str
    execution_date: datetime
    run_id: str
    status: str = "running"
    tasks: Dict[str, TaskInstance] = field(default_factory=dict)
    start_time: datetime = None
    end_time: datetime = None



class AirflowSimulator:
    

    def __init__(self):
        self.dags = {}
        self.dag_runs = []
        self.database_path = Path("data/airflow_metadata.db")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_metadata_db()

    def _init_metadata_db(self):
       
        conn = sqlite3.connect(str(self.database_path))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dag (
                dag_id TEXT PRIMARY KEY,
                description TEXT,
                schedule_interval TEXT,
                is_active BOOLEAN,
                created_at TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dag_run (
                run_id TEXT PRIMARY KEY,
                dag_id TEXT,
                execution_date TIMESTAMP,
                status TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                FOREIGN KEY (dag_id) REFERENCES dag(dag_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_instance (
                task_id TEXT,
                dag_id TEXT,
                run_id TEXT,
                status TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration REAL,
                error TEXT,
                PRIMARY KEY (task_id, dag_id, run_id)
            )
        ''')

        conn.commit()
        conn.close()

    def register_dag(self, dag):
        """Регистрация DAG"""
        self.dags[dag.dag_id] = dag
        logger.info(f" DAG '{dag.dag_id}' зарегистрирован")
        logger.info(f"   Описание: {dag.description}")
        logger.info(f"   Расписание: {dag.schedule_interval}")
        logger.info(f"   Задач: {len(dag.tasks)}")

    def trigger_dag(self, dag_id: str, execution_date: datetime = None):
        """Ручной запуск DAG"""
        if dag_id not in self.dags:
            logger.error(f" DAG '{dag_id}' не найден")
            return None

        if execution_date is None:
            execution_date = datetime.now()

        dag = self.dags[dag_id]
        run_id = f"{dag_id}_manual_{execution_date.strftime('%Y%m%d_%H%M%S')}"

        dag_run = DAGRun(
            dag_id=dag_id,
            execution_date=execution_date,
            run_id=run_id,
            start_time=datetime.now(),
            tasks={}
        )

        # Создаем копии задач для этого запуска
        for task_id, task in dag.tasks.items():
            dag_run.tasks[task_id] = TaskInstance(
                task_id=task_id,
                python_callable=task.python_callable,
                depends_on=task.depends_on.copy(),
                status=TaskStatus.PENDING
            )

        self.dag_runs.append(dag_run)

        logger.info(f"\n{'='*70}")
        logger.info(f" ЗАПУСК DAG: {dag_id}")
        logger.info(f"   Run ID: {run_id}")
        logger.info(f"   Execution Date: {execution_date}")
        logger.info(f"{'='*70}\n")

        # Выполняем DAG
        success = self._execute_dag(dag_run)

        dag_run.end_time = datetime.now()
        dag_run.status = "success" if success else "failed"

        # Сохраняем в метабазу
        self._save_dag_run(dag_run)

        # Выводим итоговый отчет
        self._print_execution_summary(dag_run)

        return dag_run

    def _execute_dag(self, dag_run: DAGRun) -> bool:
        """Выполнение DAG с учетом зависимостей"""
        executed = set()

        while len(executed) < len(dag_run.tasks):
            progress_made = False

            for task_id, task in dag_run.tasks.items():
                if task.status != TaskStatus.PENDING:
                    continue

                # Проверяем зависимости
                deps_met = True
                for dep in task.depends_on:
                    if dep not in executed:
                        deps_met = False
                        break

                if deps_met:
                    logger.info(f"\n Выполнение задачи: {task_id}")
                    task.status = TaskStatus.RUNNING
                    task.start_time = datetime.now()

                    try:
                        # Выполнение функции задачи
                        result = task.python_callable(dag_run)
                        task.result = result
                        task.status = TaskStatus.SUCCESS
                        logger.info(f" Задача '{task_id}' выполнена успешно")
                    except Exception as e:
                        task.status = TaskStatus.FAILED
                        task.error = str(e)
                        logger.error(f" Ошибка в задаче '{task_id}': {e}")
                        return False

                    task.end_time = datetime.now()
                    duration = (task.end_time - task.start_time).total_seconds()
                    logger.info(f"   ⏱️  Время выполнения: {duration:.2f} сек")

                    executed.add(task_id)
                    progress_made = True
                    break  # Перезапускаем цикл для проверки новых доступных задач

            if not progress_made:
                logger.error(" Обнаружены циклические зависимости или недостижимые задачи")
                return False

        return True

    def _save_dag_run(self, dag_run: DAGRun):
        """Сохранение информации о запуске в метабазу"""
        conn = sqlite3.connect(str(self.database_path))
        cursor = conn.cursor()


        cursor.execute('''
            INSERT OR REPLACE INTO dag_run (run_id, dag_id, execution_date, status, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (dag_run.run_id, dag_run.dag_id, dag_run.execution_date.isoformat(),
              dag_run.status, dag_run.start_time.isoformat() if dag_run.start_time else None,
              dag_run.end_time.isoformat() if dag_run.end_time else None))

    
        for task_id, task in dag_run.tasks.items():
            duration = None
            if task.start_time and task.end_time:
                duration = (task.end_time - task.start_time).total_seconds()

            cursor.execute('''
                INSERT OR REPLACE INTO task_instance 
                (task_id, dag_id, run_id, status, start_time, end_time, duration, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (task_id, dag_run.dag_id, dag_run.run_id, task.status.value,
                  task.start_time.isoformat() if task.start_time else None,
                  task.end_time.isoformat() if task.end_time else None,
                  duration, task.error))

        conn.commit()
        conn.close()

    def _print_execution_summary(self, dag_run: DAGRun):
        """Вывод сводки выполнения"""
        total_duration = (dag_run.end_time - dag_run.start_time).total_seconds()
        success_count = sum(1 for t in dag_run.tasks.values() if t.status == TaskStatus.SUCCESS)
        failed_count = sum(1 for t in dag_run.tasks.values() if t.status == TaskStatus.FAILED)

        logger.info(f"\n{'='*70}")
        logger.info(f"📊 СВОДКА ВЫПОЛНЕНИЯ DAG")
        logger.info(f"{'='*70}")
        logger.info(f"DAG ID: {dag_run.dag_id}")
        logger.info(f"Run ID: {dag_run.run_id}")
        logger.info(f"Статус: {dag_run.status.upper()}")
        logger.info(f"Общее время: {total_duration:.2f} сек")
        logger.info(f"Успешных задач: {success_count}/{len(dag_run.tasks)}")
        if failed_count > 0:
            logger.warning(f"Проваленных задач: {failed_count}")

        logger.info(f"\n📋 ДЕТАЛИЗАЦИЯ ПО ЗАДАЧАМ:")
        for task_id, task in dag_run.tasks.items():
            duration = (task.end_time - task.start_time).total_seconds() if task.end_time and task.start_time else 0
            status_icon = "✅" if task.status == TaskStatus.SUCCESS else "❌" if task.status == TaskStatus.FAILED else "⏸️"
            logger.info(f"   {status_icon} {task_id}: {task.status.value} ({duration:.2f} сек)")

        logger.info(f"{'='*70}\n")


@dataclass
class DAG:
    """Класс DAG"""
    dag_id: str
    description: str
    schedule_interval: str
    tasks: Dict[str, TaskInstance] = field(default_factory=dict)
    default_args: Dict = field(default_factory=dict)



def create_data_directories():
    """Создание необходимых директорий"""
    directories = ['data/input', 'data/output', 'data/processed']
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

def task_extract_data(dag_run: DAGRun) -> Dict:
   
    logger.info("=" * 50)
    logger.info("📥 ЗАДАЧА 1: ИЗВЛЕЧЕНИЕ ДАННЫХ")
    logger.info("=" * 50)


    pets_data = [
        {"id": 1, "name": "Бобик", "species": "dog", "breed": "Лабрадор", "age": 3, "weight": 25.5, "owner_id": 101},
        {"id": 2, "name": "Мурка", "species": "cat", "breed": "Персидская", "age": 2, "weight": 4.2, "owner_id": 102},
        {"id": 3, "name": "Кеша", "species": "bird", "breed": "Волнистый", "age": 1, "weight": 0.5, "owner_id": 101},
        {"id": 4, "name": "Рекс", "species": "dog", "breed": "Немецкая овчарка", "age": 5, "weight": 30.0, "owner_id": 103},
        {"id": 5, "name": "Снежок", "species": "rabbit", "breed": "Белый великан", "age": 2, "weight": 3.2, "owner_id": 102},
    ]


    owners_data = [
        {"id": 101, "name": "Иван Петров", "phone": "+7(999)123-45-67", "address": "ул. Ленина, 1", "email": "ivan@example.com"},
        {"id": 102, "name": "Мария Сидорова", "phone": "+7(999)987-65-43", "address": "ул. Пушкина, 5", "email": "maria@example.com"},
        {"id": 103, "name": "Алексей Иванов", "phone": "+7(999)555-12-34", "address": "ул. Гагарина, 10", "email": "alex@example.com"},
    ]


    services_data = [
        {"id": 201, "name": "Общий осмотр", "price": 1500.0, "duration_minutes": 30},
        {"id": 202, "name": "Вакцинация", "price": 1200.0, "duration_minutes": 20},
        {"id": 203, "name": "Хирургия", "price": 5000.0, "duration_minutes": 60},
        {"id": 204, "name": "Анализ крови", "price": 800.0, "duration_minutes": 15},
        {"id": 205, "name": "УЗИ", "price": 2000.0, "duration_minutes": 25},
    ]

    # JSON файлы
    with open('data/input/pets.json', 'w', encoding='utf-8') as f:
        json.dump(pets_data, f, ensure_ascii=False, indent=2)

    with open('data/input/owners.json', 'w', encoding='utf-8') as f:
        json.dump(owners_data, f, ensure_ascii=False, indent=2)

    with open('data/input/services.json', 'w', encoding='utf-8') as f:
        json.dump(services_data, f, ensure_ascii=False, indent=2)

    # Вывод статистики
    logger.info(f" Извлеченные данные:")
    logger.info(f"   • Питомцы: {len(pets_data)}")
    logger.info(f"   • Владельцы: {len(owners_data)}")
    logger.info(f"   • Услуги: {len(services_data)}")

    return {
        'pets_count': len(pets_data),
        'owners_count': len(owners_data),
        'services_count': len(services_data),
        'extraction_time': datetime.now().isoformat()
    }

def task_transform_data(dag_run: DAGRun) -> Dict:
   
    logger.info("=" * 50)
    logger.info(" ЗАДАЧА 2: ТРАНСФОРМАЦИЯ ДАННЫХ")
    logger.info("=" * 50)

    # Загрузка данных
    with open('data/input/pets.json', 'r', encoding='utf-8') as f:
        pets = json.load(f)

    with open('data/input/owners.json', 'r', encoding='utf-8') as f:
        owners = json.load(f)

    with open('data/input/services.json', 'r', encoding='utf-8') as f:
        services = json.load(f)

 
    species_distribution = {}
    breed_distribution = {}
    total_weight = 0
    total_age = 0

    for pet in pets:
        species = pet['species']
        species_distribution[species] = species_distribution.get(species, 0) + 1

        breed = pet.get('breed', 'Неизвестно')
        breed_distribution[breed] = breed_distribution.get(breed, 0) + 1

        total_weight += pet['weight']
        total_age += pet['age']

    avg_weight = total_weight / len(pets) if pets else 0
    avg_age = total_age / len(pets) if pets else 0

 
    pets_per_owner = {}
    for owner in owners:
        owner_pets = [p for p in pets if p['owner_id'] == owner['id']]
        pets_per_owner[owner['name']] = len(owner_pets)


    total_revenue_potential = sum(s['price'] for s in services)

    #  аналит отч
    analysis_report = {
        'execution_time': datetime.now().isoformat(),
        'summary': {
            'total_pets': len(pets),
            'total_owners': len(owners),
            'total_services': len(services),
            'avg_pet_age': round(avg_age, 1),
            'avg_pet_weight': round(avg_weight, 1),
            'total_revenue_potential': total_revenue_potential
        },
        'species_distribution': species_distribution,
        'breed_distribution': breed_distribution,
        'pets_per_owner': pets_per_owner
    }

    # Сохраняем JSON отчет
    with open('data/output/analysis_report.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_report, f, ensure_ascii=False, indent=2)

    # Создаем текстовый отчет
    report_lines = [
        "=" * 60,
        " ОТЧЕТ ВЕТЕРИНАРНОЙ КЛИНИКИ",
        "=" * 60,
        f"Дата формирования: {analysis_report['execution_time']}",
        "",
        " ОБЩАЯ СТАТИСТИКА:",
        f"   • Всего питомцев: {analysis_report['summary']['total_pets']}",
        f"   • Всего владельцев: {analysis_report['summary']['total_owners']}",
        f"   • Доступно услуг: {analysis_report['summary']['total_services']}",
        f"   • Средний возраст питомцев: {analysis_report['summary']['avg_pet_age']} лет",
        f"   • Средний вес: {analysis_report['summary']['avg_pet_weight']} кг",
        "",
        " РАСПРЕДЕЛЕНИЕ ПО ВИДАМ:",
    ]

    species_names = {
        'dog': ' Собаки',
        'cat': ' Кошки',
        'bird': ' Птицы',
        'rabbit': ' Кролики'
    }

    for species, count in species_distribution.items():
        name = species_names.get(species, species)
        report_lines.append(f"   • {name}: {count}")

    report_lines.extend([
        "",
        " ПИТОМЦЫ ПО ВЛАДЕЛЬЦАМ:",
    ])

    for owner, count in pets_per_owner.items():
        report_lines.append(f"   • {owner}: {count} питомец(ев)")

    report_lines.extend([
        "",
        " ЭКОНОМИЧЕСКИЕ ПОКАЗАТЕЛИ:",
        f"   • Потенциальная выручка: {total_revenue_potential:.2f} руб.",
        "",
        "=" * 60,
    ])

    with open('data/output/report.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    logger.info(f"📄 Созданы отчеты в 'data/output/'")

    return analysis_report

def task_load_to_database(dag_run: DAGRun) -> Dict:
    """
    Задача 3: Загрузка данных в базу данных
    """
    logger.info("=" * 50)
    logger.info("💾 ЗАДАЧА 3: ЗАГРУЗКА В БАЗУ ДАННЫХ")
    logger.info("=" * 50)

    with open('data/input/pets.json', 'r', encoding='utf-8') as f:
        pets = json.load(f)

    with open('data/input/owners.json', 'r', encoding='utf-8') as f:
        owners = json.load(f)

    with open('data/input/services.json', 'r', encoding='utf-8') as f:
        services = json.load(f)

    conn = sqlite3.connect('data/veterinary_clinic.db')
    cursor = conn.cursor()


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pets (
            id INTEGER PRIMARY KEY,
            name TEXT,
            species TEXT,
            breed TEXT,
            age INTEGER,
            weight REAL,
            owner_name TEXT,
            processed_date TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS owners (
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            address TEXT,
            email TEXT,
            registered_date TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL,
            duration_minutes INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dag_run_id TEXT,
            task_name TEXT,
            status TEXT,
            records_processed INTEGER,
            timestamp TEXT
        )
    ''')


    owners_dict = {o['id']: o['name'] for o in owners}

    for pet in pets:
        cursor.execute('''
            INSERT OR REPLACE INTO pets (id, name, species, breed, age, weight, owner_name, processed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pet['id'], pet['name'], pet['species'], pet.get('breed', ''),
              pet['age'], pet['weight'], owners_dict.get(pet['owner_id'], 'Unknown'),
              datetime.now().isoformat()))

    for owner in owners:
        cursor.execute('''
            INSERT OR REPLACE INTO owners (id, name, phone, address, email, registered_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (owner['id'], owner['name'], owner['phone'], owner.get('address', ''),
              owner.get('email', ''), datetime.now().isoformat()))

    for service in services:
        cursor.execute('''
            INSERT OR REPLACE INTO services (id, name, price, duration_minutes)
            VALUES (?, ?, ?, ?)
        ''', (service['id'], service['name'], service['price'], service['duration_minutes']))

    cursor.execute('''
        INSERT INTO processing_log (dag_run_id, task_name, status, records_processed, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (dag_run.run_id, 'load_to_database', 'SUCCESS', len(pets), datetime.now().isoformat()))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM pets")
    pets_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM owners")
    owners_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM services")
    services_count = cursor.fetchone()[0]

    conn.close()

    logger.info(f"✅ Данные загружены в базу данных:")
    logger.info(f"   • Питомцев: {pets_count}")
    logger.info(f"   • Владельцев: {owners_count}")
    logger.info(f"   • Услуг: {services_count}")

    return {
        'pets_loaded': pets_count,
        'owners_loaded': owners_count,
        'services_loaded': services_count,
        'database_path': 'data/veterinary_clinic.db'
    }

def task_generate_final_report(dag_run: DAGRun) -> Dict:
    """
   
    """
    logger.info("=" * 50)
    logger.info("📊 ЗАДАЧА 4: ГЕНЕРАЦИЯ ИТОГОВОГО ОТЧЕТА")
    logger.info("=" * 50)

    final_report = {
        'dag_info': {
            'dag_id': dag_run.dag_id,
            'run_id': dag_run.run_id,
            'execution_date': dag_run.execution_date.isoformat(),
            'completion_time': datetime.now().isoformat()
        },
        'tasks_status': {},
        'summary': {}
    }

    total_duration = 0

    for task_id, task in dag_run.tasks.items():
        duration = 0
        if task.start_time and task.end_time:
            duration = (task.end_time - task.start_time).total_seconds()
            total_duration += duration

        final_report['tasks_status'][task_id] = {
            'status': task.status.value,
            'duration_seconds': round(duration, 2),
            'error': task.error
        }

    try:
        with open('data/output/analysis_report.json', 'r', encoding='utf-8') as f:
            analysis = json.load(f)
            final_report['summary'] = analysis.get('summary', {})
    except:
        pass

    final_report['total_duration_seconds'] = round(total_duration, 2)


    with open('data/output/final_dag_report.json', 'w', encoding='utf-8') as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    print("\n" + "="*70)
    print("🏥 ИТОГОВЫЙ ОТЧЕТ О ВЫПОЛНЕНИИ DAG")
    print("="*70)
    print(f"DAG ID: {final_report['dag_info']['dag_id']}")
    print(f"Run ID: {final_report['dag_info']['run_id']}")
    print(f"Статус: {'✅ УСПЕШНО' if dag_run.status == 'success' else 'УСПЕШНО'}")
    print(f"Общее время выполнения: {final_report['total_duration_seconds']:.2f} сек")

    if final_report['summary']:
        print(f"\n📊 ИТОГИ ОБРАБОТКИ:")
        print(f"   • Питомцев обработано: {final_report['summary'].get('total_pets', 0)}")
        print(f"   • Владельцев обработано: {final_report['summary'].get('total_owners', 0)}")
        print(f"   • Средний возраст: {final_report['summary'].get('avg_pet_age', 0)} лет")

    print("="*70 + "\n")

    logger.info(f" Итоговый отчет сохранен в 'data/output/final_dag_report.json'")

    return final_report

#creat DAG

def create_veterinary_clinic_dag():
    """Создание DAG для ветеринарной клиники"""

    dag = DAG(
        dag_id='veterinary_clinic_etl_pipeline',
        description='ETL пайплайн для обработки данных ветеринарной клиники',
        schedule_interval='@daily',
        default_args={
            'owner': 'veterinary_clinic_team',
            'retries': 1,
            'retry_delay': 60
        }
    )


    dag.tasks['extract_data'] = TaskInstance(
        task_id='extract_data',
        python_callable=task_extract_data,
        depends_on=[]
    )

    dag.tasks['transform_data'] = TaskInstance(
        task_id='transform_data',
        python_callable=task_transform_data,
        depends_on=['extract_data']
    )

    dag.tasks['load_to_database'] = TaskInstance(
        task_id='load_to_database',
        python_callable=task_load_to_database,
        depends_on=['transform_data']
    )

    dag.tasks['generate_final_report'] = TaskInstance(
        task_id='generate_final_report',
        python_callable=task_generate_final_report,
        depends_on=['load_to_database']
    )

    return dag

# основа

def main():
    """Основная функция запуска"""
    print("""
 
    """)


    create_data_directories()

 
    airflow = AirflowSimulator()


    dag = create_veterinary_clinic_dag()
    airflow.register_dag(dag)


    print("\n Запуск DAG...")
    dag_run = airflow.trigger_dag('veterinary_clinic_etl_pipeline')

    if dag_run and dag_run.status == 'success':
        print("\n ЛАБОРАТОРНАЯ РАБОТА ВЫПОЛНЕНА УСПЕШНО!")
        print("\n Результаты сохранены в папке 'data/':")
        print("   • data/input/ - исходные данные")
        print("   • data/output/ - отчеты и результаты")
        print("   • data/veterinary_clinic.db - база данных")
        print("   • airflow_simulator.log - лог выполнения")
    else:
        print("\n Ошибка при выполнении лабораторной работы")

    print("\n Программа завершена")

if __name__ == "__main__":
    main()
