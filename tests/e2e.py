"""Real-data browser checks. Run with .venv/bin/python tests/e2e.py."""
from decimal import Decimal, ROUND_HALF_UP
import csv
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import io
import json
import os
from pathlib import Path
import statistics
import threading
import unittest
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'data/salaries.json').read_text()) if (ROOT/'data/salaries.json').exists() else None

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def money(value): return '$'+format(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP),',.0f')
def quantile(values,p):
    s=sorted(values);i=(len(s)-1)*p;lo=int(i);hi=min(lo+1,len(s)-1)
    return s[lo]+(s[hi]-s[lo])*(i-lo)

class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DATA is None: raise RuntimeError('Collect actual source data first')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright=sync_playwright().start()
        executable=os.environ.get('CHROME_PATH')
        local_chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        if not executable and Path(local_chrome).exists(): executable=local_chrome
        cls.browser=cls.playwright.chromium.launch(headless=True,executable_path=executable)
        (ROOT/'test-results').mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop();cls.server.shutdown();cls.server.server_close()

    def setUp(self):
        self.context=self.browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
        self.page=self.context.new_page();self.errors=[]
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        self.page.goto(self.url)
        expect(self.page.locator('#metrics')).to_have_attribute('aria-busy','false')
        expect(self.page.locator('#load-error')).to_be_hidden()

    def tearDown(self):
        self.assertEqual(self.errors,[])
        self.context.close()

    def select(self,key,value):
        self.page.locator(f'#{key}-details').evaluate('(el)=>el.open=true')
        self.page.locator(f'#{key}-search').fill(value[:16])
        self.page.locator(f'#{key}-options').get_by_role('checkbox',name=value,exact=True).check()
        self.page.locator(f'#{key}-details').evaluate('(el)=>el.open=false')

    def metric(self,i): return self.page.locator('.metric-value').nth(i).inner_text()

    def test_actual_snapshot_summary_and_charts(self):
        rows=DATA['records'];s=[r['salary'] for r in rows if r['salary'] is not None]
        self.assertEqual(self.metric(0),f'{len(rows):,}')
        self.assertEqual(self.metric(1),money(statistics.median(s)))
        self.assertEqual(self.metric(2),money(statistics.mean(s)))
        self.assertEqual(self.metric(3),money(quantile(s,.9)))
        self.assertEqual(self.metric(4),f"{sum(r['fullTimePercent'] is not None and r['fullTimePercent']>=100 for r in rows):,}")
        expect(self.page.locator('#year')).to_have_text('FY '+DATA['fiscalYear'])
        self.assertEqual(self.page.locator('#records tbody tr').count(),25)
        self.assertEqual(self.page.locator('#family-count .bar-row').count(),len({r['jobFamily'] for r in rows}))
        self.assertGreater(self.page.locator('#distribution svg rect').count(),0)
        self.assertGreater(self.page.locator('#group-chart .group-row').count(),0)
        self.page.screenshot(path=str(ROOT/'test-results/desktop.png'),full_page=True)

    def test_searchable_filter_minimum_and_combined_filters(self):
        self.page.locator('#jobFamily-details summary').click()
        self.page.locator('#jobFamily-search').fill('research')
        visible=self.page.locator('#jobFamily-options .filter-option:visible')
        self.assertGreater(visible.count(),0)
        for label in visible.all_inner_texts(): self.assertIn('research',label.lower())
        self.page.get_by_label('Research Faculty',exact=True).check()
        self.page.locator('#jobFamily-details').evaluate('(el)=>el.open=false')
        self.page.locator('#minimum').fill('90');self.page.locator('#minimum').dispatch_event('input')
        rows=[r for r in DATA['records'] if r['jobFamily']=='Research Faculty' and r['fullTimePercent'] is not None and r['fullTimePercent']>=90]
        self.assertEqual(self.metric(0),f'{len(rows):,}')
        group=rows[0]['departmentGroup'];self.select('departmentGroup',group)
        rows=[r for r in rows if r['departmentGroup']==group]
        title=rows[0]['jobTitle'];self.select('jobTitle',title)
        rows=[r for r in rows if r['jobTitle']==title]
        department=rows[0]['department'];self.select('department',department)
        rows=[r for r in rows if r['department']==department]
        self.assertEqual(self.metric(0),f'{len(rows):,}')
        self.assertEqual(self.metric(1),money(statistics.median(r['salary'] for r in rows if r['salary'] is not None)))
        self.assertEqual(self.page.locator('#family-median .bar-row').count(),1)
        self.assertEqual(self.page.locator('#family-count .bar-label strong').inner_text(),f'{len(rows):,}')
        self.assertEqual(self.page.locator('#family-median .bar-label strong').inner_text(),money(statistics.median(r['salary'] for r in rows if r['salary'] is not None)))
        self.assertEqual(self.page.locator('#group-chart .group-row').count(),1)
        self.assertEqual(self.page.locator('#group-chart .group-value').inner_text().split('\n')[0],money(statistics.median(r['salary'] for r in rows if r['salary'] is not None)))
        titles=self.page.locator('#distribution .histogram-bar title').all_text_contents()
        import re
        self.assertEqual(sum(int(re.search(r': ([\d,]+) records',t)[1].replace(',','')) for t in titles),len(rows))
        expect(self.page.locator('#scatter-note')).to_contain_text(f'{len(rows):,} points')
        self.page.locator('#reset').click()
        self.assertEqual(self.metric(0),f"{len(DATA['records']):,}")

    def test_salary_comparison_and_range(self):
        self.page.locator('#your-salary').fill('85000')
        s=[r['salary'] for r in DATA['records'] if r['salary'] is not None]
        expected=sum(v<=85000 for v in s)/len(s)*100
        expect(self.page.locator('#salary-percentile')).to_have_text(f'{expected:.1f}%')
        position=(85000-min(s))/(max(s)-min(s))*100
        expect(self.page.locator('#salary-position')).to_have_text(f'{position:.1f}%')
        self.select('jobFamily','Research Faculty')
        s=[r['salary'] for r in DATA['records'] if r['salary'] is not None and r['jobFamily']=='Research Faculty']
        expected=sum(v<=85000 for v in s)/len(s)*100
        expect(self.page.locator('#salary-percentile')).to_have_text(f'{expected:.1f}%')
        self.page.locator('#your-salary').fill('999999999')
        expect(self.page.locator('#comparison')).to_contain_text('above this range')
        self.page.locator('#your-salary').fill('-1')
        expect(self.page.locator('#salary-validation')).to_contain_text('valid salary')
        self.page.locator('#your-salary').fill('')
        expect(self.page.locator('#comparison')).to_contain_text('Enter a salary')

    def test_empty_results_and_reset(self):
        # Select an incompatible title/family pair from the real dataset.
        family=DATA['records'][0]['jobFamily']
        title=next(r['jobTitle'] for r in DATA['records'] if r['jobTitle'] and not any(p['jobFamily']==family and p['jobTitle']==r['jobTitle'] for p in DATA['records']))
        self.select('jobFamily',family);self.select('jobTitle',title)
        expect(self.page.locator('#empty')).to_be_visible()
        self.assertEqual(self.metric(0),'0');self.assertEqual(self.metric(1),'—')
        expect(self.page.locator('#export')).to_be_disabled()
        self.page.locator('#your-salary').fill('85000')
        expect(self.page.locator('#comparison')).to_contain_text('No known salaries')
        self.page.locator('#empty-reset').click()
        expect(self.page.locator('#empty')).to_be_hidden()

    def test_table_sort_pagination_and_peer_groups(self):
        self.page.get_by_role('button',name='Sort by Total salary',exact=True).click()
        s=sorted(r['salary'] for r in DATA['records'] if r['salary'] is not None)
        self.assertEqual(self.page.locator('#records tbody tr').first.locator('td').nth(4).inner_text(),money(s[0]))
        self.page.locator('#next').click()
        expect(self.page.locator('#page-label')).to_contain_text('Page 2')
        self.page.locator('#previous').click()
        button=self.page.locator('[data-peer]').first
        rid=button.get_attribute('data-peer');row=next(r for r in DATA['records'] if r['id']==rid)
        button.focus()
        expect(self.page.locator('#peer-tooltip')).to_be_visible()
        expect(self.page.locator('#peer-tooltip')).to_contain_text(row['departmentGroup'])
        peers=[
            [r for r in DATA['records'] if r['jobTitle']==row['jobTitle'] and r['departmentGroup']==row['departmentGroup']],
            [r for r in DATA['records'] if r['jobTitle']==row['jobTitle'] and r['fullTimePercent'] is not None and abs(r['fullTimePercent']-row['fullTimePercent'])<=10],
            DATA['records']]
        for i,group in enumerate(peers):
            salaries=[r['salary'] for r in group if r['salary'] is not None]
            content=self.page.locator('.peer-group').nth(i).inner_text()
            self.assertIn(money(statistics.median(salaries)),content)
            self.assertIn(f'{len(salaries):,}',content)
            self.assertIn(f"{sum(v<=row['salary'] for v in salaries)/len(salaries)*100:.1f}%",content)
        button.click()
        expect(self.page.locator('#peer-tooltip')).to_contain_text('dashboard filters do not affect')
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#peer-tooltip')).to_be_hidden()
        self.select('jobFamily',row['jobFamily'])
        self.page.locator(f'[data-peer="{rid}"]').first.click()
        last=self.page.locator('.peer-group').nth(2)
        all_salaries=[r['salary'] for r in DATA['records'] if r['salary'] is not None]
        expect(last).to_contain_text(f'{len(all_salaries):,}')
        expect(last).to_contain_text(money(statistics.median(all_salaries)))

    def test_csv_and_log_chart(self):
        self.select('jobFamily','Research Faculty')
        with self.page.expect_download() as event: self.page.locator('#export').click()
        download=event.value
        with open(download.path(),encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),sum(r['jobFamily']=='Research Faculty' for r in DATA['records']))
        self.assertEqual({r['campus'] for r in rows},{'CU Boulder'})
        self.page.locator('#log-scale').check()
        expect(self.page.locator('#distribution svg')).to_have_attribute('aria-label',__import__('re').compile('logarithmic'))

    def test_statistics_edge_cases_and_missing_data(self):
        result=self.page.evaluate('''async()=>{
          const s=await import('/assets/stats.js');
          const rows=[{id:'a',salary:10,fullTimePercent:100,jobTitle:'A',departmentGroup:'G'},{id:'b',salary:20,fullTimePercent:90,jobTitle:'A',departmentGroup:'G'},{id:'c',salary:20,fullTimePercent:89.99,jobTitle:'A',departmentGroup:'H'},{id:'d',salary:null,fullTimePercent:null,jobTitle:null,departmentGroup:null}];
          return {empty:s.summary([]),summary:s.summary(rows),p:s.percentile([10,20,20],20),q:s.quantile([0,100],.9),constant:s.compare([10,10],10),missing:s.compare([10],null),peers:s.buildPeers(rows)(rows[0]),filtered:s.filterRecords(rows,{jobTitle:new Set(['A'])},90).length,sort:s.sortRecords(rows,'salary',-1).map(r=>r.id)};
        }''')
        self.assertIsNone(result['empty']['median']);self.assertEqual(result['summary']['count'],4)
        self.assertEqual(result['summary']['salaryCount'],3);self.assertEqual(result['summary']['median'],20)
        self.assertEqual(result['p'],100);self.assertEqual(result['q'],90)
        self.assertIsNone(result['constant']['position']);self.assertIsNone(result['missing']['difference'])
        self.assertEqual([p['size'] for p in result['peers']],[2,2,3])
        self.assertEqual(result['filtered'],2);self.assertEqual(result['sort'][-1],'d')

    def test_responsive_and_keyboard(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),390)
        self.page.locator('#jobFamily-details summary').focus();self.page.keyboard.press('Enter')
        expect(self.page.locator('#jobFamily-search')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#jobFamily-search')).to_be_hidden()
        self.page.wait_for_timeout(200)
        self.page.screenshot(path=str(ROOT/'test-results/mobile.png'))

    def test_missing_data_ui_and_constant_salary_range(self):
        rows=[dict(DATA['records'][0]),dict(DATA['records'][1])]
        for i,row in enumerate(rows):
            row.update(id='edge-'+str(i),salary=100 if i==0 else None,fullTimePercent=None,jobFamily=None,jobTitle=None,departmentGroup=None,departmentGroupDetail=None)
        payload=dict(DATA,records=rows,recordCount=2)
        self.page.route('**/data/salaries.json',lambda route:route.fulfill(json=payload))
        self.page.reload()
        expect(self.page.locator('#metrics')).to_have_attribute('aria-busy','false')
        self.assertEqual(self.metric(0),'2');self.assertEqual(self.metric(1),'$100')
        expect(self.page.locator('#snapshot')).to_contain_text('1 filtered records missing salary')
        expect(self.page.locator('#family-median')).to_contain_text('Not reported')
        expect(self.page.locator('#scatter-note')).to_contain_text('0 points')
        self.page.locator('#your-salary').fill('100')
        expect(self.page.locator('#salary-percentile')).to_have_text('100.0%')
        expect(self.page.locator('#salary-position')).to_have_text('—')
        expect(self.page.locator('#comparison')).to_contain_text('all salaries are equal')
        self.page.locator('[data-peer]').first.click()
        expect(self.page.locator('.peer-group').first.locator('.peer-stats strong').nth(3)).to_have_text('0')

    def test_dataset_load_failure(self):
        self.page.route('**/data/salaries.json',lambda route:route.fulfill(status=503,body='unavailable'))
        self.page.reload()
        expect(self.page.locator('#load-error')).to_be_visible()
        expect(self.page.locator('#snapshot')).to_have_text('Salary snapshot unavailable')
        expect(self.page.locator('#reset')).to_be_disabled()
        expect(self.page.locator('#your-salary')).to_be_disabled()

if __name__=='__main__': unittest.main(verbosity=2)
