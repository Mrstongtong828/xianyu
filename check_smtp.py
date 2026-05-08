import sqlite3
conn = sqlite3.connect('data/xianyu_data.db')
cur = conn.cursor()
cur.execute("SELECT key, value FROM system_settings WHERE key LIKE 'smtp%'")
rows = cur.fetchall()
conn.close()
print('SMTP_CONFIG:')
for r in rows:
    status = 'SET' if r[1] else 'NOT_SET'
    print(f'  {r[0]}: {status}')
