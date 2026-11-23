"""Apply a solved Phase 3 allocation to the Phase 2 workbook + cross-phase RACI & journal.
Do not run until solution has been reviewed. Existing phase 1 entries are left unchanged.
"""
import json,statistics
from pathlib import Path
from artifact_tool import Blob,SpreadsheetFile
ROOT=Path(__file__).resolve().parents[2]
sol=json.loads((ROOT/'phase-02/calculations/allocation_solution.json').read_text(encoding='utf-8'))
model=json.loads((ROOT/'phase-02/input/model_task_data.json').read_text(encoding='utf-8'))
assign=sol['assignment']
book2=ROOT/'phase-02/calculations/Фаза_2_распределение_по_фазе_3.xlsx'
w=SpreadsheetFile.import_xlsx(Blob.load(str(book2)))
for i,t in enumerate(model['tasks'],6):
 name='Все' if t['kind']=='Общее' else 'У'+str(assign[t['id']])
 w.worksheets.get_item('WBS_фазы_3').get_range(f'G{i}').values=[[name]]
 w.worksheets.get_item('Предпочтения').get_range(f'F{i}').values=[[name]]
SpreadsheetFile.export_xlsx(w).save(str(book2))
# RACI/journal ID mapping: row 6= T01, thus T28 -> row 33
rpath=ROOT/'management/RACI_сквозная_T01_T53.xlsx'
rb=SpreadsheetFile.import_xlsx(Blob.load(str(rpath)))
r=rb.worksheets.get_item('RACI')
for t in model['tasks']:
 if t['kind']=='Общее':continue
 row=5+int(t['id'][1:]); owner=assign[t['id']]
 roles=['I','I','I'];roles[owner-1]='A/R'
 r.get_range(f'D{row}:F{row}').values=[roles]
SpreadsheetFile.export_xlsx(rb).save(str(rpath))
jpath=ROOT/'management/Журнал_задач_T01_T53.xlsx'
jb=SpreadsheetFile.import_xlsx(Blob.load(str(jpath)))
j=jb.worksheets.get_item('Журнал')
for t in model['tasks']:
 row=5+int(t['id'][1:])
 if t['kind']=='Общее':
  hh=t['estimates'];owner=1 if t['id'] in ('T28','T45','T52') else 3
 else:
  owner=assign[t['id']];h=statistics.median(t['estimates']);hh=[h if i+1==owner else 0 for i in range(3)]
 j.get_range(f'D{row}').values=[[f'У{owner}']]
 j.get_range(f'G{row}:I{row}').values=[list(hh)]
SpreadsheetFile.export_xlsx(jb).save(str(jpath))
print('Applied optimized assignments and new planned hours to 3 XLSX files. All actual dates/hours remain untouched.')
