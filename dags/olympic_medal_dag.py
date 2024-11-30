from datetime import datetime, timedelta
import random
import time
from airflow import DAG
from airflow.operators.python_operator import PythonOperator, BranchPythonOperator
from airflow.operators.mysql_operator import MySqlOperator
from airflow.sensors.sql import SqlSensor
from airflow.utils.trigger_rule import TriggerRule


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'olympic_medal_dag',
    default_args=default_args,
    description='DAG for medal processing',
    schedule_interval=None,
    start_date=datetime(2024, 11, 30),
    catchup=False,
)

create_table = MySqlOperator(
    task_id='create_table',
    mysql_conn_id='mysql_default',
    sql="""
        CREATE TABLE IF NOT EXISTS olympic_medal_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medal_type VARCHAR(50),
            count INT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """,
    dag=dag,
)

def pick_medal():
    return random.choice(['Bronze', 'Silver', 'Gold'])

pick_medal_task = BranchPythonOperator(
    task_id='pick_medal_task',
    python_callable=pick_medal,
    dag=dag,
)

def insert_medal_data(medal_type, mysql_conn_id='mysql_default'):
    from airflow.hooks.mysql_hook import MySqlHook
    hook = MySqlHook(mysql_conn_id=mysql_conn_id)
    sql_query = f"""
        SELECT COUNT(*) FROM athlete_event_results
        WHERE medal = '{medal_type}';
    """
    count = hook.get_first(sql_query)[0]
    insert_query = f"""
        INSERT INTO olympic_medal_data (medal_type, count)
        VALUES ('{medal_type}', {count});
    """
    hook.run(insert_query)

calc_bronze = PythonOperator(
    task_id='Bronze',
    python_callable=insert_medal_data,
    op_args=['Bronze'],
    dag=dag,
)

calc_silver = PythonOperator(
    task_id='Silver',
    python_callable=insert_medal_data,
    op_args=['Silver'],
    dag=dag,
)

calc_gold = PythonOperator(
    task_id='Gold',
    python_callable=insert_medal_data,
    op_args=['Gold'],
    dag=dag,
)

def delay_task():
    delay = random.randint(20, 40)
    print("Delay: ", delay)
    time.sleep(delay)


generate_delay = PythonOperator(
    task_id='generate_delay',
    python_callable=delay_task,
    trigger_rule=TriggerRule.ONE_SUCCESS,
    dag=dag,
)

check_for_correctness = SqlSensor(
    task_id='check_for_correctness',
    conn_id='mysql_default',
    sql="""
        SELECT 1 FROM olympic_medal_data
        WHERE TIMESTAMPDIFF(SECOND, created_at, NOW()) <= 30
        ORDER BY created_at DESC LIMIT 1;
    """,
    mode='poke',
    timeout=30,
    trigger_rule=TriggerRule.ONE_SUCCESS,
    dag=dag,
)


create_table >> pick_medal_task
pick_medal_task >> [calc_bronze, calc_silver, calc_gold]
[calc_bronze, calc_silver, calc_gold] >> generate_delay
generate_delay >> check_for_correctness
