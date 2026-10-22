import logging
import os
import subprocess
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def recreate_db(db_host, database, db_port, user_name, user_password, logger):
    logger.info(f"Connecting to {db_host}:{db_port} to recreate database {database}")
    try:
        # Connect to default 'postgres' database to drop/create other databases
        con = psycopg2.connect(
            dbname='postgres',
            port=db_port,
            user=user_name,
            host=db_host,
            password=user_password
        )
    except psycopg2.Error as e:
        logger.error(f"Error connecting to postgres database to recreate {database}: {e}")
        raise

    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()

    try:
        # Disconnect other clients before dropping the db if necessary
        cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{database}';")
        cur.execute(f"DROP DATABASE IF EXISTS {database};")
        logger.info(f"Dropped database {database} if it existed.")
    except psycopg2.Error as e:
        logger.error(f"Error dropping database {database}: {e}")

    try:
        cur.execute(f"CREATE DATABASE {database};")
        logger.info(f"Created database {database}.")
        cur.execute(f"GRANT ALL PRIVILEGES ON DATABASE {database} TO {user_name};")
        logger.info(f"Granted privileges to {user_name} on {database}.")
    except psycopg2.Error as e:
        logger.error(f"Error creating database {database}: {e}")
        raise
    finally:
        cur.close()
        con.close()


def backup_postgres_db(source_host, database_name, port, user, password, dest_file, logger):
    """
    Backup postgres db to a file.
    """
    logger.info(f"Backing up database {database_name} from {source_host} to {dest_file}")

    os.environ['PGPASSWORD'] = password

    try:
        process = subprocess.Popen(
            ['pg_dump',
             '-h', source_host,
             '-p', port,
             '-U', user,
             '-d', database_name,
             '-Fc', # Custom format
             '-f', dest_file,
             '-v'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"pg_dump failed with return code {process.returncode}")
            logger.error(f"pg_dump stderr: {stderr.decode('utf-8')}")
            raise Exception("pg_dump command failed")

        logger.info("Backup completed successfully.")
    except Exception as e:
        logger.error(f"Error during backup: {e}")
        raise
    finally:
        del os.environ['PGPASSWORD']


def restore_postgres_db(db_host, db, port, user, password, backup_file, logger):
    """
    Restore postgres db from a file.
    """
    logger.info(f"Restoring database {db} on {db_host} from {backup_file}")

    os.environ['PGPASSWORD'] = password

    try:
        process = subprocess.Popen(
            ['pg_restore',
             '-h', db_host,
             '-p', port,
             '-U', user,
             '-d', db,
             '--no-owner',
             '--role', user,
             '-v',
             backup_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        # pg_restore often throws warnings that are non-fatal, but a non-zero return code
        # may indicate serious issues. We will log the stderr.
        if process.returncode != 0:
            logger.warning(f"pg_restore finished with return code {process.returncode}. Stderr: {stderr.decode('utf-8')}")
        else:
            logger.info("Restore completed successfully.")

    except Exception as e:
        logger.error(f"Issue with the db restore: {e}")
        raise
    finally:
        del os.environ['PGPASSWORD']


def main():
    logger = setup_logger()

    # Load configuration from environment variables
    source_db_host = os.getenv('SOURCE_DB_HOST', 'transactional')
    source_db_port = os.getenv('SOURCE_DB_PORT', '5432')
    source_db_name = os.getenv('SOURCE_DB_NAME', 'dvdrental')
    source_db_user = os.getenv('SOURCE_DB_USER', 'postgres')
    source_db_password = os.getenv('SOURCE_DB_PASSWORD', 'password')

    dest_db_host = os.getenv('DEST_DB_HOST', 'analytics')
    dest_db_port = os.getenv('DEST_DB_PORT', '5432')
    dest_db_name = os.getenv('DEST_DB_NAME', 'analytics')
    dest_db_user = os.getenv('DEST_DB_USER', 'postgres')
    dest_db_password = os.getenv('DEST_DB_PASSWORD', 'password')

    backup_file_path = f'/tmp/backup_{source_db_name}.dump'

    try:
        # Step 1: Backup
        backup_postgres_db(
            source_host=source_db_host,
            database_name=source_db_name,
            port=source_db_port,
            user=source_db_user,
            password=source_db_password,
            dest_file=backup_file_path,
            logger=logger
        )

        # Step 2: Recreate destination DB to ensure it's clean
        recreate_db(
            db_host=dest_db_host,
            database=dest_db_name,
            db_port=dest_db_port,
            user_name=dest_db_user,
            user_password=dest_db_password,
            logger=logger
        )

        # Step 3: Restore
        restore_postgres_db(
            db_host=dest_db_host,
            db=dest_db_name,
            port=dest_db_port,
            user=dest_db_user,
            password=dest_db_password,
            backup_file=backup_file_path,
            logger=logger
        )

        logger.info("Data extraction and loading completed successfully!")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        exit(1)


if __name__ == '__main__':
    main()
