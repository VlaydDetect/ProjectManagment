#!/usr/bin/env python3
"""Imports numeric votes from three individual XLSX questionnaires into input_model.json.

No openpyxl required; XLSX is an OPC ZIP with XML spreadsheets.
Only reads cells E6:F31 from sheet 'Оценки'; never overwrites user questionnaires.
Requires 'ПОДТВЕРЖДЕНО' in Instructions!B7 for each expert unless --allow-demo.
Example: python sync_forms.py --forms-dir ../expert-inputs --model input_model.json
Then:   python solve_allocation.py
"""
import argparse, json, pathlib, re, zipfile
import xml.etree.ElementTree as ET

NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p':'http://schemas.openxmlformats.org/package/2006/relationships'}

def read_cells(path, sheet):
    with zipfile.ZipFile(path) as z:
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relmap={r.attrib['Id']:r.attrib['Target'] for r in rels}
        target=None
        for x in wb.find('x:sheets',NS):
            if x.attrib.get('name')==sheet:
                target=relmap[x.attrib['{%s}id'%NS['r']]]
                break
        if target is None:raise ValueError(f'Missing sheet {sheet} in {path}')
        target=target.lstrip('/')
        if not target.startswith('xl/'):target='xl/'+target
        content=ET.fromstring(z.read(target))
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            ss=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in ss.findall('x:si',NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//x:t',NS)))
        out={}
        for c in content.findall('.//x:c',NS):
            address=c.attrib.get('r','')
            typ=c.attrib.get('t','')
            v=c.find('x:v',NS)
            if typ=='inlineStr':
                out[address]=''.join(t.text or '' for t in c.findall('.//x:t',NS))
            elif v is not None and v.text is not None:
                if typ=='s':out[address]=shared[int(v.text)]
                elif typ in ('str','e'):out[address]=v.text
                else:out[address]=float(v.text)
        return out

def main():
    p=argparse.ArgumentParser(); p.add_argument('--forms-dir',type=pathlib.Path,default=pathlib.Path(__file__).parent.parent/'expert-inputs')
    p.add_argument('--model',type=pathlib.Path,default=pathlib.Path(__file__).with_name('input_model.json'))
    p.add_argument('--allow-demo',action='store_true',help='Allow placeholder questionnaires for verification ONLY')
    args=p.parse_args()
    model=json.loads(args.model.read_text(encoding='utf-8'))
    if len(model['tasks'])!=26:raise ValueError('Unexpected task count')
    hours=[[None]*3 for _ in model['tasks']]
    preferences=[[None]*3 for _ in model['tasks']]
    surveys=[]
    for j in range(3):
        fp=args.forms_dir/f'expert-{j+1}.xlsx'
        vals=read_cells(fp,'Оценки')
        inst=read_cells(fp,'Инструкция')
        full_name=str(inst.get('B5','')).strip(); date=str(inst.get('B6','')).strip()
        status=str(inst.get('B7','')).strip().upper()
        if not args.allow_demo:
            if status!='ПОДТВЕРЖДЕНО' or '[' in full_name or not full_name or '[' in date or not date:
                raise ValueError(f'{fp.name}: FIO/date/status not confirmed. Set Instructions!B7 = ПОДТВЕРЖДЕНО after personal review.')
        for i,t in enumerate(model['tasks']):
            row=6+i
            id_=str(vals.get(f'A{row}','')).strip()
            if id_!=t['id']:raise ValueError(f'{fp.name}!A{row}: expected {t["id"]}, got {id_}')
            hh=vals.get(f'E{row}');pp=vals.get(f'F{row}')
            if not isinstance(hh,(int,float)) or hh<0.5 or hh>20:raise ValueError(f'Invalid hours at {fp.name}:E{row}')
            if not isinstance(pp,(int,float)) or pp!=int(pp) or not 1<=pp<=9:raise ValueError(f'Invalid preference at {fp.name}:F{row}')
            hours[i][j]=round(float(hh),4);preferences[i][j]=int(pp)
        surveys.append({'name':full_name,'date':date,'status':status,'file':fp.name})
    model['individual_lead_hours']=hours
    model['individual_preferences']=preferences
    model['metadata']['status']=('ДАННЫЕ ИЗ ПОДТВЕРЖДЁННЫХ АНКЕТ' if not args.allow_demo else 'ПРОВЕРКА СИНТЕТИЧЕСКОГО ПРИМЕРА')
    model['metadata']['survey_info']=surveys
    args.model.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Updated',args.model,'records',len(hours),'from 3 expert XLSX forms; confirmed:',not args.allow_demo)
    print('NEXT: python solve_allocation.py')

if __name__=='__main__':main()
