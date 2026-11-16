"""Real PostgreSQL semantics on a private disposable container; no host ports."""
import json
from pathlib import Path
import sys
from native_common import call,container,ready

IMAGE='postgres:18.7@sha256:2ea8630df176ad090ec92136dee850397c5af8781e4bcf2e4162593691c61bbc'
ROOT=Path(__file__).resolve().parents[1]


def run():
    cases=[]
    with container(IMAGE,['--env','POSTGRES_HOST_AUTH_METHOD=trust']) as (name,identity):
        def sql(text):return call(['docker','exec','-i',name,'psql','-X','-U','postgres','-v','ON_ERROR_STOP=1','-tA'],text).strip()
        ready(lambda:sql('SELECT 1;'))
        version=sql("SELECT current_setting('server_version');")
        assert version.split()[0]=='18.7';cases.append('exact engine version')
        sql('CREATE TABLE orders(id integer PRIMARY KEY, quantity integer NOT NULL CHECK(quantity>0), amount numeric(10,2), note text); INSERT INTO orders VALUES(1,2,0.30,NULL);')
        assert sql('SELECT quantity FROM orders WHERE id=1;')=='2';cases.append('valid constrained insert')
        try:sql('INSERT INTO orders VALUES(2,0,0.10,\'invalid\');')
        except RuntimeError:pass
        else:raise AssertionError('constraint failed to reject')
        assert sql('SELECT count(*) FROM orders;')=='1';cases.append('constraint rejects invalid quantity')
        sql('BEGIN;UPDATE orders SET quantity=9 WHERE id=1;ROLLBACK;')
        assert sql('SELECT quantity FROM orders WHERE id=1;')=='2';cases.append('rollback retains prior state')
        assert sql('SELECT (0.1::numeric(10,2)+0.2::numeric(10,2))::text;')=='0.30';cases.append('exact decimal arithmetic')
        assert sql('SELECT count(note) FROM orders;')=='0';cases.append('NULL remains distinct')
        sql('CREATE ROLE app LOGIN NOSUPERUSER NOBYPASSRLS NOREPLICATION;')
        try:sql('SET ROLE app;SELECT * FROM orders;')
        except RuntimeError:pass
        else:raise AssertionError('ungranted role read data')
        cases.append('ungranted application role denied')
        # Test actual pg_dump/restore behavior instead of repeating the blanket
        # community claim that logical dumps cannot be backups.
        dump=call(['docker','exec',name,'pg_dump','-U','postgres','--table=orders','--no-owner','--no-privileges'])
        sql('CREATE DATABASE restored;')
        call(['docker','exec','-i',name,'psql','-X','-U','postgres','-d','restored','-v','ON_ERROR_STOP=1'],dump)
        count=call(['docker','exec',name,'psql','-X','-U','postgres','-d','restored','-tAc','SELECT count(*) FROM orders;']).strip()
        assert count=='1';cases.append('logical dump restored into independent database')
        rows=json.loads(sql("SELECT json_object_agg(name,setting) FROM pg_settings WHERE name IN ('fsync','full_page_writes','autovacuum','ssl','password_encryption');"))
        roles=json.loads(sql("SELECT json_agg(x) FROM (SELECT rolname,rolsuper,rolbypassrls,rolreplication FROM pg_roles WHERE rolname='app') x;"))
        hba=json.loads(sql("SELECT json_agg(x) FROM (SELECT type,auth_method FROM pg_hba_file_rules WHERE error IS NULL) x;"))
        snapshot={'schemaVersion':1,'product':'postgresql','version':'18.7','settings':rows,'appRoles':roles,'hba':hba,'applicationSettings':{}}
        out=ROOT/'artifacts';out.mkdir(exist_ok=True)
        (out/'native-snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        return {'status':'Pass','engineVersion':version,'imageDigests':identity,'cases':cases,
                'expectedSnapshotVerdict':'Fail','limits':'Disposable local trust/no-TLS fixture is deliberately not production compliant. Restore is a tiny logical-backup demonstration, not PITR/HA qualification.'}


if __name__=='__main__':
    result=run();(ROOT/'artifacts/native-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
