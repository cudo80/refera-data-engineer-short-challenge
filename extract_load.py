import argparse
import configparser
import datetime
import gzip
import logging
import os
import subprocess
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

BACKUP_PATH = '/tmp/'


def compress_file(src_file):
    compressed_file = "{}.gz".format(str(src_file))
    with open(src_file, 'rb') as f_in:
        with gzip.open(compressed_file, 'wb') as f_out:
            for line in f_in:
                f_out.write(line)
    return compressed_file


def extract_file(src_file):
    extracted_file, extension = os.path.splitext(src_file)
    print(extracted_file)
    with gzip.open(src_file, 'rb') as f_in:
        with open(extracted_file, 'wb') as f_out:
            for line in f_in:
                f_out.write(line)
    return extracted_file


def create_db(db_host, database, db_port, user_name, user_password):
    try:
        con = psycopg2.connect(dbname='postgres', port=db_port,
                               user=user_name, host=db_host,
                               password=user_password)

    except Exception as e:
        print(e)
        exit(1)

    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = con.cursor()
    try:
        cur.execute("DROP DATABASE {} ;".format(database))
    except Exception as e:
        print('DB does not exist, nothing to drop')
    cur.execute("CREATE DATABASE {} ;".format(database))
    cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {} ;".format(database, user_name))
    return database


def backup_postgres_db(source_host, database_name, port, user, password, dest_file):
    """
    Backup postgres db to a file.
    """

    try:
        process = subprocess.Popen(
            ['pg_dump',
             '--dbname=postgresql://{}:{}@{}:{}/{}'.format(user, password, source_host, port, database_name),
             '-Fc',
             '-f', dest_file,
             '-v'],
            stdout=subprocess.PIPE
        )
        output = process.communicate()[0]
        if int(process.returncode) != 0:
            print('Command failed. Return code : {}'.format(process.returncode))
            exit(1)
        return output
    except Exception as e:
        print(e)
        exit(1)


def restore_postgres_db(db_host, db, port, user, password, backup_file):
    """
    Restore postgres db from a file.
    """

    try:
        print(user, password, db_host, port, db)
        process = subprocess.Popen(
            ['pg_restore',
             '--no-owner',
             '--dbname=postgresql://{}:{}@{}:{}/{}'.format(user, password, db_host, port, db),
             '-v',
             backup_file],
            stdout=subprocess.PIPE
        )
        output = process.communicate()[0]
        if int(process.returncode) != 0:
            print('Command failed. Return code : {}'.format(process.returncode))

        return output
    except Exception as e:
        print("Issue with the db restore : {}".format(e))


def main():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    args_parser = argparse.ArgumentParser(description='Postgres database management')
    args_parser.add_argument("--action",
                             metavar="action",
                             choices=['restore', 'backup'],
                             required=True)
    args_parser.add_argument("--dest-db",
                             metavar="dest_db",
                             default=None,
                             help="Name of the new restored database")
    args_parser.add_argument("--configfile",
                             required=True,
                             help="Database configuration file")
    args = args_parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.configfile)

    postgres_source_host = config.get('postgresql', 'source_host')
    postgres_db_host = config.get('postgresql', 'db_host')
    postgres_port = config.get('postgresql', 'port')
    postgres_db = config.get('postgresql', 'db')
    postgres_restore = "{}_restore".format(postgres_db)
    postgres_user = config.get('postgresql', 'user')
    postgres_password = config.get('postgresql', 'password')
    timestr = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = 'backup-{}-{}.dump'.format(timestr, postgres_db)
    filename_compressed = '{}.gz'.format(filename)
    restore_filename = '/tmp/restore.dump.gz'
    restore_uncompressed = '/tmp/restore.dump'
    local_file_path = '{}{}'.format(BACKUP_PATH, filename)

    # backup task
    if args.action == "backup":
        logger.info('Backing up {} database to {}'.format(postgres_db, local_file_path))
        result = backup_postgres_db(postgres_source_host,
                                    postgres_db,
                                    postgres_port,
                                    postgres_user,
                                    postgres_password,
                                    local_file_path)
        for line in result.splitlines():
            logger.info(line)

        logger.info("Backup complete")
        logger.info("Compressing {}".format(local_file_path))
        comp_file = compress_file(local_file_path)

    # restore task
    elif args.action == "restore":

        logger.info("Creating temp database for restore : {}".format(postgres_restore))
        tmp_database = create_db(postgres_db_host,
                                 postgres_restore,
                                 postgres_port,
                                 postgres_user,
                                 postgres_password)
        logger.info("Created temp database for restore : {}".format(tmp_database))
        logger.info("Restore starting")
        result = restore_postgres_db(postgres_db_host,
                                     postgres_restore,
                                     postgres_port,
                                     postgres_user,
                                     postgres_password,
                                     restore_uncompressed
                                     )
        for line in result.splitlines():
            logger.info(line)
        logger.info("Restore complete")

    else:
        logger.warning("No valid argument was given.")
        logger.warning(args)


if __name__ == '__main__':
    main()
