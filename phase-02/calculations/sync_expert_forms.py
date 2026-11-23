"""Move participant-approved numerical ratings into the Phase 2 and Phase 3 models.
Use only after participants have actually confirmed their submissions. The script cannot verify authorship/consensus.
Run from anywhere: python phase-02/calculations/sync_expert_forms.py
Requires artifact_tool for XLSX read/write, not openpyxl.
"""
import json,statistics,sys
from pathlib import Path
from artifact_tool import Blob,SpreadsheetFile
ROOT=Path(__file__).resolve().parents[2]
modelpath=ROOT/'phase-02/input/model_task_data.json'
model=json.loads(modelpath.read_text(encoding='utf-8'))
ucpath=ROOT/'phase-03/use-cases/uc_data.json'
ucs=json.loads(ucpath.read_text(encoding='utf-8'))

ids2=[x['id'] for x in model['tasks']]
ids3=[x['id'] for x in ucs]
effort2=[[],[],[]];pref2=[[],[],[]];estimate3=[[],[],[]]
capability={}
for p in range(1,4):
 f=ROOT/f'phase-02/expert-inputs/expert-{p}.xlsx'
 w=SpreadsheetFile.import_xlsx(Blob.load(str(f)))
 eff=w.worksheets.get_item('Трудоёмкость').get_range('A6:D31').values
 prefs=w.worksheets.get_item('Предпочтения').get_range('A6:C31').values
 caps=w.worksheets.get_item('Компетенции').get_range('A6:C12').values
 if [r[0] for r in eff]!=ids2 or [r[0] for r in prefs]!=ids2:raise ValueError(f'WBS ID mismatch in {f}')
 for i,(e,pr) in enumerate(zip(eff,prefs)):
  h=e[3];q=pr[2]
  if not isinstance(h,(int,float)) or h<=0:raise ValueError((p,ids2[i],h))
  if not isinstance(q,(int,float)) or q!=int(q) or not 1<=q<=5:raise ValueError((p,ids2[i],q))
  effort2[p-1].append(float(h));pref2[p-1].append(int(q))
 for row in caps:
  category,_,yes=row
  if str(yes).strip().lower() in ('да','yes','true','1'):
   capability.setdefault(category,[]).append(p)
 f3=ROOT/f'phase-03/expert-inputs/expert-{p}.xlsx'
 w3=SpreadsheetFile.import_xlsx(Blob.load(str(f3)))
 m=w3.worksheets.get_item('Оценки_UC').get_range('A6:D17').values
 if [r[0] for r in m]!=ids3:raise ValueError(f'UC ID mismatch: {f3}')
 for i,r in enumerate(m):
  h=r[3]
  if not isinstance(h,(int,float)) or h<=0:raise ValueError((p,ids3[i],h))
  estimate3[p-1].append(float(h))

for i,t in enumerate(model['tasks']):
 t['estimates']=[effort2[p][i] for p in range(3)]
 t['preferences']=[pref2[p][i] for p in range(3)]
model['eligibility_by_group']=capability
model['status']='UPDATED_FROM_LOCAL_FORMS_REQUIRES_EXPLICIT_HUMAN_VALIDATION'
modelpath.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
ucmodel={ucs[i]['id']:[estimate3[p][i] for p in range(3)] for i in range(12)}
model3=ROOT/'phase-03/expert-inputs/model_estimates.json'
model3.write_text(json.dumps({'status':'UPDATED_FROM_LOCAL_FORMS_NOT_AUTOMATIC_CONSENSUS','model_estimates':ucmodel,'suggested_consensus':{i:statistics.median(v) for i,v in ucmodel.items()}},ensure_ascii=False,indent=2),encoding='utf-8')
# Patch visible inputs, keeping all formulas in place.
book2=ROOT/'phase-02/calculations/Фаза_2_распределение_по_фазе_3.xlsx'
w=SpreadsheetFile.import_xlsx(Blob.load(str(book2)))
w.worksheets.get_item('Оценки_времени').get_range('C6:E31').values=[[effort2[p][i] for p in range(3)] for i in range(26)]
w.worksheets.get_item('Предпочтения').get_range('C6:E31').values=[[pref2[p][i] for p in range(3)] for i in range(26)]
SpreadsheetFile.export_xlsx(w).save(str(book2))
book3=ROOT/'phase-03/measurements/Фаза_3_оценка_CampusEvents.xlsx'
w=SpreadsheetFile.import_xlsx(Blob.load(str(book3)))
w.worksheets.get_item('Эксперты_UC').get_range('C6:E17').values=[[estimate3[p][i] for p in range(3)] for i in range(12)]
SpreadsheetFile.export_xlsx(w).save(str(book3))
print('Synced six expert files: numerical inputs only. All final consensus and authorship still require sign-off. NEXT: solve_allocation.py then apply_solution.py')
