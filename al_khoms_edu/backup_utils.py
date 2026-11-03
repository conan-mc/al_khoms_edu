# -*- coding: utf-8 -*-
"""نسخة احتياطية كاملة لقاعدة بيانات الموقع (بديل عن mariadb-dump غير المتوفر)."""

import gzip
import os
import time

import frappe
import pymysql


def run():
    conf = frappe.conf
    db = conf.db_name
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(frappe.get_site_path(), "private", "backups")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{ts}-{db}-database.sql.gz")

    con = pymysql.connect(
        user=conf.db_user,
        password=conf.db_password or "",
        database=db,
        unix_socket=conf.db_socket or None,
        host=None if conf.db_socket else (conf.db_host or "127.0.0.1"),
        charset="utf8mb4",
    )
    cur = con.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]

    start = time.time()
    with gzip.open(out_path, "wt", encoding="utf-8", compresslevel=6) as f:
        f.write(f"-- Backup of {db} @ {ts}\nSET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n")
        for i, table in enumerate(tables, 1):
            cur.execute(f"SHOW CREATE TABLE `{table}`")
            create_sql = cur.fetchone()[1]
            f.write(f"\nDROP TABLE IF EXISTS `{table}`;\n{create_sql};\n")

            cur.execute(f"SELECT * FROM `{table}`")
            cols = [d[0] for d in cur.description]
            collist = ", ".join(f"`{c}`" for c in cols)
            batch, total = [], 0
            while True:
                rows = cur.fetchmany(200)
                if not rows:
                    break
                batch = [
                    "(" + ",".join("NULL" if v is None else con.escape(v) for v in row) + ")"
                    for row in rows
                ]
                f.write(f"INSERT INTO `{table}` ({collist}) VALUES\n" + ",\n".join(batch) + ";\n")
                total += len(rows)
            if i % 100 == 0:
                print(f"  ... {i}/{len(tables)} جدول")

        f.write("SET FOREIGN_KEY_CHECKS=1;\n")

    size = os.path.getsize(out_path)
    print(f"BACKUP_OK | {out_path} | {size/1024/1024:.2f} MB | tables={len(tables)} | {time.time()-start:.0f}s")
    return out_path
