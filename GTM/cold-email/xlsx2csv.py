# stdlib xlsx -> csv (first sheet)
import sys, zipfile, csv, re, xml.etree.ElementTree as ET
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
z=zipfile.ZipFile(sys.argv[1])
ss=[]
if 'xl/sharedStrings.xml' in z.namelist():
    for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns):
        ss.append(''.join(t.text or '' for t in si.iter('{%s}t'%ns['m'])))
sheets=sorted(n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml',n))
print('sheets',sheets,file=sys.stderr)
def col(ref):
    n=0
    for ch in re.match(r'[A-Z]+',ref).group():
        n=n*26+ord(ch)-64
    return n-1
rows=[]
for r in ET.fromstring(z.read(sheets[0])).iter('{%s}row'%ns['m']):
    out={}
    for c in r.findall('m:c',ns):
        t=c.get('t'); v=c.find('m:v',ns)
        if t=='s': val=ss[int(v.text)]
        elif t=='inlineStr': val=''.join(x.text or '' for x in c.iter('{%s}t'%ns['m']))
        else: val=v.text if v is not None else ''
        out[col(c.get('r'))]=val
    rows.append([out.get(i,'') for i in range(max(out)+1)] if out else [])
w=csv.writer(open(sys.argv[2],'w',newline=''))
w.writerows(rows)
