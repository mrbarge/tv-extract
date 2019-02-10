#!/bin/env python3

import psycopg2


def db_connect():
    conn = psycopg2.connect("dbname=tv_fanart_gallery user=matt")
    return conn


def main():
    dbcon = db_connect()

    cur = dbcon.cursor()
    cur.execute("SELECT * FROM gallery_items")
    row = cur.fetchone()
    print(row)
    cur.close()
    dbcon.close()


if __name__ == '__main__':
    main()
