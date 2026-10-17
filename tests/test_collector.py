import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh import Report, discover, normalize, number, collect, HEADERS
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / 'tests/fixtures/source-report.html').read_text()


class CollectorTests(unittest.TestCase):
    def test_actual_source_markup(self):
        page = Report(FIXTURE)
        self.assertEqual(page.headers, HEADERS)
        self.assertEqual(len(page.rows), 2)
        self.assertEqual(page.total, 11043)
        row = normalize(page.rows[0], '2025-26')
        self.assertEqual(row['campus'], 'CU Boulder')
        self.assertEqual(row['rosterId'], 'R26-1000022')
        self.assertEqual(row['department'], 'Ecology & Evolutionary Biology')
        self.assertEqual(row['salary'], 1560)
        self.assertEqual(row['fullTimePercent'], 2.5)
        self.assertEqual(row['employeeRecord'], '0')

    def test_discovers_year_and_endpoint(self):
        year, url = discover('<h3>CU Salary Information FY 2030-31</h3><script src="https://example.caspio.com/dp/abc/emb"></script>')
        self.assertEqual(year, '2030-31')
        self.assertEqual(url, 'https://example.caspio.com/dp/abc')
        with self.assertRaises(ValueError): discover('Source layout changed')

    def test_rejects_other_campus_and_changed_schema(self):
        row = Report(FIXTURE).rows[0]
        with self.assertRaises(ValueError): normalize(['CU Denver'] + row[1:], '2025-26')
        with self.assertRaises(ValueError): normalize(row[:-1], '2025-26')

    def test_missing_values_and_identity(self):
        row = Report(FIXTURE).rows[0]
        first = normalize(row, '2025-26')
        second = normalize(row[:9] + ['1'], '2025-26')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['id'], normalize(row, '2025-26')['id'])
        row[7] = ''; row[8] = ''
        missing = normalize(row, '2025-26')
        self.assertIsNone(missing['salary'])
        self.assertIsNone(missing['fullTimePercent'])
        self.assertEqual(number('$1,234.56'),1234.56)
        for bad in ['nan', 'inf', '-1']:
            with self.assertRaises(ValueError): number(bad)

    def test_pagination_and_idempotent_snapshot(self):
        source = '<h3>CU Salary Information FY 2025-26</h3><script src="https://example.caspio.com/dp/abc/emb"></script>'
        rows = Report(FIXTURE).rows
        def report(row, number, next_page=False):
            markup='<table><tr>'+''.join(f'<th>{h}</th>' for h in HEADERS)+'</tr>'
            markup+='<tr data-cb-name="data">'+''.join(f'<td>{v}</td>' for v in row)+'</tr></table>'
            markup+=f'<p>Records {number}-{number} of 2</p>'
            if next_page: markup+='<a data-cb-name="JumpToNext" href="https://example.caspio.com/dp/abc?page=2">Next</a>'
            return markup
        class Response:
            status=200
            def __init__(self, body): self.body=body
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return self.body.encode()
        class Opener:
            def __init__(self, bodies): self.bodies=iter(bodies); self.requests=[]
            def open(self, req, timeout):
                self.requests.append(req)
                return Response(next(self.bodies))
        search='<input type="hidden" name="PageID" value="2"><input type="hidden" name="FieldName1" value="CAMPUS">'
        def bodies(): return [source,search,report(rows[0],1,True),report(rows[1],2),source]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json'
            opener=Opener(bodies())
            with patch('refresh.urllib.request.build_opener', return_value=opener): collect(path,delay=0)
            self.assertIn(b'Value1_1=BOULDER',opener.requests[2].data)
            first=path.read_bytes()
            self.assertEqual(json.loads(first)['pagesCollected'],2)
            with patch('refresh.urllib.request.build_opener', return_value=Opener(bodies())): collect(path,delay=0)
            self.assertEqual(first,path.read_bytes())
            # Duplicate page must fail and preserve the last complete snapshot.
            bad=[source,search,report(rows[0],1,True),report(rows[0],2)]
            with patch('refresh.urllib.request.build_opener', return_value=Opener(bad)):
                with self.assertRaises(ValueError): collect(path,delay=0)
            self.assertEqual(first,path.read_bytes())


class SnapshotTests(unittest.TestCase):
    def test_complete_actual_snapshot(self):
        path=ROOT/'data/salaries.json'
        self.assertTrue(path.exists(),'Run python3 -B scripts/refresh.py to collect source data')
        snapshot=json.loads(path.read_text())
        rows=snapshot['records']
        self.assertGreater(len(rows),1000)
        self.assertEqual(len(rows),snapshot['recordCount'])
        self.assertEqual(len(rows),len({r['id'] for r in rows}))
        self.assertEqual({r['campus'] for r in rows},{'CU Boulder'})
        self.assertEqual({r['fiscalYear'] for r in rows},{snapshot['fiscalYear']})
        self.assertTrue(snapshot['source'].startswith('https://www.cu.edu/'))
        self.assertEqual(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),snapshot['contentSha256'])
        for row in rows:
            self.assertTrue(all(field in row for field in ['salary','fullTimePercent','employeeRecord','departmentGroupDetail']))
            for key in ['salary','fullTimePercent']:
                self.assertTrue(row[key] is None or (isinstance(row[key],(int,float)) and row[key]>=0))


if __name__=='__main__': unittest.main()
