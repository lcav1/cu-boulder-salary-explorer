#!/usr/bin/env python3
"""Collect the public CU report, Boulder only. Python standard library only."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

SOURCE = 'https://www.cu.edu/budget/cu-salary-database'
ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['campus', 'departmentGroup', 'departmentGroupDetail', 'department',
          'rosterId', 'jobTitle', 'jobFamily', 'fullTimePercent', 'salary', 'employeeRecord']
HEADERS = ['CAMPUS', 'DEPT GROUP', 'DEPT GROUP DETAIL', 'DEPT NAME', 'ROSTER ID',
           'JOB TITLE', 'JOB FAMILY', 'FULL-TIME %', 'TOTAL', 'EMPL RECORD']


class Report(HTMLParser):
    """Parse semantic report rows; omit Caspio's duplicated responsive labels."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.rows, self.headers, self.inputs = [], [], {}
        self.next_url = self.last_url = None
        self.in_row = self.in_cell = self.in_header = False
        self.skip = 0
        self.text, self.row = [], []
        self.feed(html)
        count = re.search(r'Records\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)', html)
        self.total = int(count[1].replace(',', '')) if count else None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('type') == 'hidden' and a.get('name'):
            self.inputs[a['name']] = a.get('value', '')
        if tag == 'a':
            if a.get('data-cb-name') == 'JumpToNext': self.next_url = a.get('href')
            if a.get('data-cb-name') == 'JumpToLast': self.last_url = a.get('href')
        if tag == 'tr' and a.get('data-cb-name') == 'data':
            self.in_row, self.row = True, []
        if tag == 'th': self.in_header, self.text = True, []
        if tag == 'td' and self.in_row: self.in_cell, self.text = True, []
        if tag == 'span' and 'data-tabular-html-cell-label' in a: self.skip += 1

    def handle_endtag(self, tag):
        if tag == 'span' and self.skip: self.skip -= 1
        if tag == 'th' and self.in_header:
            self.headers.append(' '.join(''.join(self.text).split()))
            self.in_header = False
        if tag == 'td' and self.in_cell:
            self.row.append(' '.join(''.join(self.text).split()))
            self.in_cell = False
        if tag == 'tr' and self.in_row:
            self.rows.append(self.row)
            self.in_row = False

    def handle_data(self, text):
        if (self.in_cell or self.in_header) and not self.skip: self.text.append(text)


def discover(html):
    year = re.search(r'CU Salary Information\s+FY\s+(\d{4}[-–]\d{2,4})', html)
    embed = re.search(r'src=[\"\'](https://[^\"\']+\.caspio\.com/dp/[^/\"\']+)/emb', html)
    if not year or not embed:
        raise ValueError('Source fiscal year or Caspio embed changed; refusing to publish.')
    return year[1].replace('–', '-'), embed[1]


def number(value):
    if value.strip() in ('', '-', 'N/A'): return None
    n = float(value.replace('$', '').replace(',', '').replace('%', ''))
    if not (0 <= n < float('inf')): raise ValueError('Invalid numeric source value')
    return n


def normalize(row, year):
    if len(row) != len(FIELDS): raise ValueError(f'Unexpected column count: {len(row)}')
    result = dict(zip(FIELDS, (v or None for v in row)))
    if result['campus'] != 'CU Boulder': raise ValueError('Non-Boulder record in report')
    result['salary'] = number(row[8])
    result['fullTimePercent'] = number(row[7])
    result['fiscalYear'] = year
    # Caspio's source row ID is not stable across reloads; preserve appointment identity.
    identity = [year, result['campus'], result['rosterId'], result['employeeRecord']]
    if not result['rosterId'] or result['employeeRecord'] is None:
        identity = [result[f] for f in ['fiscalYear'] + FIELDS]
    result['id'] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
    return result


def collect(output, delay=6.0):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(url, data=None):
        encoded = urllib.parse.urlencode(data).encode() if data is not None else None
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, encoded, headers={'User-Agent': 'CU-Boulder-Salary-Explorer/1.0 (public salary research)'})
                with opener.open(req, timeout=60) as response:
                    if response.status != 200:
                        raise OSError(f'Unexpected source HTTP status: {response.status}')
                    return response.read().decode('utf-8')
            except (OSError, TimeoutError) as error:
                if attempt == 3: raise
                print(f'Source request paused: {error}; retrying after {30 * (attempt + 1)} seconds.', flush=True)
                time.sleep(30 * (attempt + 1))

    year, endpoint = discover(request(SOURCE))
    search = Report(request(endpoint))
    form = search.inputs.copy()
    if form.get('FieldName1') != 'CAMPUS':
        raise ValueError('Campus search form changed; refusing an unscoped collection.')
    form['Value1_1'] = 'BOULDER'
    report = Report(request(endpoint, form))
    if report.headers != HEADERS: raise ValueError(f'Source schema changed: {report.headers}')
    expected = report.total
    if not expected or not report.rows: raise ValueError('Empty source report')
    records, seen_pages, page_count, raw_count = {}, set(), 0, 0
    while True:
        fingerprint = hashlib.sha256(json.dumps(report.rows).encode()).hexdigest()
        if fingerprint in seen_pages: raise ValueError('Repeated page; pagination failed')
        seen_pages.add(fingerprint)
        page_count += 1
        for row in report.rows:
            record = normalize(row, year)
            previous = records.get(record['id'])
            if previous and previous != record: raise ValueError('Conflicting appointment identity')
            records[record['id']] = record
        raw_count += len(report.rows)
        print(f'Page {page_count}: {raw_count}/{expected} source records', flush=True)
        if not report.next_url: break
        next_url = urllib.parse.urljoin(endpoint, report.next_url)
        if urllib.parse.urlsplit(next_url).netloc != urllib.parse.urlsplit(endpoint).netloc:
            raise ValueError('Unexpected pagination host')
        time.sleep(delay)
        for attempt in range(4):
            page_html = request(next_url)
            report = Report(page_html)
            if report.headers == HEADERS and report.total == expected:
                break
            if attempt == 3:
                Path('/tmp/cu-failed-page.html').write_text(page_html)
                raise ValueError(f'Source changed on page {page_count + 1}: headers={report.headers}, total={report.total}')
            time.sleep(2 ** (attempt + 1))
    if raw_count != expected or len(records) != expected:
        raise ValueError(f'Incomplete/duplicate report: {raw_count} rows, {len(records)} unique, expected {expected}')
    # Recheck year after pagination to avoid publishing a snapshot across annual rollover.
    if discover(request(SOURCE))[0] != year: raise ValueError('Fiscal year changed during collection')
    rows = sorted(records.values(), key=lambda r: r['id'])
    payload = {'schemaVersion': 1, 'fiscalYear': year, 'source': SOURCE,
               'reportUrl': endpoint, 'recordCount': len(rows), 'pagesCollected': page_count,
               'records': rows}
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    payload['contentSha256'] = digest
    old = json.loads(output.read_text()) if output.exists() else {}
    # An identical snapshot is a true no-op: no commit or deployment churn.
    if old.get('contentSha256') == digest and old.get('fiscalYear') == year:
        print('Unchanged snapshot; existing collection timestamp preserved.')
        return
    payload['collectedAt'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(output)
    print(f'Saved {len(rows)} Boulder appointment records, FY {year}, to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/salaries.json')
    args = parser.parse_args()
    collect(args.output)
