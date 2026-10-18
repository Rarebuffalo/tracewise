import psycopg


def connect():
    # The service container must be healthy.
    return psycopg.connect("postgresql://postgres@127.0.0.1:5432/postgres")
