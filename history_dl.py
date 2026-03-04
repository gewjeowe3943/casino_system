@app.route('/api/transactions/export')
def export_transactions():
    with get_db() as conn:
        rows = conn.execute('''
            SELECT t.id, p.name, t.change, t.timestamp, t.is_valid
            FROM transactions t
            JOIN players p ON t.player_id = p.id
            ORDER BY t.id DESC
        ''').fetchall()
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'プレイヤー名', '増減', '日時', '有効'])
    for r in rows:
        writer.writerow([r['id'], r['name'], r['change'], r['timestamp'], '有効' if r['is_valid'] else '無効'])
    response = app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=transactions.csv'}
    )
    return response